# SPDX-FileCopyrightText: 2026 Khushwant Parihar
# SPDX-License-Identifier: MPL-2.0

"""Validation of tagged PDF logical structure."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from decimal import Decimal
from typing import TYPE_CHECKING, Any, NamedTuple, cast

from pikepdf._core import Page, Pdf
from pikepdf.models._content_stream import parse_content_stream
from pikepdf.models.structure._common import (
    _MAX_STRUCTURE_TREE_ELEMENTS,
    StructureTreeError,
    _appearance_dictionary_references_stream,
    _as_bool,
    _as_int,
    _as_page_obj,
    _effective_page_obj,
    _inherited_page_attribute,
    _is_name,
    _is_struct_elem,
    _kid_items,
    _object_identity,
    _ObjectIdentity,
    _ObjectKey,
    _require_object_graph_owner,
    _same_object,
    _stream_owner_references_stream,
    _WrapperIdentity,
    _XObjectContextKey,
)
from pikepdf.models.structure._content_analysis import (
    _CLOSE_OPERATORS,
    _OPEN_OPERATORS,
    _PATH_CLIPPING_OPERATORS,
    _PATH_CONSTRUCTION_OPERATORS,
    _PATH_END_OPERATORS,
    _SCOPE_CLOSE_TO_OPEN,
    _marked_content_kind,
    _xobject_content_kinds,
)
from pikepdf.models.structure._tree import StructElem, _structure_key_containers
from pikepdf.objects import (
    Array,
    Dictionary,
    Name,
    Object,
    Operator,
    Stream,
    String,
)

if TYPE_CHECKING:
    from pikepdf.models.structure._tree import StructTree


class _ValidationContentClaim(NamedTuple):
    owner: Dictionary
    page_key: _ObjectKey | None
    resource_context_key: _ObjectKey | None


class _Validator:
    def __init__(self, tree: StructTree):
        self.tree = tree

    @property
    def pdf(self) -> Pdf:
        return self.tree.pdf

    @property
    def obj(self) -> Dictionary:
        return self.tree.obj

    @property
    def exists(self) -> bool:
        return self.tree.exists

    @property
    def marked(self) -> bool:
        return self.tree.marked

    def validate(self, *, check_content: bool = True) -> list[str]:
        """Check the structure tree for inconsistencies.

        Verifies that the tree, the parent tree, the pages' ``/StructParents``
        keys and (optionally) the marked content actually present in the page
        content streams all agree with each other.

        Arguments:
            check_content: Also parse each page's content stream and check that
                its marked-content identifiers correspond to parent tree
                entries. Set to ``False`` to skip the parsing cost.

        Returns:
            A list of human-readable problem descriptions, empty if the
            structure tree is consistent.
        """
        problems: list[str] = []
        if not self.exists:
            return ["Document has no /StructTreeRoot"]
        raw_root = self.pdf.Root.get(Name.StructTreeRoot)
        if not isinstance(raw_root, Dictionary):
            return ["Document catalog /StructTreeRoot is not a dictionary"]
        root = raw_root
        if not root.is_indirect:
            problems.append("/StructTreeRoot is a direct object")
        elif not root.same_owner_as(self.pdf.Root):
            problems.append("/StructTreeRoot belongs to another PDF")
        root_type = root.get(Name.Type)
        if root_type is None:
            problems.append("/StructTreeRoot is missing required /Type")
        elif not _is_name(root_type, Name.StructTreeRoot):
            problems.append("/StructTreeRoot has the wrong /Type")
        namespace_members: list[Dictionary] = []
        namespaces_present = Name.Namespaces in root
        namespaces_shape_valid = False
        raw_namespaces = root.get(Name.Namespaces)
        if namespaces_present:
            if not isinstance(raw_namespaces, Array):
                problems.append("/StructTreeRoot /Namespaces is not an array")
            else:
                namespaces_shape_valid = True
                for index, namespace in enumerate(raw_namespaces):
                    if not isinstance(namespace, Dictionary) or isinstance(
                        namespace, Stream
                    ):
                        problems.append(
                            f"/StructTreeRoot /Namespaces[{index}] is not a "
                            "namespace dictionary"
                        )
                    elif not namespace.is_indirect:
                        problems.append(
                            f"/StructTreeRoot /Namespaces[{index}] is a direct object"
                        )
                    elif not namespace.same_owner_as(self.pdf.Root):
                        problems.append(
                            f"/StructTreeRoot /Namespaces[{index}] belongs to "
                            "another PDF"
                        )
                    elif namespace.get(Name.Type) not in (None, Name.Namespace):
                        problems.append(
                            f"/StructTreeRoot /Namespaces[{index}] has the wrong /Type"
                        )
                    elif not isinstance(namespace.get(Name.NS), String):
                        problems.append(
                            f"/StructTreeRoot /Namespaces[{index}] has no string /NS"
                        )
                    else:
                        namespace_members.append(namespace)
        role_map = root.get(Name.RoleMap)
        if role_map is not None:
            if not isinstance(role_map, Dictionary):
                problems.append("/StructTreeRoot /RoleMap is not a dictionary")
            else:
                for role in role_map.keys():
                    mapped_role = role_map[role]
                    if not isinstance(mapped_role, Name):
                        problems.append("/StructTreeRoot /RoleMap values must be names")
        problems.extend(self._validate_class_map(root.get(Name.ClassMap)))
        mark_info = self.pdf.Root.get(Name.MarkInfo)
        if (
            isinstance(mark_info, Dictionary)
            and _as_bool(mark_info.get(Name.Marked)) is None
        ):
            problems.append("Document catalog /MarkInfo /Marked is not a boolean")
        elif not self.marked:
            problems.append("Document catalog does not have /MarkInfo /Marked true")

        entries, has_parent_tree = self._validation_parent_entries(root, problems)
        entry_keys = sorted(entries)
        raw_next_key = root.get(Name.ParentTreeNextKey)
        next_key: int | None = None
        if raw_next_key is not None:
            next_key = _as_int(raw_next_key)
            if next_key is None:
                problems.append("/ParentTreeNextKey is not an integer")

        object_key = self._validation_object_key
        page_objects: dict[_ObjectKey, Object] = {}
        page_resources: dict[_ObjectKey, Object | None] = {}
        containers: dict[
            _ObjectKey,
            tuple[
                Object,
                str,
                Page | Object,
                list[tuple[Object | None, _ObjectKey | None]],
            ],
        ] = {}
        known_objects: dict[_ObjectKey, tuple[Object, str]] = {}
        annotation_pages: dict[_ObjectKey, set[_ObjectKey]] = {}

        def add_container(
            container: Object,
            label: str,
            source: Page | Object,
            resources: Object | None,
            resource_context_key: _ObjectKey | None,
        ) -> None:
            container_key = object_key(container)
            existing = containers.get(container_key)
            if existing is None:
                containers[container_key] = (
                    container,
                    label,
                    source,
                    [(resources, resource_context_key)],
                )
                return
            contexts = existing[3]
            if not any(
                _same_object(context_resources, resources)
                and context_key == resource_context_key
                for context_resources, context_key in contexts
            ):
                contexts.append((resources, resource_context_key))

        for page_number, page in enumerate(self.pdf.pages):
            page_obj_key = object_key(page.obj)
            page_objects[page_obj_key] = page.obj
            resources = _inherited_page_attribute(page, Name.Resources)
            page_resources[page_obj_key] = resources
            add_container(
                page.obj,
                f"Page {page_number}",
                page,
                resources,
                page_obj_key,
            )
            annots = page.obj.get(Name.Annots)
            if isinstance(annots, Array):
                for annot_number, annot in enumerate(annots):
                    if isinstance(annot, Dictionary):
                        annot_key = object_key(annot)
                        known_objects[annot_key] = (
                            annot,
                            f"Annotation {annot_number} on page {page_number}",
                        )
                        annotation_pages.setdefault(annot_key, set()).add(page_obj_key)
        for annot_key, pages in annotation_pages.items():
            if len(pages) > 1:
                label = known_objects[annot_key][1]
                problems.append(
                    f"{label} appears in the /Annots arrays of more than one page"
                )
        content_claims: dict[_ObjectKey, dict[int, list[_ValidationContentClaim]]] = {}
        object_claims: dict[
            _ObjectKey, list[tuple[Object, Dictionary, str, Object | None]]
        ] = {}
        element_ids: dict[bytes, list[Dictionary]] = {}

        def valid_page(page_obj: Object | None, owner: str) -> bool:
            if not isinstance(page_obj, Dictionary):
                problems.append(f"{owner} has content with no page")
                return False
            if (
                not page_obj.is_indirect
                or not _is_name(page_obj.get(Name.Type), Name.Page)
                or not page_obj.same_owner_as(self.pdf.Root)
                or not any(
                    _same_object(page_obj, candidate)
                    for candidate in page_objects.values()
                )
            ):
                problems.append(f"{owner} refers to a page outside the page tree")
                return False
            return True

        def add_content_claim(
            container: Object,
            mcid: int,
            owner: Dictionary,
            page_key: _ObjectKey | None,
            resource_context_key: _ObjectKey | None,
        ) -> None:
            claims = content_claims.setdefault(object_key(container), {})
            claims.setdefault(mcid, []).append(
                _ValidationContentClaim(owner, page_key, resource_context_key)
            )

        stack: list[tuple[bool, Dictionary, Dictionary]] = []
        for item in reversed(list(_kid_items(root.get(Name.K)))):
            if _is_struct_elem(item):
                element = cast(Dictionary, item)
                if element.is_indirect and not element.same_owner_as(self.pdf.Root):
                    problems.append(
                        "/StructTreeRoot /K contains a structure element that "
                        "belongs to another PDF"
                    )
                else:
                    stack.append((False, element, root))
            else:
                problems.append(
                    "/StructTreeRoot has a malformed /K entry that is not "
                    "a structure element"
                )

        seen: set[tuple[str, int, int]] = set()
        active: set[tuple[str, int, int]] = set()
        saw_content_item = False
        visited_elements = 0
        while stack:
            exiting, elem_obj, expected_parent = stack.pop()
            elem_key = object_key(elem_obj)
            if exiting:
                active.discard(elem_key)
                continue
            visited_elements += 1
            if visited_elements > _MAX_STRUCTURE_TREE_ELEMENTS:
                problems.append("Structure tree traversal limit exceeded")
                break

            elem = StructElem(elem_obj, self.tree)
            problems.extend(self._validate_parent_link(elem))
            actual_parent = elem_obj.get(Name.P)
            if isinstance(actual_parent, Dictionary) and not _same_object(
                actual_parent, expected_parent
            ):
                problems.append(
                    f"{elem!r} has a /P that does not name the element "
                    "whose /K contains it"
                )
            if elem_key in active:
                problems.append(f"{elem!r} creates a cycle in the structure tree")
                continue
            if elem_key in seen:
                problems.append(
                    f"{elem!r} appears more than once in the structure tree"
                )
                continue
            seen.add(elem_key)
            active.add(elem_key)
            stack.append((True, elem_obj, expected_parent))
            direct_parent = not elem_obj.is_indirect and Name.K in elem_obj
            if direct_parent:
                problems.append(
                    f"{elem!r} is a direct structure element and cannot be a parent"
                )
            if isinstance(elem_obj.get(Name.K), Array) and len(elem_obj.K) == 0:
                problems.append(f"{elem!r} has an empty /K array")

            if Name.Pg in elem_obj:
                explicit_page = elem_obj.get(Name.Pg)
                if not isinstance(explicit_page, Dictionary) or isinstance(
                    explicit_page, Stream
                ):
                    problems.append(f"{elem!r} has a /Pg that is not a page dictionary")
                elif not explicit_page.is_indirect:
                    problems.append(f"{elem!r} has a direct /Pg")
                elif not explicit_page.same_owner_as(self.pdf.Root):
                    problems.append(f"{elem!r} has a /Pg that belongs to another PDF")
                elif not _is_name(explicit_page.get(Name.Type), Name.Page):
                    problems.append(f"{elem!r} has a /Pg that is not a page dictionary")
                elif not any(
                    _same_object(explicit_page, page_obj)
                    for page_obj in page_objects.values()
                ):
                    problems.append(f"{elem!r} refers to a page outside the page tree")
            raw_namespace = elem_obj.get(Name.NS)
            if Name.NS in elem_obj:
                if not isinstance(raw_namespace, Dictionary) or isinstance(
                    raw_namespace, Stream
                ):
                    problems.append(
                        f"{elem!r} has an /NS that is not a namespace dictionary"
                    )
                elif not raw_namespace.is_indirect:
                    problems.append(f"{elem!r} has a direct /NS")
                elif not raw_namespace.same_owner_as(self.pdf.Root):
                    problems.append(f"{elem!r} has an /NS that belongs to another PDF")
                elif raw_namespace.get(Name.Type) is not None and not _is_name(
                    raw_namespace.get(Name.Type), Name.Namespace
                ):
                    problems.append(
                        f"{elem!r} has an /NS dictionary with the wrong /Type"
                    )
                elif not isinstance(raw_namespace.get(Name.NS), String):
                    problems.append(
                        f"{elem!r} has an /NS dictionary with no string /NS"
                    )
                else:
                    if not namespaces_present:
                        problems.append(
                            f"{elem!r} has an /NS but /StructTreeRoot has no "
                            "/Namespaces array"
                        )
                    elif namespaces_shape_valid and not any(
                        _same_object(raw_namespace, member)
                        for member in namespace_members
                    ):
                        problems.append(
                            f"{elem!r} has an /NS that is not registered in "
                            "/StructTreeRoot /Namespaces"
                        )
            tag = elem_obj.get(Name.S)
            if tag is None:
                problems.append(f"{elem!r} is missing required /S")
            elif not isinstance(tag, Name):
                problems.append(f"{elem!r} has an /S that is not a name")
            for text_key in (
                Name.Alt,
                Name.ActualText,
                Name.E,
                Name.Lang,
                Name.T,
            ):
                if text_key in elem_obj and not isinstance(
                    elem_obj.get(text_key), String
                ):
                    problems.append(
                        f"{elem!r} has a {text_key} that is not a text string"
                    )
            raw_element_id = elem_obj.get(Name.ID)
            if raw_element_id is not None:
                if not isinstance(raw_element_id, String):
                    problems.append(f"{elem!r} has an /ID that is not a string")
                else:
                    element_ids.setdefault(bytes(raw_element_id), []).append(elem_obj)
            attributes = elem_obj.get(Name.A)
            if attributes is not None:
                problems.extend(self._validate_attributes(elem, attributes))
            if Name.C in elem_obj:
                problems.extend(self._validate_class_names(elem, elem_obj.get(Name.C)))
            if Name.R in elem_obj:
                revision = _as_int(elem_obj.get(Name.R))
                if revision is None or revision < 0:
                    problems.append(
                        f"{elem!r} has an /R that is not a non-negative integer"
                    )

            effective_page = _effective_page_obj(elem_obj)
            child_elements: list[Dictionary] = []
            for item in _kid_items(elem_obj.get(Name.K)):
                mcid = _as_int(item)
                if mcid is not None:
                    saw_content_item = True
                    if mcid < 0:
                        problems.append(
                            f"{elem!r} has a marked-content identifier that "
                            "is not a non-negative integer"
                        )
                    elif valid_page(effective_page, repr(elem)):
                        page_key = object_key(cast(Object, effective_page))
                        add_content_claim(
                            cast(Object, effective_page),
                            mcid,
                            elem_obj,
                            page_key,
                            page_key,
                        )
                    continue
                if not isinstance(item, Dictionary):
                    if isinstance(item, bool | int | float | Decimal):
                        problems.append(
                            f"{elem!r} has a marked-content identifier that "
                            "is not a non-negative integer"
                        )
                        continue
                    problems.append(
                        f"{elem!r} has a malformed /K entry; expected a "
                        "structure element, /MCR, /OBJR, or non-negative integer"
                    )
                    continue
                item_type = item.get(Name.Type)
                if item_type is not None and not isinstance(item_type, Name):
                    problems.append(
                        f"{elem!r} has a malformed /K entry dictionary /Type"
                    )
                    continue
                if _is_name(item_type, Name.MCR):
                    saw_content_item = True
                    raw_mcid = item.get(Name.MCID)
                    ref_mcid = _as_int(raw_mcid)
                    if ref_mcid is None or ref_mcid < 0:
                        problems.append(
                            f"{elem!r} has an /MCR whose /MCID is not a "
                            "non-negative integer"
                        )
                    ref_page = item.get(Name.Pg, effective_page)
                    page_is_valid = valid_page(ref_page, repr(elem))
                    if (
                        Name.Pg in item
                        and isinstance(ref_page, Object)
                        and not ref_page.is_indirect
                    ):
                        problems.append(f"{elem!r} has an /MCR with a direct /Pg")
                    stream = item.get(Name.Stm)
                    stream_is_valid = stream is None
                    if stream is not None and not isinstance(stream, Stream):
                        problems.append(f"{elem!r} has an /MCR with an invalid /Stm")
                    elif isinstance(stream, Stream) and not stream.is_indirect:
                        problems.append(f"{elem!r} has an /MCR with a direct /Stm")
                    elif isinstance(stream, Stream) and not stream.same_owner_as(
                        self.pdf.Root
                    ):
                        problems.append(
                            f"{elem!r} has an /MCR with an /Stm that belongs "
                            "to another PDF"
                        )
                    else:
                        stream_is_valid = True
                    stream_owner = item.get(Name.StmOwn)
                    if stream_owner is not None and stream is None:
                        problems.append(
                            f"{elem!r} has an /MCR with /StmOwn but no /Stm"
                        )
                    if stream_owner is not None and (
                        not isinstance(stream_owner, Object)
                        or not stream_owner.is_indirect
                    ):
                        problems.append(
                            f"{elem!r} has an /MCR with a non-indirect /StmOwn"
                        )
                    elif isinstance(
                        stream_owner, Object
                    ) and not stream_owner.same_owner_as(self.pdf.Root):
                        problems.append(
                            f"{elem!r} has an /MCR with an /StmOwn that belongs "
                            "to another PDF"
                        )
                    elif ref_mcid is not None and ref_mcid >= 0:
                        if isinstance(stream, Stream) and stream_is_valid:
                            stream_label = self._validation_object_label(
                                stream, "Form XObject"
                            )
                            stream_resources = stream.get(Name.Resources)
                            has_stream_resources = Name.Resources in stream
                            if has_stream_resources and not isinstance(
                                stream_resources, Dictionary
                            ):
                                problems.append(
                                    f"{stream_label} has a /Resources that is not "
                                    "a dictionary"
                                )
                                stream_resources = None
                            stream_page_key = (
                                object_key(cast(Object, ref_page))
                                if page_is_valid
                                else None
                            )
                            if stream_owner is not None:
                                owner_key = object_key(cast(Object, stream_owner))
                                owner_references_stream = isinstance(
                                    stream_owner, Object
                                ) and _stream_owner_references_stream(
                                    stream_owner, stream, self.pdf
                                )
                                if not owner_references_stream:
                                    problems.append(
                                        f"{elem!r} has an /MCR whose /StmOwn does "
                                        "not reference /Stm"
                                    )
                                is_annotation_appearance = (
                                    isinstance(stream_owner, Dictionary)
                                    and not isinstance(stream_owner, Stream)
                                    and (
                                        _is_name(
                                            stream_owner.get(Name.Type), Name.Annot
                                        )
                                        or owner_key in annotation_pages
                                    )
                                    and _appearance_dictionary_references_stream(
                                        stream_owner, stream
                                    )
                                )
                                if is_annotation_appearance and (
                                    stream_page_key is None
                                    or stream_page_key
                                    not in annotation_pages.get(owner_key, set())
                                ):
                                    problems.append(
                                        f"{elem!r} has an annotation appearance "
                                        "/StmOwn that is not on /Pg"
                                    )
                            if not has_stream_resources and page_is_valid:
                                stream_resources = _inherited_page_attribute(
                                    cast(Object, ref_page), Name.Resources
                                )
                            add_container(
                                stream,
                                stream_label,
                                stream,
                                stream_resources,
                                stream_page_key,
                            )
                            add_content_claim(
                                stream,
                                ref_mcid,
                                elem_obj,
                                stream_page_key,
                                stream_page_key,
                            )
                        elif stream is None and page_is_valid:
                            page_key = object_key(cast(Object, ref_page))
                            add_content_claim(
                                cast(Object, ref_page),
                                ref_mcid,
                                elem_obj,
                                page_key,
                                page_key,
                            )
                    continue
                if _is_name(item_type, Name.OBJR):
                    saw_content_item = True
                    referent = item.get(Name.Obj)
                    if not isinstance(referent, Dictionary | Stream):
                        problems.append(f"{elem!r} has an /OBJR with no valid /Obj")
                        continue
                    if not referent.is_indirect:
                        problems.append(f"{elem!r} has an /OBJR with a direct /Obj")
                    elif not referent.same_owner_as(self.pdf.Root):
                        problems.append(
                            f"{elem!r} has an /OBJR with an /Obj that belongs "
                            "to another PDF"
                        )
                        continue
                    ref_page = item.get(Name.Pg, effective_page)
                    page_is_valid = valid_page(ref_page, repr(elem))
                    ref_key = object_key(referent)
                    is_annotation = (
                        isinstance(referent, Dictionary)
                        and not isinstance(referent, Stream)
                        and (
                            _is_name(referent.get(Name.Type), Name.Annot)
                            or ref_key in annotation_pages
                        )
                    )
                    if is_annotation and page_is_valid:
                        claimed_page = cast(Object, ref_page)
                        annots = claimed_page.get(Name.Annots)
                        if Name.Annots in claimed_page and not isinstance(
                            annots, Array
                        ):
                            problems.append(
                                f"{elem!r} has an /OBJR whose /Pg has malformed /Annots"
                            )
                        elif object_key(claimed_page) not in annotation_pages.get(
                            ref_key, set()
                        ):
                            problems.append(
                                f"{elem!r} has an annotation /OBJR that is not on /Pg"
                            )
                    label = known_objects.get(
                        ref_key,
                        (
                            referent,
                            self._validation_object_label(referent, "Object"),
                        ),
                    )[1]
                    object_claims.setdefault(ref_key, []).append(
                        (
                            referent,
                            elem_obj,
                            label,
                            cast(Object, ref_page) if page_is_valid else None,
                        )
                    )
                    continue
                if _is_struct_elem(item):
                    if item.is_indirect and not item.same_owner_as(self.pdf.Root):
                        problems.append(
                            f"{elem!r} has a child structure element that belongs "
                            "to another PDF"
                        )
                    elif not direct_parent:
                        child_elements.append(item)
                    continue
                problems.append(f"{elem!r} has a malformed /K entry dictionary")

            for child in reversed(child_elements):
                stack.append((False, child, elem_obj))

        id_entries, has_id_tree = self._validation_id_entries(root, problems)
        if element_ids and not has_id_tree:
            problems.append(
                "/StructTreeRoot is missing /IDTree required by element /ID values"
            )
        for element_id, owners in sorted(element_ids.items()):
            display_id = str(String(element_id))
            if len(owners) > 1:
                problems.append(
                    f"Structure element identifier {display_id!r} is not unique"
                )
            target = id_entries.get(element_id)
            if target is None:
                if has_id_tree:
                    problems.append(
                        f"Structure element identifier {display_id!r} is missing "
                        "from /IDTree"
                    )
            elif not isinstance(target, Dictionary) or not any(
                _same_object(target, owner) for owner in owners
            ):
                problems.append(
                    f"/IDTree entry {display_id!r} points to the wrong element"
                )
        for element_id, target in sorted(id_entries.items()):
            display_id = str(String(element_id))
            owners = element_ids.get(element_id, [])
            if not owners:
                problems.append(
                    f"/IDTree entry {display_id!r} has no matching reachable "
                    "structure element /ID"
                )
            elif not isinstance(target, Dictionary) or not any(
                _same_object(target, owner) for owner in owners
            ):
                problems.append(
                    f"/IDTree entry {display_id!r} does not map back to its element"
                )

        claimed_mcids_by_context: dict[
            _ObjectKey | None, dict[_ObjectIdentity, set[int]]
        ] = {}
        for container_key, by_mcid in content_claims.items():
            container_info = containers.get(container_key)
            if container_info is not None:
                container_identity = _object_identity(container_info[0])
                for mcid, claim_records in by_mcid.items():
                    for claim in claim_records:
                        claimed_mcids_by_context.setdefault(
                            claim.resource_context_key, {}
                        ).setdefault(container_identity, set()).add(mcid)
        structural_object_identities = {
            _object_identity(ref_claims[0][0])
            for ref_claims in object_claims.values()
            if ref_claims
        }

        if check_content:
            pending_contexts: list[
                tuple[
                    Page | Object,
                    Object | None,
                    _ObjectKey | None,
                    _WrapperIdentity | None,
                ]
            ] = [
                (Page(page_obj), page_resources[page_key], page_key, None)
                for page_key, page_obj in page_objects.items()
            ]
            execution_visits: dict[
                tuple[_ObjectKey, _ObjectKey | None, _WrapperIdentity | None], int
            ] = {}
            scheduled_contexts: dict[
                tuple[_ObjectKey, _ObjectKey | None, _WrapperIdentity | None], int
            ] = {}
            for source, _, context_key, inherited_wrapper in pending_contexts:
                source_obj = _as_page_obj(source)
                assert source_obj is not None
                scheduled_contexts[
                    (object_key(source_obj), context_key, inherited_wrapper)
                ] = 1
            form_execution_counts: dict[_ObjectKey, int] = {}
            form_execution_records: dict[
                _ObjectKey,
                list[tuple[_ObjectKey | None, _WrapperIdentity | None]],
            ] = {}
            while pending_contexts:
                (
                    execution_source,
                    resources,
                    context_key,
                    inherited_wrapper,
                ) = pending_contexts.pop()
                source_obj = _as_page_obj(execution_source)
                if source_obj is None:
                    continue
                execution_key = (
                    object_key(source_obj),
                    context_key,
                    inherited_wrapper,
                )
                visit_count = execution_visits.get(execution_key, 0)
                if visit_count >= 2:
                    continue
                execution_visits[execution_key] = visit_count + 1
                try:
                    instructions = list(parse_content_stream(execution_source))
                except Exception:
                    # The normal content-validation pass reports parse failures.
                    continue
                xobjects = (
                    resources.get(Name.XObject)
                    if isinstance(resources, Dictionary)
                    else None
                )
                if not isinstance(xobjects, Dictionary):
                    continue
                source_key = object_key(source_obj)
                source_claimed_mcids = {
                    mcid
                    for mcid, claim_records in content_claims.get(
                        source_key, {}
                    ).items()
                    if any(
                        claim.resource_context_key == context_key
                        for claim in claim_records
                    )
                }
                marked_scopes: list[tuple[int, bool]] = []
                for instruction_index, instruction in enumerate(instructions):
                    operator = getattr(instruction, "operator", None)
                    operands = list(getattr(instruction, "operands", ()))
                    if operator == Operator("BMC"):
                        marked_scopes.append((instruction_index, False))
                        continue
                    if operator == Operator("BDC"):
                        marked_scopes.append(
                            (
                                instruction_index,
                                _marked_content_kind(
                                    'BDC', operands, resources, source_claimed_mcids
                                )
                                is False,
                            )
                        )
                        continue
                    if operator == Operator("EMC"):
                        if marked_scopes:
                            marked_scopes.pop()
                        continue
                    if operator != Operator("Do"):
                        continue
                    if len(operands) != 1 or not isinstance(operands[0], Name):
                        continue
                    target = xobjects.get(operands[0])
                    if not isinstance(target, Stream) or not _is_name(
                        target.get(Name.Subtype), Name.Form
                    ):
                        continue
                    target_key = object_key(target)
                    local_wrapper = next(
                        (
                            (_object_identity(source_obj), opened_at)
                            for opened_at, is_structural in reversed(marked_scopes)
                            if is_structural
                        ),
                        None,
                    )
                    wrapper = (
                        local_wrapper
                        if local_wrapper is not None
                        else inherited_wrapper
                    )
                    form_execution_records.setdefault(target_key, []).append(
                        (context_key, wrapper)
                    )
                    form_execution_counts[target_key] = min(
                        2, form_execution_counts.get(target_key, 0) + 1
                    )
                    form_resources = target.get(Name.Resources)
                    has_form_resources = Name.Resources in target
                    form_label = self._validation_object_label(target, "Form XObject")
                    if has_form_resources and not isinstance(
                        form_resources, Dictionary
                    ):
                        problems.append(
                            f"{form_label} has a /Resources that is not a dictionary"
                        )
                        effective_resources = None
                    else:
                        effective_resources = (
                            form_resources
                            if has_form_resources
                            else (
                                page_resources[context_key]
                                if context_key is not None
                                and context_key in page_resources
                                else resources
                            )
                        )
                    form_context_key = context_key
                    add_container(
                        target,
                        form_label,
                        target,
                        effective_resources,
                        form_context_key,
                    )
                    target_execution_key = (
                        target_key,
                        form_context_key,
                        wrapper,
                    )
                    scheduled = scheduled_contexts.get(target_execution_key, 0)
                    if scheduled < 2:
                        scheduled_contexts[target_execution_key] = scheduled + 1
                        pending_contexts.append(
                            (
                                target,
                                effective_resources,
                                form_context_key,
                                wrapper,
                            )
                        )

            for form_key, execution_count in form_execution_counts.items():
                if execution_count < 2:
                    continue
                form_info = containers.get(form_key)
                if form_info is None or not isinstance(form_info[0], Stream):
                    continue
                _, label, _, _ = form_info
                has_structural_content = bool(content_claims.get(form_key))
                if has_structural_content:
                    problems.append(
                        f"{label} contains structural marked content but is "
                        "invoked more than once"
                    )

            for form_key, executions in form_execution_records.items():
                form_info = containers.get(form_key)
                if form_info is None:
                    continue
                _, label, _, _ = form_info
                ref_claims = object_claims.get(form_key, [])
                if ref_claims:
                    covered_pages = {
                        object_key(ref_page)
                        for _, _, _, ref_page in ref_claims
                        if ref_page is not None
                    }
                    observed_pages = {
                        page_key for page_key, _ in executions if page_key is not None
                    }
                    if observed_pages - covered_pages:
                        problems.append(
                            f"{label} is invoked on a page without a matching "
                            "/OBJR claim"
                        )
                    continue
                if len(executions) < 2 or content_claims.get(form_key):
                    continue
                wrappers = [wrapper for _, wrapper in executions]
                claimed_wrappers = [
                    wrapper for wrapper in wrappers if wrapper is not None
                ]
                if claimed_wrappers and (
                    len(claimed_wrappers) != len(wrappers)
                    or len(set(claimed_wrappers)) != len(claimed_wrappers)
                ):
                    problems.append(
                        f"{label} repeated invocations are not each enclosed by a "
                        "distinct claimed marked-content sequence"
                    )

        for container_key, by_mcid in content_claims.items():
            default_container: tuple[None, str, None, list[None]] = (
                None,
                "Content stream",
                None,
                [],
            )
            label = containers.get(container_key, default_container)[1]
            for mcid, claim_records in sorted(by_mcid.items()):
                if len(claim_records) < 2:
                    continue
                owner_keys = {object_key(claim.owner) for claim in claim_records}
                if len(owner_keys) > 1:
                    problems.append(
                        f"{label} MCID {mcid} is claimed by multiple structure elements"
                    )
                else:
                    problems.append(
                        f"{label} MCID {mcid} is claimed more than once by "
                        "the same structure element"
                    )

        key_users: dict[int, list[tuple[tuple[str, int, int], str]]] = {}
        for container_key, (
            container,
            label,
            source,
            resource_contexts,
        ) in containers.items():
            container_claims = content_claims.get(container_key, {})
            self._validate_content_container(
                container,
                label,
                source,
                resource_contexts,
                container_claims,
                entries,
                key_users,
                problems,
                check_content,
                page_resources,
                claimed_mcids_by_context,
                structural_object_identities,
            )

        for ref_key, ref_claims in object_claims.items():
            if len(ref_claims) > 1:
                ref_owner_keys = {
                    object_key(ref_owner) for _, ref_owner, _, _ in ref_claims
                }
                if len(ref_owner_keys) > 1:
                    problems.append(
                        f"{ref_claims[0][2]} is claimed by multiple structure elements"
                    )
                else:
                    valid_page_keys = [
                        object_key(ref_page)
                        for _, _, _, ref_page in ref_claims
                        if ref_page is not None
                    ]
                    if len(valid_page_keys) != len(set(valid_page_keys)):
                        problems.append(
                            f"{ref_claims[0][2]} is referenced more than once "
                            "by the same structure element on the same page"
                        )
            claimed_referent, ref_owner, ref_label, _ = ref_claims[0]
            self._validate_object_reference(
                ref_key,
                claimed_referent,
                ref_owner,
                ref_label,
                entries,
                key_users,
                problems,
            )

        structural_objects = dict(known_objects)
        for container_key, (container, label, _, _) in containers.items():
            structural_objects.setdefault(container_key, (container, label))
        for ref_key, ref_claims in object_claims.items():
            structural_objects.setdefault(ref_key, (ref_claims[0][0], ref_claims[0][2]))
        for candidate in _structure_key_containers(self.pdf):
            if (
                Name.StructParent not in candidate
                and Name.StructParents not in candidate
            ):
                continue
            candidate_key = object_key(candidate)
            kind = (
                "Form XObject"
                if isinstance(candidate, Stream)
                and _is_name(candidate.get(Name.Subtype), Name.Form)
                else "Object"
            )
            structural_objects.setdefault(
                candidate_key,
                (candidate, self._validation_object_label(candidate, kind)),
            )

        for ref_key, (referent, label) in structural_objects.items():
            if Name.StructParents not in referent or ref_key in containers:
                continue
            self._validate_content_container(
                referent,
                label,
                referent,
                [(None, None)],
                {},
                entries,
                key_users,
                problems,
                False,
                page_resources,
                claimed_mcids_by_context,
                structural_object_identities,
            )

        for ref_key, (referent, label) in structural_objects.items():
            if Name.StructParent not in referent or Name.StructParents not in referent:
                continue
            problems.append(
                f"{label} has both /StructParent and /StructParents; "
                "an object may carry at most one"
            )

        claimed_objects = set(object_claims)
        for ref_key, (referent, label) in structural_objects.items():
            if ref_key in claimed_objects or Name.StructParent not in referent:
                continue
            problems.append(
                f"{label} has /StructParent but no structure element /OBJR claims it"
            )
            raw_key = referent.get(Name.StructParent)
            struct_parent_key = _as_int(raw_key)
            if struct_parent_key is not None:
                key_users.setdefault(struct_parent_key, []).append((ref_key, label))

        has_content_items = bool(
            saw_content_item or content_claims or object_claims or key_users
        )
        if not has_parent_tree and has_content_items:
            problems.append(
                "/StructTreeRoot is missing required /ParentTree for its "
                "structure content items"
            )

        for parent_key, users in sorted(key_users.items()):
            distinct_users = {user_key for user_key, _ in users}
            if len(distinct_users) > 1:
                labels = ", ".join(dict.fromkeys(label for _, label in users))
                problems.append(
                    f"Parent tree key {parent_key} is shared by multiple "
                    f"objects: {labels}"
                )
        used_keys = set(key_users)
        all_keys = used_keys | set(entry_keys)
        if next_key is not None and all_keys and next_key <= max(all_keys):
            problems.append(
                f"/ParentTreeNextKey is {next_key}, but structural parent key "
                f"{max(all_keys)} is already used"
            )
        for parent_key in entry_keys:
            if parent_key not in used_keys:
                problems.append(
                    f"Parent tree entry {parent_key} is not referenced by any "
                    "/StructParents or /StructParent"
                )
        return problems

    @staticmethod
    def _validation_object_key(obj: Object) -> tuple[str, int, int]:
        if obj.is_indirect:
            return ("indirect", obj.objgen[0], obj.objgen[1])
        return ("direct", id(obj), 0)

    @staticmethod
    def _validation_object_label(obj: Object, kind: str) -> str:
        if obj.is_indirect:
            return f"{kind} {obj.objgen[0]} {obj.objgen[1]}"
        return f"Direct {kind.lower()}"

    def _validation_parent_entries(
        self, root: Dictionary, problems: list[str]
    ) -> tuple[dict[int, Object], bool]:
        raw_parent_tree = root.get(Name.ParentTree)
        if raw_parent_tree is None:
            return {}, False
        if not isinstance(raw_parent_tree, Dictionary):
            problems.append("/ParentTree is not a number-tree dictionary")
            return {}, True
        if raw_parent_tree.is_indirect and not raw_parent_tree.same_owner_as(
            self.pdf.Root
        ):
            problems.append("/ParentTree belongs to another PDF")
            return {}, True

        def parent_key(value: Any) -> int | None:
            return _as_int(value)

        entries = self._validation_tree_entries(
            raw_parent_tree,
            problems,
            tree_name="/ParentTree",
            values_name=Name.Nums,
            parse_key=parent_key,
            key_description="integers",
            entry_label="Parent tree entry",
        )
        return cast(dict[int, Object], entries), True

    def _validation_id_entries(
        self, root: Dictionary, problems: list[str]
    ) -> tuple[dict[bytes, Object], bool]:
        raw_id_tree = root.get(Name.IDTree)
        if raw_id_tree is None:
            return {}, False
        if not isinstance(raw_id_tree, Dictionary):
            problems.append("/IDTree is not a name-tree dictionary")
            return {}, True
        if raw_id_tree.is_indirect and not raw_id_tree.same_owner_as(self.pdf.Root):
            problems.append("/IDTree belongs to another PDF")
            return {}, True

        def id_key(value: Any) -> bytes | None:
            return bytes(value) if isinstance(value, String) else None

        entries = self._validation_tree_entries(
            raw_id_tree,
            problems,
            tree_name="/IDTree",
            values_name=Name.Names,
            parse_key=id_key,
            key_description="strings",
            entry_label="/IDTree entry",
        )
        id_entries = cast(dict[bytes, Object], entries)
        for key, target in id_entries.items():
            if (
                isinstance(target, Dictionary)
                and _is_struct_elem(target)
                and not target.is_indirect
            ):
                problems.append(
                    f"/IDTree entry {str(String(key))!r} is a direct structure element"
                )
        return id_entries, True

    def _validation_tree_entries(
        self,
        tree: Dictionary,
        problems: list[str],
        *,
        tree_name: str,
        values_name: Name,
        parse_key: Callable[[Any], int | str | bytes | None],
        key_description: str,
        entry_label: str,
    ) -> dict[int | str | bytes, Object]:
        entries: dict[int | str | bytes, Object] = {}
        root_identity = _object_identity(tree)
        scheduled = {root_identity}
        pending = [(tree, True)]
        traversal_order: list[_ObjectIdentity] = []
        records: dict[
            _ObjectIdentity,
            tuple[
                bool,
                list[int | str | bytes],
                list[_ObjectIdentity],
                tuple[int | str | bytes, int | str | bytes] | None,
            ],
        ] = {}

        def key_is_less(first: int | str | bytes, second: int | str | bytes) -> bool:
            if isinstance(first, int) and isinstance(second, int):
                return first < second
            if isinstance(first, str) and isinstance(second, str):
                return first < second
            if isinstance(first, bytes) and isinstance(second, bytes):
                return first < second
            return False

        visited_nodes = 0
        while pending:
            node, is_root = pending.pop()
            visited_nodes += 1
            if visited_nodes > _MAX_STRUCTURE_TREE_ELEMENTS:
                problems.append(f"{tree_name} traversal limit exceeded")
                break
            identity = _object_identity(node)
            traversal_order.append(identity)
            try:
                values = node.get(values_name)
                kids = node.get(Name.Kids)
                limits = node.get(Name.Limits)
            except Exception as error:
                problems.append(f"{tree_name} is malformed: {error}")
                records[identity] = (is_root, [], [], None)
                continue

            if values is not None and kids is not None:
                problems.append(
                    f"{tree_name} node contains both {values_name} and /Kids"
                )
            if values is None and kids is None:
                problems.append(f"{tree_name} node has neither {values_name} nor /Kids")

            parsed_limits: tuple[int | str | bytes, int | str | bytes] | None = None
            if limits is None:
                if not is_root:
                    problems.append(
                        f"{tree_name} non-root node is missing required /Limits"
                    )
            elif not isinstance(limits, Array) or len(limits) != 2:
                problems.append(f"{tree_name} node has malformed /Limits")
            else:
                lower = parse_key(limits[0])
                upper = parse_key(limits[1])
                if lower is None or upper is None:
                    problems.append(
                        f"{tree_name} node /Limits must contain {key_description}"
                    )
                elif key_is_less(upper, lower):
                    problems.append(
                        f"{tree_name} node /Limits are not in increasing order"
                    )
                else:
                    parsed_limits = (lower, upper)

            node_keys: list[int | str | bytes] = []
            if values is not None:
                if not isinstance(values, Array) or len(values) % 2:
                    problems.append(
                        f"{tree_name} node has a malformed {values_name} array"
                    )
                else:
                    previous_key: int | str | bytes | None = None
                    for index in range(0, len(values), 2):
                        key = parse_key(values[index])
                        value = values[index + 1]
                        if key is None:
                            problems.append(
                                f"{tree_name} keys must be {key_description}"
                            )
                            continue
                        node_keys.append(key)
                        if previous_key is not None and not key_is_less(
                            previous_key, key
                        ):
                            problems.append(
                                f"{tree_name} keys are not in strictly increasing order"
                            )
                        previous_key = key
                        if key in entries:
                            problems.append(
                                f"{tree_name} contains duplicate key {key!r}"
                            )
                        if value is None:
                            problems.append(f"{entry_label} {key!r} is null")
                        elif (
                            isinstance(value, Object)
                            and value.is_indirect
                            and not value.same_owner_as(self.pdf.Root)
                        ):
                            problems.append(
                                f"{entry_label} {key!r} belongs to another PDF"
                            )
                        else:
                            entries[key] = value

            child_identities: list[_ObjectIdentity] = []
            child_nodes: list[Dictionary] = []
            if kids is not None:
                if not isinstance(kids, Array):
                    problems.append(f"{tree_name} node has a malformed /Kids array")
                else:
                    for kid in kids:
                        if not isinstance(kid, Dictionary):
                            problems.append(
                                f"{tree_name} /Kids contains a non-dictionary"
                            )
                            continue
                        if not kid.is_indirect:
                            problems.append(f"{tree_name} /Kids contains a direct node")
                            continue
                        elif not kid.same_owner_as(self.pdf.Root):
                            problems.append(
                                f"{tree_name} /Kids contains a node that belongs "
                                "to another PDF"
                            )
                            continue
                        child_identity = _object_identity(kid)
                        if child_identity in scheduled:
                            problems.append(
                                f"{tree_name} contains a cycle or repeated node"
                            )
                            continue
                        scheduled.add(child_identity)
                        child_identities.append(child_identity)
                        child_nodes.append(kid)
            records[identity] = (
                is_root,
                node_keys,
                child_identities,
                parsed_limits,
            )
            pending.extend((child, False) for child in reversed(child_nodes))

        extents: dict[
            _ObjectIdentity,
            tuple[int | str | bytes, int | str | bytes] | None,
        ] = {}
        for identity in reversed(traversal_order):
            _, node_keys, child_identities, record_limits = records[identity]
            ranges = [(key, key) for key in node_keys]
            ranges.extend(
                child_extent
                for child_identity in child_identities
                if (child_extent := extents.get(child_identity)) is not None
            )
            extent: tuple[int | str | bytes, int | str | bytes] | None = None
            if ranges:
                lowest, highest = ranges[0]
                for lower, upper in ranges[1:]:
                    if key_is_less(lower, lowest):
                        lowest = lower
                    if key_is_less(highest, upper):
                        highest = upper
                extent = (lowest, highest)
            extents[identity] = extent

            if record_limits is not None and record_limits != extent:
                problems.append(
                    f"{tree_name} node /Limits do not match its subtree key range"
                )

            previous_upper: int | str | bytes | None = None
            for child_identity in child_identities:
                child_extent = extents.get(child_identity)
                if child_extent is None:
                    continue
                lower, upper = child_extent
                if previous_upper is not None and not key_is_less(
                    previous_upper, lower
                ):
                    problems.append(
                        f"{tree_name} /Kids subtrees are not in strictly "
                        "increasing, non-overlapping order"
                    )
                previous_upper = upper

        return entries

    @staticmethod
    def _validate_attributes(elem: StructElem, attributes: Object) -> list[str]:
        if isinstance(attributes, Dictionary | Stream):
            if not isinstance(attributes.get(Name.O), Name):
                return [f"{elem!r} has an /A attribute object without a name-valued /O"]
            return []
        if not isinstance(attributes, Array) or len(attributes) == 0:
            return [f"{elem!r} has an /A that is not an attribute dictionary or array"]
        may_have_revision = False
        for item in attributes:
            if isinstance(item, Dictionary | Stream):
                if not isinstance(item.get(Name.O), Name):
                    return [
                        f"{elem!r} has a malformed /A attribute array; each "
                        "attribute object requires a name-valued /O"
                    ]
                may_have_revision = True
                continue
            revision = _as_int(item)
            if revision is None or revision < 0 or not may_have_revision:
                return [f"{elem!r} has a malformed /A attribute array"]
            may_have_revision = False
        return []

    def _validate_class_map(self, class_map: Object | None) -> list[str]:
        if class_map is None:
            return []
        if not isinstance(class_map, Dictionary):
            return ["/StructTreeRoot /ClassMap is not a dictionary"]
        if class_map.is_indirect and not class_map.same_owner_as(self.pdf.Root):
            return ["/StructTreeRoot /ClassMap belongs to another PDF"]
        problems: list[str] = []
        for class_name in class_map.keys():
            value = class_map[class_name]
            objects = list(value) if isinstance(value, Array) else [value]
            if not objects or any(
                not isinstance(item, Dictionary | Stream)
                or not isinstance(item.get(Name.O), Name)
                for item in objects
            ):
                problems.append(
                    f"/ClassMap entry {class_name} is not an attribute object "
                    "or array of attribute objects with name-valued /O entries"
                )
                continue
            try:
                _require_object_graph_owner(value, self.pdf, "ClassMap attribute")
            except StructureTreeError:
                problems.append(f"/ClassMap entry {class_name} belongs to another PDF")
        return problems

    @staticmethod
    def _validate_class_names(elem: StructElem, value: Object | None) -> list[str]:
        if isinstance(value, Name):
            return []
        if not isinstance(value, Array) or len(value) == 0:
            return [f"{elem!r} has a malformed /C class-name value"]
        may_have_revision = False
        for item in value:
            if isinstance(item, Name):
                may_have_revision = True
                continue
            revision = _as_int(item)
            if revision is None or revision < 0 or not may_have_revision:
                return [f"{elem!r} has a malformed /C class-name array"]
            may_have_revision = False
        return []

    def _validate_parent_link(self, elem: StructElem) -> list[str]:
        parent = elem.obj.get(Name.P)
        if parent is None:
            return [f"{elem!r} is missing required /P"]
        if not isinstance(parent, Dictionary):
            return [f"{elem!r} has a /P that is not a dictionary"]
        if not parent.is_indirect:
            return [f"{elem!r} has a /P that is not an indirect reference"]
        if not parent.same_owner_as(self.pdf.Root):
            return [f"{elem!r} has a /P that belongs to another PDF"]
        if _same_object(parent, self.obj):
            return []
        if not _is_struct_elem(parent):
            return [f"{elem!r} has a /P that is not a structure element"]
        return []

    def _validate_content_container(
        self,
        container: Object,
        label: str,
        source: Page | Object,
        resource_contexts: list[tuple[Object | None, _ObjectKey | None]],
        claims: dict[int, list[_ValidationContentClaim]],
        entries: dict[int, Object],
        key_users: dict[int, list[tuple[tuple[str, int, int], str]]],
        problems: list[str],
        check_content: bool,
        page_resources: dict[_ObjectKey, Object | None],
        claimed_mcids_by_context: Mapping[
            _ObjectKey | None,
            Mapping[_ObjectIdentity, set[int] | frozenset[int]],
        ],
        structural_object_identities: set[_ObjectIdentity] | frozenset[_ObjectIdentity],
    ) -> None:
        raw_key = container.get(Name.StructParents)
        key = _as_int(raw_key)
        entry: Array | None = None
        if raw_key is None:
            if claims:
                problems.append(
                    f"{label} is referenced by the structure tree but has no "
                    "/StructParents"
                )
        elif key is None:
            problems.append(f"{label} has an invalid /StructParents value")
        else:
            key_users.setdefault(key, []).append(
                (self._validation_object_key(container), label)
            )
            raw_entry = entries.get(key)
            if raw_entry is None:
                problems.append(
                    f"{label} has /StructParents {key}, which is not in the parent tree"
                )
            elif not isinstance(raw_entry, Array):
                problems.append(f"Parent tree entry {key} for {label} is not an array")
            else:
                entry = raw_entry

        if entry is not None:
            for mcid, claim_records in sorted(claims.items()):
                if mcid >= len(entry) or not isinstance(entry[mcid], Dictionary):
                    problems.append(f"{label} MCID {mcid} has no parent tree entry")
                elif not entry[mcid].is_indirect:
                    problems.append(
                        f"{label} MCID {mcid} points to a direct structure element"
                    )
                elif not _is_struct_elem(entry[mcid]):
                    problems.append(
                        f"{label} MCID {mcid} points to an object that is not "
                        "a structure element"
                    )
                elif not any(
                    _same_object(entry[mcid], claim.owner) for claim in claim_records
                ):
                    problems.append(f"{label} MCID {mcid} points to the wrong element")
            for mcid, owner in enumerate(entry):
                if owner is None:
                    continue
                if not isinstance(owner, Dictionary):
                    problems.append(
                        f"Parent tree entry for {label} MCID {mcid} is not a "
                        "structure element"
                    )
                elif not owner.is_indirect and mcid not in claims:
                    problems.append(
                        f"Parent tree entry for {label} MCID {mcid} contains "
                        "a direct structure element"
                    )
                elif mcid not in claims:
                    problems.append(
                        f"Parent tree entry for {label} MCID {mcid} has no "
                        "matching structure element /K claim"
                    )

        if not check_content:
            return
        for resources, resource_context_key in resource_contexts:
            context_claims = {
                mcid: claim_records
                for mcid, claim_records in claims.items()
                if resource_context_key is None
                or any(
                    claim.resource_context_key == resource_context_key
                    for claim in claim_records
                )
            }
            top_resources = resources
            if (
                resource_context_key is not None
                and resource_context_key in page_resources
            ):
                top_resources = page_resources[resource_context_key]
            if resource_context_key is None:
                context_claimed_mcids: dict[_ObjectIdentity, set[int]] = {}
                for context_map in claimed_mcids_by_context.values():
                    for identity, mcids in context_map.items():
                        context_claimed_mcids.setdefault(identity, set()).update(mcids)
            else:
                context_claimed_mcids = {
                    identity: set(mcids)
                    for identity, mcids in claimed_mcids_by_context.get(
                        resource_context_key, {}
                    ).items()
                }
            found = self._validation_content_mcids(
                source,
                resources,
                label,
                problems,
                top_resources=top_resources,
                claimed_mcids=set(context_claims),
                claimed_mcids_by_identity=context_claimed_mcids,
                structural_object_identities=structural_object_identities,
            )
            if found is None:
                continue
            present = set(found)
            for mcid in sorted(set(context_claims) - present):
                problems.append(
                    f"{label} MCID {mcid} is claimed by a structure element but "
                    "does not appear in the content stream"
                )

    def _validation_content_mcids(
        self,
        source: Page | Object,
        resources: Object | None,
        label: str,
        problems: list[str],
        *,
        top_resources: Object | None,
        claimed_mcids: set[int] | frozenset[int],
        claimed_mcids_by_identity: Mapping[_ObjectIdentity, set[int] | frozenset[int]],
        structural_object_identities: set[_ObjectIdentity] | frozenset[_ObjectIdentity],
    ) -> list[int] | None:
        try:
            instructions = parse_content_stream(source)
        except Exception as error:
            problems.append(f"{label} content stream could not be parsed: {error}")
            return None
        found: list[int] = []
        all_mcids: list[int] = []
        marked_content_stack: list[tuple[str, tuple[str, ...]]] = []
        content_scope_stack: list[str] = []
        path_active = False
        xobject_cache: dict[_XObjectContextKey, frozenset[str]] = {}

        def open_scope(scope: str) -> None:
            active_scopes = [active_scope for active_scope, _ in marked_content_stack]
            if scope == "structural" and "structural" in active_scopes:
                problems.append(
                    f"{label} nests an MCID-bearing marked-content sequence "
                    "inside another structural marked-content sequence"
                )
            marked_content_stack.append((scope, tuple(content_scope_stack)))

        for instruction in instructions:
            operands = list(getattr(instruction, "operands", ()))
            operator = getattr(instruction, "operator", None)
            operator_name = str(operator) if isinstance(operator, Operator) else ""
            if operator_name in _OPEN_OPERATORS:
                content_scope_stack.append(operator_name)
            elif operator_name in _CLOSE_OPERATORS:
                expected_open = _SCOPE_CLOSE_TO_OPEN[operator_name]
                if not content_scope_stack:
                    problems.append(
                        f"{label} has {operator_name} without a matching "
                        f"{expected_open}"
                    )
                elif content_scope_stack[-1] != expected_open:
                    problems.append(
                        f"{label} has {operator_name} while "
                        f"{content_scope_stack[-1]} is the active content scope"
                    )
                else:
                    content_scope_stack.pop()
            if operator_name in {'m', 're'}:
                path_active = True
                continue
            if operator_name in _PATH_CONSTRUCTION_OPERATORS:
                if not path_active:
                    problems.append(
                        f"{label} has path construction outside a path object"
                    )
                    path_active = True
                continue
            if operator_name in _PATH_CLIPPING_OPERATORS:
                if not path_active:
                    problems.append(
                        f"{label} has a clipping operator outside a path object"
                    )
                continue
            if operator_name in _PATH_END_OPERATORS:
                if not path_active:
                    problems.append(
                        f"{label} has a path-painting operator outside a path object"
                    )
                path_active = False
                continue
            if path_active and operator_name in {'BMC', 'BDC', 'EMC'}:
                problems.append(
                    f"{label} has a marked-content boundary inside a path object"
                )
            elif path_active:
                problems.append(
                    f"{label} has operator {operator_name or '<unknown>'} inside "
                    "an active path object"
                )
            if operator == Operator("Do"):
                if not any(scope == "structural" for scope, _ in marked_content_stack):
                    continue
                if len(operands) != 1 or not isinstance(operands[0], Name):
                    problems.append(f"{label} has a malformed Do operator")
                    continue
                xobjects = (
                    resources.get(Name.XObject)
                    if isinstance(resources, Dictionary)
                    else None
                )
                target = (
                    xobjects.get(operands[0])
                    if isinstance(xobjects, Dictionary)
                    else None
                )
                target_is_structural = (
                    isinstance(target, Dictionary | Stream)
                    and _object_identity(target) in structural_object_identities
                )
                if isinstance(target, Stream):
                    try:
                        target_is_structural = target_is_structural or (
                            'structural'
                            in _xobject_content_kinds(
                                target,
                                top_resources=top_resources,
                                cache=xobject_cache,
                                visiting=set(),
                                claimed_mcids=claimed_mcids_by_identity,
                                structural_objects=structural_object_identities,
                            )
                        )
                    except StructureTreeError:
                        # Other validation passes report malformed Form graphs.
                        pass
                if target_is_structural:
                    problems.append(
                        f"{label} invokes a structural object from inside an "
                        "MCID-bearing marked-content sequence"
                    )
                continue
            if operator not in {
                Operator("BMC"),
                Operator("BDC"),
                Operator("EMC"),
            }:
                continue
            if operator == Operator("EMC"):
                if operands:
                    problems.append(f"{label} has an EMC operator with operands")
                if not marked_content_stack:
                    problems.append(f"{label} has an EMC without a matching BMC or BDC")
                else:
                    _, opening_content_scopes = marked_content_stack.pop()
                    if opening_content_scopes != tuple(content_scope_stack):
                        problems.append(
                            f"{label} has a marked-content sequence that crosses "
                            "a q/Q, BT/ET, or BX/EX boundary"
                        )
                continue
            if operator == Operator("BMC"):
                if len(operands) != 1 or not isinstance(operands[0], Name):
                    problems.append(f"{label} has a malformed BMC operator")
                scope = (
                    "artifact"
                    if len(operands) == 1 and _is_name(operands[0], Name.Artifact)
                    else "other"
                )
                open_scope(scope)
                continue
            if len(operands) != 2:
                problems.append(f"{label} has a malformed BDC operator")
                open_scope("other")
                continue
            tag = operands[0]
            if not isinstance(tag, Name):
                problems.append(f"{label} has a BDC tag that is not a name")
            nonstructural_scope = (
                "artifact" if _is_name(tag, Name.Artifact) else "other"
            )
            properties = operands[1]
            if not isinstance(properties, Name | Dictionary):
                problems.append(
                    f"{label} has a BDC property list that is not a name or dictionary"
                )
                open_scope(nonstructural_scope)
                continue
            if isinstance(properties, Name):
                if not isinstance(resources, Dictionary):
                    problems.append(
                        f"{label} uses named marked-content properties "
                        f"{properties} that cannot be resolved"
                    )
                    open_scope(nonstructural_scope)
                    continue
                property_dict = resources.get(Name.Properties)
                properties = (
                    property_dict.get(properties)
                    if isinstance(property_dict, Dictionary)
                    else None
                )
                if properties is None:
                    problems.append(
                        f"{label} uses named marked-content properties that "
                        "cannot be resolved"
                    )
                    open_scope(nonstructural_scope)
                    continue
            if not isinstance(properties, Dictionary) or Name.MCID not in properties:
                open_scope(nonstructural_scope)
                continue
            raw_mcid = properties.get(Name.MCID)
            mcid = _as_int(raw_mcid)
            scope = (
                "artifact"
                if _is_name(tag, Name.Artifact)
                else (
                    "structural"
                    if mcid is not None and mcid >= 0 and mcid in claimed_mcids
                    else "other"
                )
            )
            open_scope(scope)
            if mcid is None or mcid < 0:
                problems.append(
                    f"{label} content stream has an /MCID that is not a "
                    "non-negative integer"
                )
                continue
            all_mcids.append(mcid)
            if _is_name(tag, Name.Artifact):
                continue
            found.append(mcid)
        if marked_content_stack:
            problems.append(
                f"{label} has {len(marked_content_stack)} unclosed marked-content "
                "sequence(s)"
            )
        if content_scope_stack:
            problems.append(f"{label} has unclosed q, BT, or BX content scope(s)")
        if path_active:
            problems.append(f"{label} has an unclosed path object")
        counts: dict[int, int] = {}
        for mcid in all_mcids:
            counts[mcid] = counts.get(mcid, 0) + 1
        for mcid, count in sorted(counts.items()):
            if count > 1:
                problems.append(
                    f"{label} uses marked content identifier {mcid} {count} "
                    "times; they must be unique"
                )
        if all_mcids and min(all_mcids) != 0:
            problems.append(f"{label} marked content identifiers must start at 0")
        return found

    def _validate_object_reference(
        self,
        ref_key: tuple[str, int, int],
        referent: Object,
        owner: Dictionary,
        label: str,
        entries: dict[int, Object],
        key_users: dict[int, list[tuple[tuple[str, int, int], str]]],
        problems: list[str],
    ) -> None:
        raw_key = referent.get(Name.StructParent)
        key = _as_int(raw_key)
        if raw_key is None:
            problems.append(f"{label} is referenced by /OBJR but has no /StructParent")
            return
        if key is None:
            problems.append(f"{label} has an invalid /StructParent value")
            return
        key_users.setdefault(key, []).append((ref_key, label))
        entry = entries.get(key)
        if entry is None:
            problems.append(
                f"{label} has /StructParent {key}, which is not in the parent tree"
            )
        elif not isinstance(entry, Dictionary) or not _is_struct_elem(entry):
            problems.append(
                f"Parent tree entry {key} for {label} is not a structure element"
            )
        elif not entry.is_indirect:
            problems.append(
                f"Parent tree entry {key} for {label} is a direct structure element"
            )
        elif not _same_object(entry, owner):
            problems.append(f"{label} points to the wrong structure element")


def _validate_tree(tree: StructTree, *, check_content: bool = True) -> list[str]:
    return _Validator(tree).validate(check_content=check_content)


def _validation_id_entries(
    tree: StructTree, root: Dictionary, problems: list[str]
) -> tuple[dict[bytes, Object], bool]:
    return _Validator(tree)._validation_id_entries(root, problems)
