# SPDX-FileCopyrightText: 2026 Khushwant Parihar
# SPDX-License-Identifier: MPL-2.0

"""Logical structure tree objects and parent-tree mutation."""

from __future__ import annotations

from collections.abc import Iterable, Iterator, Mapping
from dataclasses import dataclass
from typing import NamedTuple, cast

from pikepdf._core import NameTree, NumberTree, Page, Pdf
from pikepdf.models.structure._common import (
    _MAX_STRUCTURE_TREE_ELEMENTS,
    StructureTreeError,
    _appearance_dictionary_references_stream,
    _as_bool,
    _as_int,
    _as_page_obj,
    _effective_page_obj,
    _form_xobjects,
    _inherited_page_attribute,
    _is_name,
    _is_page_annotation,
    _is_struct_elem,
    _kid_items,
    _locked,
    _object_identity,
    _ObjectIdentity,
    _page_has_annotation,
    _require_attributes,
    _require_content_container,
    _require_namespace,
    _require_owned_indirect,
    _require_page,
    _require_referent,
    _require_stream,
    _safe_object_description,
    _same_graph_node,
    _same_object,
    _stream_owner_references_stream,
    _validate_integer,
    _validate_mcid,
    _validate_nonnegative_int,
)
from pikepdf.models.structure._content_analysis import (
    _claims_create_structural_nesting,
    _observed_form_execution_count,
)
from pikepdf.objects import (
    Array,
    Dictionary,
    Name,
    Object,
    Stream,
    String,
)


@dataclass
class _ContentCheckState:
    key_users: dict[int, list[tuple[Object, Name]]]
    claims: dict[tuple[_ObjectIdentity, int], list[StructElem]]
    claim_pages: dict[_ObjectIdentity, set[_ObjectIdentity]]
    attached: set[_ObjectIdentity]
    validated_containers: set[_ObjectIdentity]
    number_tree: NumberTree | None
    parent_tree_keys: set[int]
    next_available_key: int
    prospective_keys: dict[_ObjectIdentity, int]


class _ParentRemovalPlan(NamedTuple):
    number_tree: NumberTree | None
    entries: list[tuple[int, Object]]
    removed_objgens: set[tuple[int, int]]
    referents: list[Object]


class _IdRemovalPlan(NamedTuple):
    entries: dict[bytes, Object]


def _strict_effective_page_obj(elem_obj: Dictionary, tree: StructTree) -> Object | None:
    """Resolve inherited ``/Pg`` while requiring a valid ancestry chain."""
    current = elem_obj
    active: list[Object] = []
    effective_page: Object | None = None
    visited = 0
    while True:
        visited += 1
        if visited > _MAX_STRUCTURE_TREE_ELEMENTS:
            raise StructureTreeError("Structure element ancestry is too deep")
        if any(_same_graph_node(current, candidate) for candidate in active):
            raise StructureTreeError("Structure element ancestry contains a cycle")
        active.append(current)
        if current.is_indirect and not current.same_owner_as(tree.pdf.Root):
            raise StructureTreeError(
                "Structure element ancestry belongs to another PDF"
            )
        if effective_page is None and Name.Pg in current:
            effective_page = current.get(Name.Pg)
        parent = current.get(Name.P)
        if not isinstance(parent, Dictionary) or isinstance(parent, Stream):
            raise StructureTreeError(
                "Structure element ancestry has a missing or malformed /P"
            )
        if not parent.is_indirect:
            raise StructureTreeError(
                "Structure element ancestry has a direct /P reference"
            )
        if not parent.same_owner_as(tree.pdf.Root):
            raise StructureTreeError(
                "Structure element ancestry has a /P from another PDF"
            )
        if _same_object(parent, tree.obj):
            return effective_page
        if _is_name(parent.get(Name.Type), Name.StructTreeRoot):
            raise StructureTreeError(
                "Structure element ancestry belongs to another structure tree"
            )
        if not _is_struct_elem(parent):
            raise StructureTreeError(
                "Structure element ancestry /P is not a structure element"
            )
        current = parent


def _content_references(elem: StructElem) -> Iterator[MarkedContentRef]:
    """Marked-content references of *elem*, skipping malformed ``/K`` entries."""
    page_obj = _effective_page_obj(elem.obj)
    for item in _kid_items(elem.obj.get(Name.K)):
        is_mcr = isinstance(item, Dictionary) and _is_name(
            item.get(Name.Type), Name.MCR
        )
        if _as_int(item) is None and not is_mcr:
            continue
        try:
            yield MarkedContentRef.from_object(item, page_obj)
        except StructureTreeError:
            continue


def _has_inherited_page_reference(elem: StructElem) -> bool:
    for item in _kid_items(elem.obj.get(Name.K)):
        if _as_int(item) is not None:
            return True
        if (
            isinstance(item, Dictionary)
            and isinstance(item.get(Name.Type), Name)
            and item.get(Name.Type) in (Name.MCR, Name.OBJR)
            and Name.Pg not in item
        ):
            return True
    return False


def _elements_including(tree: StructTree, elem: StructElem) -> Iterator[StructElem]:
    found = False
    for candidate in tree._walk_all():
        if _same_object(candidate.obj, elem.obj):
            found = True
        yield candidate
    if not found:
        yield elem


def _referenced_objects(elements: Iterable[StructElem]) -> Iterator[Object]:
    """Objects named by the ``/OBJR`` entries of *elements*."""
    for elem in elements:
        for item in _kid_items(elem.obj.get(Name.K)):
            if not isinstance(item, Dictionary) or not _is_name(
                item.get(Name.Type), Name.OBJR
            ):
                continue
            referent = item.get(Name.Obj)
            if isinstance(referent, Dictionary | Stream):
                yield referent


def _page_structure_containers(page: Page) -> Iterator[Object]:
    """Objects on *page* that may carry a structure key of their own."""
    annots = page.obj.get(Name.Annots)
    if isinstance(annots, Array):
        for annot in annots:
            if isinstance(annot, Dictionary):
                yield annot
    resources = _inherited_page_attribute(page, Name.Resources)
    yield from _form_xobjects(resources)


def _structure_key_containers(pdf: Pdf) -> Iterator[Object]:
    """Yield owned objects that can carry a structural-parent key."""
    candidates: Iterator[Object] = iter(pdf.objects)
    seen: set[tuple[int, int] | int] = set()
    for obj in candidates:
        if not isinstance(obj, Dictionary | Stream):
            continue
        identity: tuple[int, int] | int = obj.objgen if obj.is_indirect else id(obj)
        if identity not in seen:
            seen.add(identity)
            yield obj
    for page in pdf.pages:
        for obj in (page.obj, *_page_structure_containers(page)):
            identity = obj.objgen if obj.is_indirect else id(obj)
            if identity not in seen:
                seen.add(identity)
                yield obj


class MarkedContentRef:
    """A reference from a structure element to a marked-content sequence.

    In ``/K`` this is either a bare integer (a marked-content identifier in the
    element's own ``/Pg``) or a marked-content reference dictionary
    (``/Type /MCR``), which additionally names the page and, for content that
    does not live in a page's content stream, the stream that contains it.
    """

    def __init__(
        self,
        mcid: int,
        page: Object | None = None,
        *,
        stream: Object | None = None,
        stream_owner: Object | None = None,
        obj: Dictionary | None = None,
    ):
        """Initialize MarkedContentRef."""
        self.mcid = mcid
        self.page = page
        self.stream = stream
        self.stream_owner = stream_owner
        self.obj = obj

    @classmethod
    def from_object(cls, item: Object, default_page: Object | None) -> MarkedContentRef:
        """Parse a ``/K`` entry that refers to marked content."""
        mcid = _as_int(item)
        if mcid is not None:
            return cls(_validate_mcid(mcid), default_page)
        if not isinstance(item, Dictionary):
            raise TypeError(
                "Marked-content references must be an integer or Dictionary"
            )
        mcid = _as_int(item.get(Name.MCID))
        if mcid is None:
            raise StructureTreeError(
                "Marked content reference has no /MCID "
                f"({_safe_object_description(item)})"
            )
        return cls(
            mcid,
            item.get(Name.Pg, default_page),
            stream=item.get(Name.Stm),
            stream_owner=item.get(Name.StmOwn),
            obj=cast(Dictionary, item),
        )

    def to_object(self, default_page: Object | None) -> Object | int:
        """Build the ``/K`` entry for this reference.

        A bare integer is used when the reference needs no information beyond
        the marked-content identifier; otherwise an ``/MCR`` dictionary.
        """
        mcid = _validate_mcid(self.mcid)
        if self.page is not None and (
            not isinstance(self.page, Object) or not self.page.is_indirect
        ):
            raise ValueError("page must be an indirect object")
        if self.stream is not None:
            if not isinstance(self.stream, Stream):
                raise TypeError("stream must be a pikepdf.Stream")
            if not self.stream.is_indirect:
                raise ValueError("stream must be an indirect object")
        if self.stream_owner is not None:
            if (
                not isinstance(self.stream_owner, Object)
                or not self.stream_owner.is_indirect
            ):
                raise ValueError("stream_owner must be an indirect object")
            if self.stream is None:
                raise ValueError("stream_owner requires stream")
            if not _stream_owner_references_stream(self.stream_owner, self.stream):
                raise ValueError("stream_owner must reference stream")
        if self.stream is None and (
            self.page is None
            or (default_page is not None and _same_object(self.page, default_page))
        ):
            return mcid
        d = Dictionary(Type=Name.MCR, MCID=mcid)
        if self.page is not None:
            d.Pg = self.page
        if self.stream is not None:
            d.Stm = self.stream
        if self.stream_owner is not None:
            d.StmOwn = self.stream_owner
        return d

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, MarkedContentRef):
            return NotImplemented
        return (
            self.mcid == other.mcid
            and _same_object(self.page, other.page)
            and _same_object(self.stream, other.stream)
            and _same_object(self.stream_owner, other.stream_owner)
        )

    def __repr__(self):
        display_mcid = str(self.mcid) if type(self.mcid) is int else '<malformed>'
        return f'<pikepdf.MarkedContentRef: mcid={display_mcid}>'


class ObjectRef:
    """A reference from a structure element to a whole PDF object.

    Corresponds to an object reference dictionary (``/Type /OBJR``), used when
    the structural content item is an annotation or an XObject rather than a
    marked-content sequence.
    """

    def __init__(
        self,
        referent: Object,
        page: Object | None = None,
        *,
        obj: Dictionary | None = None,
    ):
        """Initialize ObjectRef."""
        self.referent = referent
        self.page = page
        self.obj = obj

    @classmethod
    def from_object(cls, item: Dictionary, default_page: Object | None) -> ObjectRef:
        """Parse an ``/OBJR`` dictionary."""
        if not isinstance(item, Dictionary):
            raise TypeError("Object references must be Dictionaries")
        referent = item.get(Name.Obj)
        if referent is None:
            raise StructureTreeError(
                f"Object reference has no /Obj ({_safe_object_description(item)})"
            )
        return cls(referent, item.get(Name.Pg, default_page), obj=item)

    def to_object(self, default_page: Object | None) -> Dictionary:
        """Build the ``/OBJR`` dictionary for this reference."""
        if not isinstance(self.referent, Object) or not self.referent.is_indirect:
            raise ValueError("referent must be an indirect object")
        if self.page is not None and (
            not isinstance(self.page, Object) or not self.page.is_indirect
        ):
            raise ValueError("page must be an indirect object")
        d = Dictionary(Type=Name.OBJR, Obj=self.referent)
        if self.page is not None and not _same_object(self.page, default_page):
            d.Pg = self.page
        return d

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, ObjectRef):
            return NotImplemented
        return _same_object(self.referent, other.referent) and _same_object(
            self.page, other.page
        )

    def __repr__(self):
        return f'<pikepdf.ObjectRef: {_safe_object_description(self.referent)}>'


class StructElem:
    """A structure element: one node of a PDF's logical structure tree.

    Structure elements are obtained from a :class:`StructTree`, either by
    walking an existing tree or by creating them with :meth:`StructTree.add`
    and :meth:`add_child`. Anything this class does not model is reachable
    through :attr:`obj`.

    Arguments:
        obj: The ``/StructElem`` dictionary this element wraps.
        tree: The structure tree the element belongs to.
    """

    def __init__(self, obj: Dictionary, tree: StructTree):
        """Initialize StructElem."""
        if not isinstance(obj, Dictionary):
            raise TypeError("StructElem must wrap a Dictionary")
        self.obj = obj
        self._tree = tree

    @property
    def tree(self) -> StructTree:
        """The structure tree this element belongs to."""
        return self._tree

    @property
    def _lock_pdf(self) -> Pdf:
        return self._tree.pdf

    def _reader_problem(self, message: str) -> None:
        """Report a defect found while reading.

        Readers are lenient by default, matching :class:`pikepdf.Outline`:
        a damaged document yields ``None`` rather than an exception, so a
        malformed file can still be inspected and repaired. Constructing the
        tree with ``strict=True`` turns these into
        :exc:`pikepdf.StructureTreeError` instead.

        Writers are unaffected: a mutation always validates what it touches,
        because writing into a structure that is already inconsistent makes it
        worse rather than better.
        """
        if self._tree._strict:
            raise StructureTreeError(message)
        return None

    def _walk_ancestry(self) -> bool:
        """Verify the ancestry chain and report whether it reaches the root.

        Each hop must be claimed exactly once by the parent its ``/P`` names;
        anything else is corruption and raises. An element with no ``/P`` is
        detached -- free-floating, not yet attached or already removed -- and
        is reported as such rather than rejected.

        Claim lookups are memoized per parent, so this costs time proportional
        to the element's depth rather than to the size of the tree.
        """
        root = self._tree.obj
        current = self.obj
        seen: set[_ObjectIdentity] = set()
        while True:
            identity = _object_identity(current)
            if identity in seen:
                raise StructureTreeError("Structure element ancestry contains a cycle")
            seen.add(identity)
            parent = current.get(Name.P)
            if parent is None:
                return False
            if not isinstance(parent, Dictionary):
                raise StructureTreeError("Structure element /P must be a dictionary")
            claims = self._tree._claims_for(parent)
            occurrences = claims.get(_object_identity(current), 0)
            if occurrences == 0:
                raise StructureTreeError(
                    "Structure element is not attached uniquely to this structure "
                    "tree: its /P is not the element whose /K contains it"
                )
            if occurrences > 1:
                raise StructureTreeError(
                    "Structure element is not attached uniquely to this structure "
                    "tree: its parent claims it more than once"
                )
            if _same_object(parent, root):
                return True
            if not _is_struct_elem(parent):
                return False
            _require_owned_indirect(parent, self._tree.pdf, "Structure element parent")
            current = parent

    def _require_owned(self) -> None:
        """Require that this element may be edited in place.

        Checks what a local write can break: the element is an indirect object
        owned by this ``Pdf``, its tree exists, and its ancestry is consistent.
        A detached element -- one with no ``/P``, such as a subtree being built
        before it is attached, or an element that has been removed -- may still
        be edited, so that it can be prepared or repaired and attached later.

        Writes that touch the document-global parent tree require
        :meth:`_require_attached` instead. Whole-tree properties are reported
        by :meth:`StructTree.validate`, not re-proved on every write.
        """
        if not self.obj.is_indirect:
            raise StructureTreeError(
                "Direct structure elements are read-only; mutation requires "
                "an indirect structure element"
            )
        _require_owned_indirect(self.obj, self._tree.pdf, "Structure element")
        if not self._tree.exists:
            raise StructureTreeError(
                "Structure element is not attached to this structure tree"
            )
        self._walk_ancestry()

    def _require_attached(self) -> None:
        """Require that this element is reachable from the structure tree root.

        Used by operations that write into the parent tree, which indexes the
        document as a whole: registering content against a detached element
        would leave the parent tree pointing at something no reader can reach.
        """
        self._require_owned()
        if not self._walk_ancestry():
            raise StructureTreeError(
                "Structure element is not attached to this structure tree"
            )

    @property
    def tag(self) -> Name:
        """The structure type (``/S``), e.g. ``Name.P`` or ``Name.H1``."""
        tag = self.obj.get(Name.S)
        if tag is None:
            raise StructureTreeError("Structure element is missing required /S")
        if not isinstance(tag, Name):
            raise StructureTreeError("Structure element /S must be a pikepdf.Name")
        return tag

    @tag.setter
    @_locked
    def tag(self, value: Name) -> None:
        if not isinstance(value, Name):
            raise TypeError("Structure type must be a pikepdf.Name")
        self._require_owned()
        self.obj.S = value

    @property
    def parent(self) -> StructElem | None:
        """The parent structure element (``/P``), or ``None`` at the top level."""
        if Name.P not in self.obj:
            self._reader_problem("Structure element is missing required /P")
            return None
        parent = self.obj.get(Name.P)
        if not isinstance(parent, Dictionary) or isinstance(parent, Stream):
            self._reader_problem("Structure element /P must be a dictionary")
            return None
        if not parent.is_indirect:
            self._reader_problem("Structure element /P must be an indirect object")
            return None
        if not parent.same_owner_as(self._tree.pdf.Root):
            self._reader_problem("Structure element /P belongs to another PDF")
            return None
        if _is_name(parent.get(Name.Type), Name.StructTreeRoot):
            if not _same_object(parent, self._tree.obj):
                self._reader_problem(
                    "Structure element /P belongs to another structure tree"
                )
                return None
            return None
        if not _is_struct_elem(parent):
            self._reader_problem(
                "Structure element /P is not a structure element or tree root"
            )
            return None
        result = StructElem(parent, self._tree)
        try:
            result._require_owned()
        except StructureTreeError:
            self._reader_problem(
                "Structure element /P belongs to another structure tree"
            )
            return None
        return result

    @property
    def page(self) -> Page | None:
        """The effective page, inherited from an ancestor when necessary."""
        try:
            pg = _strict_effective_page_obj(self.obj, self._tree)
            if pg is None:
                return None
            return Page(_require_page(pg, self._tree.pdf))
        except (TypeError, ValueError, StructureTreeError) as error:
            self._reader_problem(
                f"Structure element has an invalid effective /Pg: {error}"
            )
            return None

    @page.setter
    @_locked
    def page(self, value: Page | Object | None) -> None:
        self._require_owned()
        page_obj = None if value is None else _require_page(value, self._tree.pdf)
        parent = self.obj.get(Name.P)
        inherited = (
            _effective_page_obj(cast(Dictionary, parent))
            if isinstance(parent, Dictionary) and _is_struct_elem(parent)
            else None
        )
        proposed = inherited if page_obj is None else page_obj
        pending: list[tuple[StructElem, Object | None]] = [(self, proposed)]
        seen: set[_ObjectIdentity] = set()
        while pending:
            elem, effective = pending.pop()
            identity = _object_identity(elem.obj)
            if identity in seen:
                continue
            seen.add(identity)
            if not _same_object(_effective_page_obj(elem.obj), effective) and (
                _has_inherited_page_reference(elem)
            ):
                raise StructureTreeError(
                    "Cannot change the effective page of existing content references"
                )
            for child in elem.children:
                explicit = child.obj.get(Name.Pg)
                child_page: Object | None
                if Name.Pg in child.obj:
                    child_page = _require_page(cast(Object, explicit), self._tree.pdf)
                else:
                    child_page = effective
                pending.append((child, child_page))
        if page_obj is None:
            if Name.Pg in self.obj:
                del self.obj[Name.Pg]
        else:
            self.obj.Pg = page_obj

    @property
    def alt(self) -> str | None:
        """Alternate description (``/Alt``), for content such as an image."""
        return self._get_text(Name.Alt)

    @alt.setter
    @_locked
    def alt(self, value: str | None) -> None:
        self._set_text(Name.Alt, value)

    @property
    def actual_text(self) -> str | None:
        """Replacement text (``/ActualText``) for this element's content."""
        return self._get_text(Name.ActualText)

    @actual_text.setter
    @_locked
    def actual_text(self, value: str | None) -> None:
        self._set_text(Name.ActualText, value)

    @property
    def expansion(self) -> str | None:
        """Expansion (``/E``) of an abbreviation or acronym."""
        return self._get_text(Name.E)

    @expansion.setter
    @_locked
    def expansion(self, value: str | None) -> None:
        self._set_text(Name.E, value)

    @property
    def lang(self) -> str | None:
        """Language (``/Lang``) of this element's content, e.g. ``'en-US'``."""
        return self._get_text(Name.Lang)

    @lang.setter
    @_locked
    def lang(self, value: str | None) -> None:
        self._set_text(Name.Lang, value)

    @property
    def title(self) -> str | None:
        """Human-readable title (``/T``) of this element."""
        return self._get_text(Name.T)

    @title.setter
    @_locked
    def title(self, value: str | None) -> None:
        self._set_text(Name.T, value)

    @property
    def element_id(self) -> str | bytes | None:
        """Identifier (``/ID``) of this element within the document's ID tree.

        A text value is returned when converting it back to a PDF string
        preserves its exact bytes. Otherwise, the original bytes are returned.
        """
        if Name.ID not in self.obj:
            return None
        value = self.obj.get(Name.ID)
        if not isinstance(value, String):
            raise StructureTreeError("Structure element /ID must be a string")
        raw_value = bytes(value)
        text_value = str(value)
        return text_value if bytes(String(text_value)) == raw_value else raw_value

    @element_id.setter
    @_locked
    def element_id(self, value: str | bytes | None) -> None:
        if value is not None and not isinstance(value, str | bytes):
            raise TypeError("element_id must be a str, bytes, or None")
        self._require_owned()
        tree = self._tree
        current_entries, _ = tree._id_entries_for_mutation()
        raw_value = None if value is None else bytes(String(value))
        entries = tree._reachable_id_entries(replacement=(self.obj, raw_value))
        old_value = self.obj.get(Name.ID)
        old_raw = bytes(old_value) if isinstance(old_value, String) else None
        if old_raw == raw_value and tree._same_id_entries(current_entries, entries):
            return

        replacement_tree = tree._build_id_tree(entries) if entries else None
        if raw_value is None:
            if Name.ID in self.obj:
                del self.obj[Name.ID]
        else:
            self.obj.ID = String(raw_value)
        if replacement_tree is None:
            if Name.IDTree in tree.obj:
                del tree.obj[Name.IDTree]
        else:
            tree.obj.IDTree = replacement_tree

    @property
    def attributes(self) -> Object | None:
        """Attribute dictionaries or arrays (``/A``) attached to this element."""
        return self.obj.get(Name.A)

    @attributes.setter
    @_locked
    def attributes(self, value: Object | None) -> None:
        self._require_owned()
        if value is None:
            if Name.A in self.obj:
                del self.obj[Name.A]
        else:
            _require_attributes(value, self._tree.pdf)
            self.obj.A = value

    @property
    def namespace(self) -> Object | None:
        """The registered PDF 2.0 namespace dictionary (``/NS``)."""
        return self.obj.get(Name.NS)

    @namespace.setter
    @_locked
    def namespace(self, value: Object | None) -> None:
        self._require_owned()
        if value is None:
            if Name.NS in self.obj:
                del self.obj[Name.NS]
            return
        namespace = _require_namespace(value, self._tree.pdf)
        root = self._tree.obj
        raw_namespaces = root.get(Name.Namespaces)
        if Name.Namespaces in root:
            if not isinstance(raw_namespaces, Array):
                raise StructureTreeError("/Namespaces must be an array")
            for item in raw_namespaces:
                try:
                    _require_namespace(item, self._tree.pdf)
                except (TypeError, StructureTreeError) as exc:
                    raise StructureTreeError(
                        "/Namespaces contains an invalid namespace dictionary"
                    ) from exc
            namespaces = raw_namespaces
        else:
            namespaces = Array([])
        if not any(_same_object(item, namespace) for item in namespaces):
            namespaces.append(namespace)
        if Name.Namespaces not in root:
            root.Namespaces = namespaces
        self.obj.NS = namespace

    def _get_text(self, key: Name) -> str | None:
        if key not in self.obj:
            return None
        value = self.obj.get(key)
        if not isinstance(value, String):
            raise StructureTreeError(f"Structure element {key} must be a text string")
        return str(value)

    def _set_text(self, key: Name, value: str | None) -> None:
        if value is not None and not isinstance(value, str):
            raise TypeError("Structure text values must be str or None")
        self._require_owned()
        if value is None:
            if key in self.obj:
                del self.obj[key]
        else:
            self.obj[key] = String(value)

    @property
    def kids(self) -> list[StructElem | MarkedContentRef | ObjectRef]:
        """Every child of this element, in order.

        Children may be nested structure elements, marked-content references,
        or object references.
        """
        page_obj = _effective_page_obj(self.obj)
        result: list[StructElem | MarkedContentRef | ObjectRef] = []
        for item in _kid_items(self.obj.get(Name.K)):
            result.append(self._wrap_kid(item, page_obj))
        return result

    def _wrap_kid(
        self, item: Object, page_obj: Object | None
    ) -> StructElem | MarkedContentRef | ObjectRef:
        mcid = _as_int(item)
        if mcid is not None:
            if mcid < 0:
                raise StructureTreeError(
                    "Marked content identifiers in /K must be non-negative"
                )
            return MarkedContentRef.from_object(item, page_obj)
        if not isinstance(item, Dictionary):
            raise StructureTreeError(
                f"Unexpected object ({_safe_object_description(item)}) in /K"
            )
        item_type = item.get(Name.Type)
        if item_type is not None and not isinstance(item_type, Name):
            raise StructureTreeError("Unexpected dictionary /Type in /K")
        if _is_name(item_type, Name.MCR):
            marked_ref = MarkedContentRef.from_object(item, page_obj)
            if marked_ref.mcid < 0:
                raise StructureTreeError(
                    "Marked content identifiers in /K must be non-negative"
                )
            if marked_ref.stream is not None and not isinstance(
                marked_ref.stream, Stream
            ):
                raise StructureTreeError(
                    "Marked content reference /Stm must be a stream"
                )
            if marked_ref.stream_owner is not None and marked_ref.stream is None:
                raise StructureTreeError(
                    "Marked content reference /StmOwn requires /Stm"
                )
            return marked_ref
        if _is_name(item_type, Name.OBJR):
            object_ref = ObjectRef.from_object(item, page_obj)
            if not isinstance(object_ref.referent, Dictionary | Stream):
                raise StructureTreeError(
                    "Object reference /Obj must be a dictionary or stream"
                )
            return object_ref
        if _is_struct_elem(item):
            return StructElem(item, self._tree)
        raise StructureTreeError("Unexpected dictionary type in /K")

    @property
    def children(self) -> list[StructElem]:
        """The child structure elements, excluding content references."""
        return [kid for kid in self.kids if isinstance(kid, StructElem)]

    def _child_elements(self) -> list[StructElem]:
        """Child elements, skipping anything malformed rather than raising.

        Internal traversals must keep working on a damaged tree so that
        :meth:`StructTree.validate` can report the damage and
        :meth:`remove` can still clean up.
        """
        return [
            StructElem(cast(Dictionary, item), self._tree)
            for item in _kid_items(self.obj.get(Name.K))
            if _is_struct_elem(item)
        ]

    def _kid_count(self) -> int:
        existing = self.obj.get(Name.K)
        if existing is None:
            return 0
        return len(existing) if isinstance(existing, Array) else 1

    def _preflight_append_kid(self, *, _check_structure: bool = True) -> None:
        """Validate this element's existing ``/K`` before appending to it.

        The scan is proportional to the number of entries already present, so
        it is memoized per element: appending many children validates the
        existing entries once rather than on every append. Appends made
        through this API record the entry they added, and any raw edit that
        changes the length of ``/K`` re-triggers the scan.

        The memo is keyed on that length, so replacing an entry in place
        without changing it is not noticed here and the append is allowed.
        That is a deliberate trade: re-deriving the whole invariant on every
        write made bulk tagging quadratic, and
        :meth:`StructTree.validate` reports the defect either way.
        """
        if _check_structure:
            self._require_owned()
        checked = self._tree._checked_kids
        identity = _object_identity(self.obj)
        count = self._kid_count()
        if checked.get(identity) == count:
            return
        self._validate_existing_kids()
        checked[identity] = count

    def _validate_existing_kids(self) -> None:
        if Name.K not in self.obj:
            return
        existing = self.obj.get(Name.K)
        if existing is None:
            raise StructureTreeError("Structure element /K is null")
        default_page = _effective_page_obj(self.obj)
        content_refs: list[tuple[Object, int, Object]] = []
        object_refs: list[tuple[Object, Object]] = []
        child_ids: set[_ObjectIdentity] = set()
        content_ids: set[tuple[_ObjectIdentity, int]] = set()
        object_ids: set[tuple[_ObjectIdentity, _ObjectIdentity]] = set()
        stream_pages: dict[_ObjectIdentity, set[_ObjectIdentity]] = {}
        for item in _kid_items(existing):
            mcid = _as_int(item)
            if mcid is not None:
                ref = MarkedContentRef(mcid, default_page)
            elif isinstance(item, Dictionary):
                item_type = item.get(Name.Type)
                if item_type is not None and not isinstance(item_type, Name):
                    raise StructureTreeError("Existing /K entry has a non-name /Type")
                if _is_name(item_type, Name.MCR):
                    ref = MarkedContentRef.from_object(item, default_page)
                elif _is_name(item_type, Name.OBJR):
                    object_ref = ObjectRef.from_object(item, default_page)
                    try:
                        if object_ref.page is None:
                            raise StructureTreeError("Existing /OBJR has no /Pg")
                        referent = _require_referent(
                            object_ref.referent, self._tree.pdf
                        )
                        ref_page = _require_page(object_ref.page, self._tree.pdf)
                    except (TypeError, StructureTreeError) as exc:
                        raise StructureTreeError(
                            "Existing /OBJR has an invalid /Obj or /Pg"
                        ) from exc
                    object_key = (
                        _object_identity(referent),
                        _object_identity(ref_page),
                    )
                    if object_key in object_ids:
                        raise StructureTreeError(
                            "Existing /K repeats an /OBJR on the same page"
                        )
                    object_ids.add(object_key)
                    object_refs.append((referent, ref_page))
                    continue
                elif _is_struct_elem(item):
                    parent = item.get(Name.P)
                    if not isinstance(parent, Dictionary) or not _same_object(
                        parent, self.obj
                    ):
                        raise StructureTreeError(
                            "Existing child /P does not name this structure element"
                        )
                    if item.is_indirect:
                        _require_owned_indirect(
                            item, self._tree.pdf, "Existing child structure element"
                        )
                        child_identity = _object_identity(item)
                        if child_identity in child_ids:
                            raise StructureTreeError(
                                "Existing /K repeats a child structure element"
                            )
                        child_ids.add(child_identity)
                    elif Name.K in item:
                        raise StructureTreeError(
                            "A direct structure element must be a terminal child"
                        )
                    continue
                else:
                    raise StructureTreeError(
                        "Existing /K contains an unexpected dictionary"
                    )
            else:
                raise StructureTreeError(
                    f"Existing /K contains {_safe_object_description(item)}"
                )

            try:
                mcid = _validate_mcid(ref.mcid)
                if ref.page is None:
                    raise StructureTreeError(
                        "Existing marked-content reference has no /Pg"
                    )
                ref_page = _require_page(ref.page, self._tree.pdf)
            except (TypeError, StructureTreeError, ValueError) as exc:
                raise StructureTreeError(
                    "Existing marked-content reference has an invalid /MCID or /Pg"
                ) from exc
            if ref.stream is None:
                container = ref_page
            else:
                try:
                    container = _require_stream(ref.stream, self._tree.pdf)
                except (TypeError, StructureTreeError) as exc:
                    raise StructureTreeError(
                        "Existing marked-content reference has an invalid /Stm"
                    ) from exc
                raw_resources = container.get(Name.Resources)
                if Name.Resources in container and not isinstance(
                    raw_resources, Dictionary
                ):
                    raise StructureTreeError(
                        "Existing Form XObject /Resources must be a dictionary"
                    )
                stream_pages.setdefault(_object_identity(container), set()).add(
                    _object_identity(ref_page)
                )
            if ref.stream_owner is not None:
                if ref.stream is None:
                    raise StructureTreeError("Existing /StmOwn requires /Stm")
                try:
                    owner = _require_owned_indirect(
                        ref.stream_owner,
                        self._tree.pdf,
                        "Existing marked-content stream owner",
                    )
                except (TypeError, StructureTreeError) as exc:
                    raise StructureTreeError(
                        "Existing marked-content reference has an invalid /StmOwn"
                    ) from exc
                if not _stream_owner_references_stream(
                    owner, cast(Stream, container), self._tree.pdf
                ):
                    raise StructureTreeError("Existing /StmOwn does not reference /Stm")
                if (
                    isinstance(owner, Dictionary)
                    and not isinstance(owner, Stream)
                    and (
                        _is_name(owner.get(Name.Type), Name.Annot)
                        or _is_page_annotation(self._tree.pdf, owner)
                    )
                    and _appearance_dictionary_references_stream(
                        owner, cast(Stream, container)
                    )
                    and not _page_has_annotation(ref_page, owner)
                ):
                    raise StructureTreeError(
                        "Existing annotation appearance /StmOwn is not on /Pg"
                    )
            content_key = (_object_identity(container), mcid)
            if content_key in content_ids:
                raise StructureTreeError(
                    "Existing /K repeats a marked-content identifier claim"
                )
            content_ids.add(content_key)
            content_refs.append((container, mcid, ref_page))

        if any(len(pages) > 1 for pages in stream_pages.values()):
            raise StructureTreeError(
                "Existing Form marked content is claimed on more than one page"
            )
        if content_refs:
            state = self._tree.parent_tree._content_check_state()
            for container, mcid, ref_page in content_refs:
                self._tree.parent_tree._check_content(
                    container,
                    mcid,
                    self,
                    page=ref_page,
                    allow_existing_claim=True,
                    _state=state,
                )
        for referent, ref_page in object_refs:
            self._tree.parent_tree._check_object(
                referent,
                self,
                page=ref_page,
                allow_existing_claim=True,
            )

    @property
    def content(self) -> list[MarkedContentRef]:
        """The marked-content references owned directly by this element."""
        return [kid for kid in self.kids if isinstance(kid, MarkedContentRef)]

    @_locked
    def add_child(
        self,
        tag: Name,
        *,
        page: Page | Object | None = None,
        alt: str | None = None,
        actual_text: str | None = None,
        expansion: str | None = None,
        lang: str | None = None,
        title: str | None = None,
        attributes: Object | None = None,
    ) -> StructElem:
        """Create a structure element and append it to this element's children.

        Arguments:
            tag: The structure type (``/S``) of the new element. Any name is
                accepted; if it is not a standard structure type, map it to one
                with :meth:`StructTree.add_role`.
            page: The page the new element's content appears on (``/Pg``).
            alt: Alternate description (``/Alt``).
            actual_text: Replacement text (``/ActualText``).
            expansion: Expansion of an abbreviation (``/E``).
            lang: Language of the content (``/Lang``).
            title: Human-readable title (``/T``).
            attributes: Attribute dictionaries or arrays (``/A``).

        Returns:
            The newly created :class:`StructElem`.
        """
        page_obj = self._tree._validate_element_arguments(
            tag,
            page,
            alt,
            actual_text,
            expansion,
            lang,
            title,
            attributes,
        )
        self._preflight_append_kid()
        elem = self._tree._new_element(
            self.obj,
            tag,
            page=page_obj,
            alt=alt,
            actual_text=actual_text,
            expansion=expansion,
            lang=lang,
            title=title,
            attributes=attributes,
        )
        self._append_kid(elem.obj, prechecked=True)
        return elem

    @_locked
    def add_content(
        self,
        page: Page | Object,
        mcid: int,
        *,
        stream: Object | None = None,
        stream_owner: Object | None = None,
    ) -> MarkedContentRef:
        """Attach a marked-content sequence on *page* to this element.

        Appends the reference to ``/K`` and records this element as the
        structural parent of the MCID in the document's parent tree. This
        creates ``/StructParents`` on the page for page content, or on the
        supplied stream for stream content such as a Form XObject.

        Arguments:
            page: The page on which the marked content is used. When *stream*
                is omitted, this page's content stream contains the sequence.
            mcid: The marked-content identifier, as written in the ``BDC``
                property list. Use :func:`next_mcid` or :class:`ContentMarker`
                to allocate one that does not collide.
            stream: The stream containing the sequence (``/Stm``), if it is not
                the page's own content stream.
            stream_owner: The indirect object that owns *stream* (``/StmOwn``),
                such as an annotation that owns an appearance stream.

        Returns:
            The newly created :class:`MarkedContentRef`.
        """
        mcid = _validate_mcid(mcid)
        self._require_attached()
        page_obj = _require_page(page, self._tree.pdf)
        stream_obj = None if stream is None else _require_stream(stream, self._tree.pdf)
        if (
            stream_obj is not None
            and Name.Resources in stream_obj
            and not isinstance(stream_obj.get(Name.Resources), Dictionary)
        ):
            raise StructureTreeError("Form XObject /Resources must be a dictionary")
        if stream_owner is not None and stream_obj is None:
            raise ValueError("stream_owner requires stream")
        stream_owner_obj = (
            None
            if stream_owner is None
            else _require_owned_indirect(
                stream_owner, self._tree.pdf, "Marked-content stream owner"
            )
        )
        if stream_owner_obj is not None and not _stream_owner_references_stream(
            stream_owner_obj, cast(Stream, stream_obj), self._tree.pdf
        ):
            raise StructureTreeError(
                "Marked-content stream owner does not reference stream"
            )
        if (
            stream_owner_obj is not None
            and isinstance(stream_owner_obj, Dictionary)
            and not isinstance(stream_owner_obj, Stream)
            and _appearance_dictionary_references_stream(
                stream_owner_obj, cast(Stream, stream_obj)
            )
            and (
                _is_name(stream_owner_obj.get(Name.Type), Name.Annot)
                or _is_page_annotation(self._tree.pdf, stream_owner_obj)
            )
            and not _page_has_annotation(page_obj, stream_owner_obj)
        ):
            raise StructureTreeError(
                "Annotation appearance stream owner is not on the claimed page"
            )
        if (
            stream_obj is not None
            and _is_name(stream_obj.get(Name.Subtype), Name.Form)
            and _observed_form_execution_count(self._tree.pdf, stream_obj) > 1
        ):
            raise StructureTreeError(
                "A Form XObject with internal marked content cannot be invoked "
                "more than once"
            )
        self._preflight_append_kid()
        container = page_obj if stream_obj is None else stream_obj
        parent_tree = self._tree.parent_tree
        state = parent_tree._content_check_state()
        state.validated_containers.add(_object_identity(container))
        parent_tree._check_content(
            container,
            mcid,
            self,
            page=page_obj,
            _state=state,
        )
        return self._add_content_prechecked(
            page_obj,
            mcid,
            stream_obj=stream_obj,
            stream_owner_obj=stream_owner_obj,
            state=state,
            prechecked_k=True,
        )

    def _add_content_prechecked(
        self,
        page_obj: Object,
        mcid: int,
        *,
        stream_obj: Stream | None,
        stream_owner_obj: Object | None = None,
        state: _ContentCheckState,
        prechecked_k: bool = False,
    ) -> MarkedContentRef:
        container = page_obj if stream_obj is None else stream_obj
        ref = MarkedContentRef(
            mcid,
            page_obj,
            stream=stream_obj,
            stream_owner=stream_owner_obj,
        )
        kid = ref.to_object(_effective_page_obj(self.obj))
        self._append_kid(kid, prechecked=prechecked_k)
        if isinstance(kid, Dictionary):
            ref.obj = kid
        self._tree.parent_tree._register_content(container, mcid, self, state)
        state.claims.setdefault((_object_identity(container), mcid), []).append(self)
        state.claim_pages.setdefault(_object_identity(container), set()).add(
            _object_identity(page_obj)
        )
        return ref

    @_locked
    def add_object(self, referent: Object, page: Page | Object) -> ObjectRef:
        """Attach a whole object, such as an annotation, to this element.

        Appends an ``/OBJR`` entry to ``/K``, sets ``/StructParent`` on
        *referent*, and records this element as its structural parent.

        Arguments:
            referent: The annotation or XObject to reference.
            page: The page the object appears on.

        Returns:
            The newly created :class:`ObjectRef`.
        """
        self._require_attached()
        page_obj = _require_page(page, self._tree.pdf)
        referent = _require_referent(referent, self._tree.pdf)
        self._preflight_append_kid()
        self._tree.parent_tree._check_object(referent, self, page=page_obj)
        if (
            isinstance(referent, Dictionary)
            and not isinstance(referent, Stream)
            and (
                _is_name(referent.get(Name.Type), Name.Annot)
                or _is_page_annotation(self._tree.pdf, referent)
            )
        ):
            annots = page_obj.get(Name.Annots)
            if Name.Annots in page_obj and not isinstance(annots, Array):
                raise StructureTreeError("Page /Annots must be an array")
            if not _page_has_annotation(page_obj, referent):
                raise StructureTreeError(
                    "Annotation object reference is not on the claimed page"
                )
        ref = ObjectRef(referent, page_obj)
        kid = ref.to_object(_effective_page_obj(self.obj))
        self._append_kid(kid, prechecked=True)
        ref.obj = kid
        self._tree.parent_tree._register_object(referent, self)
        return ref

    def _append_kid(self, item: Object | int, *, prechecked: bool = False) -> None:
        if not prechecked:
            self._preflight_append_kid()
        existing = self.obj.get(Name.K)
        if existing is None:
            self.obj.K = Array([item])
        elif isinstance(existing, Array):
            existing.append(item)
        else:
            self.obj.K = Array([existing, item])
        identity = _object_identity(self.obj)
        if identity in self._tree._checked_kids:
            self._tree._checked_kids[identity] = self._kid_count()
        self._tree._record_claim(self.obj, item)

    @_locked
    def attach_child(self, elem: StructElem) -> StructElem:
        """Attach a detached structure element as a child of this element.

        The counterpart of :meth:`remove`: a subtree may be built or repaired
        while detached and then spliced into the tree. Every marked-content
        and object reference in the attached subtree is re-registered in the
        parent tree, so the reverse mapping is restored along with the link.

        Arguments:
            elem: A detached element -- one with no ``/P``, either newly built
                or previously removed -- belonging to this tree's ``Pdf``.

        Returns:
            *elem*, now attached.

        Raises:
            StructureTreeError: If *elem* is already attached, belongs to
                another PDF, or attaching it would create a cycle.
        """
        self._require_attached()
        self._tree._preflight_attach(elem, self.obj)
        with self._tree.pdf.lock():
            elem.obj.P = self.obj
            self._append_kid(elem.obj)
            self._tree._register_subtree(elem)
        return elem

    @_locked
    def remove(self) -> None:
        """Remove this element and its descendants from the structure tree.

        Detaches the element from its parent's ``/K`` and clears every parent
        tree entry that pointed at the element or any of its descendants.
        """
        self._require_attached()
        removed = list(self._tree._walk_from(self, None))
        parent_tree = self._tree.parent_tree
        parent_plan = parent_tree._preflight_unregister_subtree(removed)
        id_plan = self._tree._preflight_remove_element_ids(removed)
        parent = self.obj.get(Name.P)
        if isinstance(parent, Dictionary) and Name.K in parent:
            kids = parent.K
            if isinstance(kids, Array):
                remaining = Array([k for k in kids if not self._is_self(k)])
                if len(remaining) == 0:
                    del parent[Name.K]
                else:
                    parent.K = remaining
            elif self._is_self(kids):
                del parent[Name.K]
            self._tree._invalidate_claims(parent)
        # A removed element keeps no parent link: a stale /P would name an
        # element that no longer claims it, which is corruption rather than
        # detachment. Clearing it leaves the subtree free-floating, so it can
        # be edited and attached again.
        if Name.P in self.obj:
            del self.obj[Name.P]
        parent_tree._unregister_subtree(parent_plan)
        self._tree._remove_element_ids(id_plan)

    def _is_self(self, item: Object) -> bool:
        return isinstance(item, Dictionary) and _same_object(item, self.obj)

    def walk(self) -> Iterator[StructElem]:
        """Iterate this element and all its descendants, depth first."""
        yield from self._tree._walk_from(self, self._tree._max_depth)

    def __iter__(self) -> Iterator[StructElem]:
        return iter(self.children)

    def __len__(self) -> int:
        return len(self.children)

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, StructElem):
            return NotImplemented
        return _same_object(self.obj, other.obj)

    def __repr__(self):
        tag = self.obj.get(Name.S)
        display_tag = str(tag) if isinstance(tag, Name) else '<malformed tag>'
        child_count = len(self._child_elements())
        return f'<pikepdf.StructElem: {display_tag} with {child_count} children>'


class ParentTree:
    """The structural parent tree, which maps content back to its element.

    A number tree ({{ pdfrm }} 14.7.4.4) keyed by the ``/StructParents`` entry
    of a page or content stream -- whose value is an array indexed by
    marked-content identifier -- or by the ``/StructParent`` entry of an
    annotation or XObject, whose value is a single structure element.

    Obtain this from :attr:`StructTree.parent_tree`.
    """

    def __init__(self, tree: StructTree):
        """Initialize ParentTree."""
        self._tree = tree

    @property
    def _lock_pdf(self) -> Pdf:
        return self._tree.pdf

    @property
    def obj(self) -> Dictionary:
        """The number tree's root dictionary (``/ParentTree``)."""
        root = self._tree.obj
        existing = root.get(Name.ParentTree)
        if existing is None:
            existing = NumberTree.new(self._tree.pdf).obj
            root.ParentTree = existing
        if not isinstance(existing, Dictionary):
            raise StructureTreeError("/ParentTree must be a dictionary")
        return existing

    @property
    def number_tree(self) -> NumberTree:
        """The parent tree as a :class:`pikepdf.NumberTree`."""
        return NumberTree(self.obj)

    def _existing_number_tree(self) -> NumberTree | None:
        """Return the existing parent tree without creating one."""
        root = self._tree.obj
        if Name.ParentTree not in root:
            return None
        existing = root.get(Name.ParentTree)
        if not isinstance(existing, Dictionary):
            raise StructureTreeError("/ParentTree must be a dictionary")
        try:
            number_tree = NumberTree(existing)
            list(number_tree.keys())
        except Exception as exc:
            raise StructureTreeError("/ParentTree is not a valid number tree") from exc
        return number_tree

    @staticmethod
    def _number_tree_keys(number_tree: NumberTree | None) -> set[int]:
        return set() if number_tree is None else set(number_tree.keys())

    @property
    def next_key(self) -> int:
        """The next unused key (``/ParentTreeNextKey``)."""
        root = self._tree.obj
        if Name.ParentTreeNextKey not in root:
            return 0
        value = _as_int(root.get(Name.ParentTreeNextKey))
        if value is None:
            raise StructureTreeError("/ParentTreeNextKey must be an integer")
        return value

    @next_key.setter
    @_locked
    def next_key(self, value: int) -> None:
        value = _validate_integer(value, "Parent tree keys")
        used = self._number_tree_keys(self._existing_number_tree())
        used.update(self._key_users())
        if used and value <= max(used):
            raise ValueError(
                "/ParentTreeNextKey must be greater than every used parent tree key"
            )
        self._tree.obj.ParentTreeNextKey = value

    @_locked
    def allocate_key(
        self,
        *,
        _key_users: dict[int, list[tuple[Object, Name]]] | None = None,
    ) -> int:
        """Reserve and return an unused parent tree key."""
        key = self._next_available_key(_key_users)
        self.next_key = key + 1
        return key

    def _key_users(self) -> dict[int, list[tuple[Object, Name]]]:
        users: dict[int, list[tuple[Object, Name]]] = {}
        for container in _structure_key_containers(self._tree.pdf):
            for name in (Name.StructParent, Name.StructParents):
                key = _as_int(container.get(name))
                if key is not None:
                    users.setdefault(key, []).append((container, name))
        return users

    def _content_check_state(self) -> _ContentCheckState:
        _ = self.next_key
        elements = list(self._tree._walk_all())
        claims: dict[tuple[_ObjectIdentity, int], list[StructElem]] = {}
        claim_pages: dict[_ObjectIdentity, set[_ObjectIdentity]] = {}
        for claimant in elements:
            for ref in _content_references(claimant):
                container = ref.stream if ref.stream is not None else ref.page
                if isinstance(container, Object):
                    container_identity = _object_identity(container)
                    claims.setdefault((container_identity, ref.mcid), []).append(
                        claimant
                    )
                    if isinstance(ref.page, Object):
                        claim_pages.setdefault(container_identity, set()).add(
                            _object_identity(ref.page)
                        )
        key_users = self._key_users()
        number_tree = self._existing_number_tree()
        parent_tree_keys = self._number_tree_keys(number_tree)
        used_keys = parent_tree_keys | set(key_users)
        next_available_key = max(
            0,
            self.next_key,
            max(used_keys, default=-1) + 1,
        )
        while next_available_key in used_keys:
            next_available_key += 1
        return _ContentCheckState(
            key_users=key_users,
            claims=claims,
            claim_pages=claim_pages,
            attached={_object_identity(elem.obj) for elem in elements},
            validated_containers=set(),
            number_tree=number_tree,
            parent_tree_keys=parent_tree_keys,
            next_available_key=next_available_key,
            prospective_keys={},
        )

    @staticmethod
    def _reserve_key(container: Object, state: _ContentCheckState) -> int:
        identity = _object_identity(container)
        existing = state.prospective_keys.get(identity)
        if existing is not None:
            return existing
        key = state.next_available_key
        used = (
            state.parent_tree_keys
            | set(state.key_users)
            | set(state.prospective_keys.values())
        )
        while key in used:
            key += 1
        state.prospective_keys[identity] = key
        state.next_available_key = key + 1
        return key

    def _next_available_key(
        self,
        key_users: dict[int, list[tuple[Object, Name]]] | None = None,
    ) -> int:
        used = self._number_tree_keys(self._existing_number_tree())
        if key_users is None:
            key_users = self._key_users()
        used.update(key_users)
        key = max(0, self.next_key, max(used, default=-1) + 1)
        while key in used:
            key += 1
        return key

    @staticmethod
    def _check_key_owner(
        container: Object,
        key: int,
        key_users: dict[int, list[tuple[Object, Name]]],
        key_name: Name,
    ) -> None:
        if any(
            not _same_object(other, container) for other, _ in key_users.get(key, [])
        ):
            raise StructureTreeError(
                f"{key_name} {key} is already used by another object"
            )

    def __contains__(self, key: object) -> bool:
        if isinstance(key, bool) or not isinstance(key, int):
            return False
        number_tree = self._existing_number_tree()
        return number_tree is not None and key in number_tree

    def __getitem__(self, key: int) -> Object:
        key = _validate_integer(key, "Parent tree keys")
        number_tree = self._existing_number_tree()
        if number_tree is None:
            raise KeyError(key)
        try:
            return number_tree[key]
        except (IndexError, KeyError) as exc:
            raise KeyError(key) from exc

    @_locked
    def __setitem__(self, key: int, value: Object) -> None:
        """Set a raw parent-tree entry.

        This low-level mapping operation does not create or validate matching
        structure-element ``/K`` references. Callers own that consistency and
        should run :meth:`StructTree.validate` after editing raw entries.
        """
        key = _validate_integer(key, "Parent tree keys")
        current_next_key = self.next_key
        self.number_tree[key] = value
        used = self._number_tree_keys(self._existing_number_tree())
        used.update(self._key_users())
        required_next_key = max(current_next_key, max(used) + 1)
        if required_next_key != current_next_key:
            self.next_key = required_next_key

    def keys(self) -> list[int]:
        """Every key present in the parent tree, in ascending order."""
        return sorted(self._number_tree_keys(self._existing_number_tree()))

    def key_for_page(
        self,
        page: Page | Object,
        *,
        create: bool = False,
        _state: _ContentCheckState | None = None,
    ) -> int | None:
        """Return the ``/StructParents`` key of *page*.

        Arguments:
            page: The page to look up, or a content stream that carries its own
                ``/StructParents``, such as a form XObject.
            create: If ``True``, assign the page a key and an empty parent tree
                entry when it does not already have one.
        """
        raw_container = _as_page_obj(page)
        assert raw_container is not None
        if (
            _state is not None
            and _object_identity(raw_container) in _state.validated_containers
        ):
            container = raw_container
        else:
            container = _require_content_container(page, self._tree.pdf)
            if _state is not None:
                _state.validated_containers.add(_object_identity(container))
        if create and Name.StructParent in container:
            raise StructureTreeError(
                "A content container cannot also have /StructParent"
            )
        raw_key = container.get(Name.StructParents)
        key = _as_int(raw_key)
        if Name.StructParents in container:
            if key is None:
                raise StructureTreeError("/StructParents must be an integer")
            key_users = self._key_users() if _state is None else _state.key_users
            self._check_key_owner(container, key, key_users, Name.StructParents)
            key_exists = (
                key in self if _state is None else key in _state.parent_tree_keys
            )
            if create and not key_exists:
                raise StructureTreeError(
                    f"/StructParents {key} has no corresponding parent tree entry"
                )
            return key
        if not create:
            return None
        key_users = self._key_users() if _state is None else _state.key_users
        if _state is None:
            key = self.allocate_key(_key_users=key_users)
        else:
            key = self._reserve_key(container, _state)
            if key >= self.next_key:
                self.next_key = key + 1
        container.StructParents = key
        if not any(
            _same_object(owner, container) and name == Name.StructParents
            for owner, name in key_users.get(key, [])
        ):
            key_users.setdefault(key, []).append((container, Name.StructParents))
        self[key] = self._tree.pdf.make_indirect(Array([]))
        if _state is not None:
            _state.number_tree = self._existing_number_tree()
            _state.parent_tree_keys.add(key)
        return key

    def entry_for_page(self, page: Page | Object) -> Array | None:
        """Return the array of structural parents for *page*, by MCID."""
        key = self.key_for_page(page)
        if key is None:
            return None
        if key not in self:
            raise StructureTreeError(
                f"/StructParents {key} has no corresponding parent tree entry"
            )
        entry = self[key]
        if not isinstance(entry, Array):
            raise StructureTreeError(
                f"Parent tree entry {key} for /StructParents must be an array"
            )
        return entry

    def _check_content(
        self,
        container: Object,
        mcid: int,
        elem: StructElem,
        *,
        page: Object | None = None,
        allow_existing_claim: bool = False,
        _state: _ContentCheckState | None = None,
    ) -> None:
        """Reject a content registration before anything has been mutated."""
        mcid = _validate_mcid(mcid)
        if (
            _state is None
            or _object_identity(container) not in _state.validated_containers
        ):
            container = _require_content_container(container, self._tree.pdf)
            if _state is not None:
                _state.validated_containers.add(_object_identity(container))
        if _state is None:
            elem._require_owned()
            _state = self._content_check_state()
        elif _object_identity(elem.obj) not in _state.attached:
            elem._require_owned()
        if Name.StructParent in container:
            raise StructureTreeError(
                "A content container cannot also have /StructParent"
            )
        if (
            isinstance(container, Stream)
            and page is not None
            and _state.claim_pages.get(_object_identity(container), set())
            - {_object_identity(page)}
        ):
            raise StructureTreeError(
                "A Form XObject with internal marked content cannot be "
                "claimed on more than one page"
            )
        claims = _state.claims.get((_object_identity(container), mcid), [])
        same_owner = bool(claims) and all(
            _same_object(claim.obj, elem.obj) for claim in claims
        )
        repair = allow_existing_claim and len(claims) == 1 and same_owner
        if claims and not repair:
            owner = "this" if same_owner else "another"
            raise StructureTreeError(
                f"Marked content identifier {mcid} is already claimed by "
                f"{owner} structure element"
            )
        if page is not None:
            container_identity = _object_identity(container)
            prospective_claims = {
                claimed_mcid
                for (claim_container, claimed_mcid), owners in _state.claims.items()
                if claim_container == container_identity and owners
            }
            prospective_claims.add(mcid)
            if isinstance(container, Stream):
                raw_resources = container.get(Name.Resources)
                resources = (
                    raw_resources
                    if isinstance(raw_resources, Dictionary)
                    else _inherited_page_attribute(page, Name.Resources)
                )
                source: Page | Object = container
            else:
                resources = _inherited_page_attribute(page, Name.Resources)
                source = Page(page)
            if _claims_create_structural_nesting(
                source,
                resources,
                prospective_claims,
            ):
                raise StructureTreeError(
                    "Structural marked-content claims must not be nested"
                )
        raw_key = container.get(Name.StructParents)
        if Name.StructParents not in container:
            self._reserve_key(container, _state)
            return
        key = _as_int(raw_key)
        if key is None:
            raise StructureTreeError("/StructParents must be an integer")
        self._check_key_owner(container, key, _state.key_users, Name.StructParents)
        if key not in _state.parent_tree_keys:
            raise StructureTreeError(
                f"/StructParents {key} has no corresponding parent tree entry"
            )
        assert _state.number_tree is not None
        entry = _state.number_tree[key]
        if not isinstance(entry, Array):
            raise StructureTreeError(
                f"Parent tree entry {key} is not an array "
                f"({_safe_object_description(entry)})"
            )
        if mcid >= len(entry) or entry[mcid] is None:
            return
        if isinstance(entry[mcid], Dictionary):
            if repair and _same_object(entry[mcid], elem.obj):
                return
            owner = "this" if _same_object(entry[mcid], elem.obj) else "another"
            raise StructureTreeError(
                f"Marked content identifier {mcid} is already claimed by "
                f"{owner} structure element"
            )
        raise StructureTreeError(
            f"Parent tree entry {key}[{mcid}] is not a structure element"
        )

    @_locked
    def register_content(
        self, container: Page | Object, mcid: int, elem: StructElem
    ) -> None:
        """Repair the reverse map for one existing ``/K`` content claim.

        *container* is the page or, for content that does not live in a page's
        own content stream, the form XObject or other stream that holds the
        marked-content sequence. Exactly one reachable ``/K`` claim by *elem*
        must already name ``(container, mcid)``. This method only creates or
        repairs the matching parent-tree entry; use :meth:`StructElem.add_content`
        to create a new claim.

        Raises:
            StructureTreeError: If the matching claim is absent, duplicated,
                or belongs to another element.
        """
        mcid = _validate_mcid(mcid)
        elem._require_owned()
        container_obj = _require_content_container(container, self._tree.pdf)
        state = self._content_check_state()
        claimants = state.claims.get((_object_identity(container_obj), mcid), [])
        if len(claimants) != 1:
            raise StructureTreeError(
                "register_content requires exactly one reachable matching /K claim"
            )
        if not _same_object(claimants[0].obj, elem.obj):
            raise StructureTreeError(
                "The matching /K claim belongs to another structure element"
            )
        self._check_content(
            container_obj,
            mcid,
            elem,
            allow_existing_claim=True,
            _state=state,
        )
        self._register_content(container_obj, mcid, elem, state)

    def _register_content(
        self,
        container: Object,
        mcid: int,
        elem: StructElem,
        state: _ContentCheckState,
    ) -> None:
        key = self.key_for_page(container, create=True, _state=state)
        assert key is not None
        entry = self[key]
        if not isinstance(entry, Array):
            raise StructureTreeError(
                f"Parent tree entry {key} is not an array "
                f"({_safe_object_description(entry)})"
            )
        while len(entry) <= mcid:
            entry.append(None)
        entry[mcid] = elem.obj

    def _check_object(
        self,
        referent: Object,
        elem: StructElem,
        *,
        page: Object | None = None,
        allow_existing_claim: bool = False,
    ) -> None:
        """Reject an object registration before anything has been mutated."""
        referent = _require_referent(referent, self._tree.pdf)
        elem._require_owned()
        _ = self.next_key
        if Name.StructParents in referent:
            raise StructureTreeError(
                "A referenced object cannot also have /StructParents"
            )
        claims: list[tuple[StructElem, Object]] = []
        for claimant in _elements_including(self._tree, elem):
            default_page = _effective_page_obj(claimant.obj)
            for item in _kid_items(claimant.obj.get(Name.K)):
                if (
                    not isinstance(item, Dictionary)
                    or not _is_name(item.get(Name.Type), Name.OBJR)
                    or not _same_object(item.get(Name.Obj), referent)
                ):
                    continue
                claim_page = item.get(Name.Pg, default_page)
                if claim_page is None:
                    raise StructureTreeError(
                        "Existing object reference has no associated page"
                    )
                claims.append((claimant, _require_page(claim_page, self._tree.pdf)))
        is_annotation = (
            isinstance(referent, Dictionary)
            and not isinstance(referent, Stream)
            and (
                _is_name(referent.get(Name.Type), Name.Annot)
                or _is_page_annotation(self._tree.pdf, referent)
            )
        )
        if is_annotation:
            containing_pages = [
                candidate.obj
                for candidate in self._tree.pdf.pages
                if _page_has_annotation(candidate.obj, referent)
            ]
            claim_pages = [claim_page for _, claim_page in claims]
            if page is not None:
                claim_pages.append(page)
            if len(containing_pages) != 1 or any(
                not _same_object(claim_page, containing_pages[0])
                for claim_page in claim_pages
            ):
                raise StructureTreeError(
                    "An annotation dictionary must appear on exactly its claimed page"
                )
        if claims:
            if any(not _same_object(claim.obj, elem.obj) for claim, _ in claims):
                raise StructureTreeError(
                    "Referenced object is already claimed by another structure element"
                )
            for index, (_, claim_page) in enumerate(claims):
                if any(
                    _same_object(claim_page, other_page)
                    for _, other_page in claims[:index]
                ):
                    raise StructureTreeError(
                        "Referenced object is already claimed on the same page"
                    )
            if not allow_existing_claim and (
                page is None
                or any(_same_object(page, claim_page) for _, claim_page in claims)
            ):
                raise StructureTreeError(
                    "Referenced object is already claimed on the same page"
                )
        raw_key = referent.get(Name.StructParent)
        if Name.StructParent not in referent:
            if claims and not allow_existing_claim:
                raise StructureTreeError(
                    "Referenced object has no parent tree owner for another page"
                )
            self._next_available_key()
            return
        key = _as_int(raw_key)
        if key is None:
            raise StructureTreeError("/StructParent must be an integer")
        if key not in self:
            if claims and not allow_existing_claim:
                raise StructureTreeError(
                    "Referenced object has no parent tree owner for another page"
                )
            for container in _structure_key_containers(self._tree.pdf):
                if _same_object(container, referent):
                    continue
                if any(
                    _as_int(container.get(name)) == key
                    for name in (Name.StructParent, Name.StructParents)
                ):
                    raise StructureTreeError(
                        f"/StructParent {key} is already used by another object"
                    )
            return
        claimed = self[key]
        if isinstance(claimed, Dictionary):
            if claims and _same_object(claimed, elem.obj):
                return
            owner = "this" if _same_object(claimed, elem.obj) else "another"
            raise StructureTreeError(
                f"/StructParent {key} is already claimed by {owner} structure element"
            )
        raise StructureTreeError(
            f"Parent tree entry {key} is not a structure element "
            f"({_safe_object_description(claimed)})"
        )

    @_locked
    def register_object(self, referent: Object, elem: StructElem) -> int:
        """Repair the reverse map for existing ``/OBJR`` claims.

        One or more reachable ``/K`` ``/OBJR`` entries owned by *elem* must
        already name *referent*. Multiple entries are accepted only for
        distinct pages where that representation is legal. This method creates
        or repairs only ``/StructParent`` and its parent-tree entry; use
        :meth:`StructElem.add_object` to create a new object claim.

        Raises:
            StructureTreeError: If no matching claim exists, claims are
                inconsistent, or a claim belongs to another element.
        """
        referent = _require_referent(referent, self._tree.pdf)
        elem._require_owned()
        claimants: list[StructElem] = []
        for claimant in self._tree._walk_all():
            for item in _kid_items(claimant.obj.get(Name.K)):
                if (
                    isinstance(item, Dictionary)
                    and _is_name(item.get(Name.Type), Name.OBJR)
                    and _same_object(item.get(Name.Obj), referent)
                ):
                    claimants.append(claimant)
        if not claimants:
            raise StructureTreeError(
                "register_object requires a reachable matching /OBJR claim"
            )
        if any(not _same_object(claimant.obj, elem.obj) for claimant in claimants):
            raise StructureTreeError(
                "The matching /OBJR claim belongs to another structure element"
            )
        self._check_object(referent, elem, allow_existing_claim=True)
        return self._register_object(referent, elem)

    def _register_object(self, referent: Object, elem: StructElem) -> int:
        """Write an object reverse mapping after the claim was prechecked."""
        if Name.StructParent in referent:
            key = _as_int(referent.get(Name.StructParent))
            assert key is not None
        else:
            key = self.allocate_key()
            referent.StructParent = key
        self[key] = elem.obj
        return key

    def _preflight_unregister_subtree(
        self, removed: list[StructElem]
    ) -> _ParentRemovalPlan:
        root = self._tree.obj
        if Name.ParentTree not in root:
            number_tree = None
            entries: list[tuple[int, Object]] = []
        else:
            raw_parent_tree = root.get(Name.ParentTree)
            if not isinstance(raw_parent_tree, Dictionary):
                raise StructureTreeError("/ParentTree must be a dictionary")
            try:
                number_tree = NumberTree(raw_parent_tree)
                entries = [(key, number_tree[key]) for key in list(number_tree.keys())]
            except Exception as exc:
                raise StructureTreeError(
                    "/ParentTree is not a valid number tree"
                ) from exc
        referents = list(_referenced_objects(removed))
        structural_targets = list(referents)
        for elem in removed:
            for ref in _content_references(elem):
                structural_targets.extend(
                    target
                    for target in (ref.page, ref.stream, ref.stream_owner)
                    if isinstance(target, Object)
                )
        if any(
            target.is_indirect and not target.same_owner_as(self._tree.pdf.Root)
            for target in structural_targets
        ):
            raise StructureTreeError(
                "Cannot remove a subtree that references objects in another PDF"
            )
        return _ParentRemovalPlan(
            number_tree,
            entries,
            {elem.obj.objgen for elem in removed},
            referents,
        )

    @staticmethod
    def _unregister_subtree(plan: _ParentRemovalPlan) -> None:
        removed_keys: set[int] = set()
        for key, entry in plan.entries:
            if isinstance(entry, Array):
                for i, item in enumerate(entry):
                    if (
                        isinstance(item, Dictionary)
                        and item.objgen in plan.removed_objgens
                    ):
                        entry[i] = None
            elif isinstance(entry, Dictionary) and entry.objgen in plan.removed_objgens:
                assert plan.number_tree is not None
                del plan.number_tree[key]
                removed_keys.add(key)
        retained_keys = {key for key, _ in plan.entries} - removed_keys
        for referent in plan.referents:
            struct_parent = _as_int(referent.get(Name.StructParent))
            if struct_parent is not None and struct_parent not in retained_keys:
                del referent[Name.StructParent]

    def __repr__(self):
        try:
            raw_tree = self._tree.obj.get(Name.ParentTree)
            count = (
                len(list(NumberTree(raw_tree).keys()))
                if isinstance(raw_tree, Dictionary)
                else 0
            )
            return f'<pikepdf.ParentTree: {count} entries>'
        except Exception:
            return '<pikepdf.ParentTree: unavailable>'


class StructTree:
    """The logical structure tree of a tagged PDF ({{ pdfrm }} section 14.7).

    Wraps the document catalog's ``/StructTreeRoot``. Nothing is written to the
    PDF until :meth:`create` or :meth:`add` is called.

    Arguments:
        pdf: PDF document object.
        max_depth: Maximum recursion depth when walking the tree.

    See Also:
        :meth:`pikepdf.Pdf.open_structure_tree`
    """

    def __init__(self, pdf: Pdf, max_depth: int = 100, strict: bool = False):
        """Initialize StructTree."""
        self.pdf = pdf
        self._strict = bool(strict)
        self._max_depth = _validate_nonnegative_int(max_depth, "max_depth")
        self._checked_kids: dict[_ObjectIdentity, int] = {}
        self._lock_pdf = pdf
        self._claims: dict[_ObjectIdentity, tuple[int, dict[_ObjectIdentity, int]]] = {}

    @property
    def exists(self) -> bool:
        """True if the catalog contains a ``/StructTreeRoot`` entry."""
        return Name.StructTreeRoot in self.pdf.Root

    @property
    def obj(self) -> Dictionary:
        """The ``/StructTreeRoot`` dictionary."""
        if Name.StructTreeRoot not in self.pdf.Root:
            raise StructureTreeError(
                "This PDF has no structure tree. Call StructTree.create() first."
            )
        root = self.pdf.Root.get(Name.StructTreeRoot)
        if not isinstance(root, Dictionary):
            raise StructureTreeError("/StructTreeRoot must be a dictionary")
        return root

    @_locked
    def create(self) -> StructTree:
        """Create the structure tree if the document does not have one.

        Also marks the document as tagged (``/MarkInfo``). Returns ``self`` so
        the call can be chained. Does nothing if a structure tree exists.
        """
        root_present = Name.StructTreeRoot in self.pdf.Root
        existing_root = self.pdf.Root.get(Name.StructTreeRoot)
        if root_present and not isinstance(existing_root, Dictionary):
            raise StructureTreeError("/StructTreeRoot must be a dictionary")
        if isinstance(existing_root, Dictionary) and not existing_root.is_indirect:
            raise StructureTreeError("/StructTreeRoot must be an indirect object")
        if isinstance(existing_root, Dictionary):
            root_type = existing_root.get(Name.Type)
            if root_type is not None and not _is_name(root_type, Name.StructTreeRoot):
                raise StructureTreeError("/StructTreeRoot has the wrong /Type")
        if Name.MarkInfo in self.pdf.Root and not isinstance(
            self.pdf.Root.get(Name.MarkInfo), Dictionary
        ):
            raise StructureTreeError("/MarkInfo must be a dictionary")

        if not root_present:
            self.pdf.Root.StructTreeRoot = self.pdf.make_indirect(
                Dictionary(
                    Type=Name.StructTreeRoot,
                    K=Array([]),
                    ParentTreeNextKey=0,
                )
            )
            self.obj.ParentTree = NumberTree.new(self.pdf).obj
        elif isinstance(existing_root, Dictionary) and Name.Type not in existing_root:
            existing_root.Type = Name.StructTreeRoot
        self.marked = True
        return self

    @property
    def marked(self) -> bool:
        """Whether the document declares itself tagged (``/MarkInfo /Marked``)."""
        mark_info = self.pdf.Root.get(Name.MarkInfo)
        if not isinstance(mark_info, Dictionary):
            return False
        return _as_bool(mark_info.get(Name.Marked)) is True

    @marked.setter
    @_locked
    def marked(self, value: bool) -> None:
        if not isinstance(value, bool):
            raise TypeError("marked must be a bool")
        mark_info = self.pdf.Root.get(Name.MarkInfo)
        if Name.MarkInfo in self.pdf.Root and not isinstance(mark_info, Dictionary):
            raise StructureTreeError("/MarkInfo must be a dictionary")
        if mark_info is None:
            mark_info = self.pdf.make_indirect(Dictionary())
            self.pdf.Root.MarkInfo = mark_info
        mark_info.Marked = value

    @property
    def parent_tree(self) -> ParentTree:
        """The structural parent tree."""
        return ParentTree(self)

    @property
    def role_map(self) -> Dictionary | None:
        """The role map (``/RoleMap``), mapping custom tags to standard ones."""
        if Name.RoleMap not in self.obj:
            return None
        role_map = self.obj.get(Name.RoleMap)
        if not isinstance(role_map, Dictionary) or isinstance(role_map, Stream):
            raise StructureTreeError("/RoleMap must be a dictionary")
        if role_map.is_indirect and not role_map.same_owner_as(self.pdf.Root):
            raise StructureTreeError("/RoleMap belongs to another PDF")
        return role_map

    @_locked
    def add_role(self, custom: Name, standard: Name) -> None:
        """Map a custom structure type to a standard one in ``/RoleMap``."""
        if not isinstance(custom, Name) or not isinstance(standard, Name):
            raise TypeError("Role map keys and values must be pikepdf.Name objects")
        role_map = self.role_map
        if role_map is not None and any(
            not isinstance(role_map[key], Name) for key in role_map.keys()
        ):
            raise StructureTreeError("/RoleMap values must be names")
        if role_map is None:
            role_map = Dictionary()
            self.obj.RoleMap = role_map
        role_map[custom] = standard

    @property
    def class_map(self) -> Dictionary | None:
        """The class map (``/ClassMap``) of named attribute sets."""
        if Name.ClassMap not in self.obj:
            return None
        class_map = self.obj.get(Name.ClassMap)
        if not isinstance(class_map, Dictionary) or isinstance(class_map, Stream):
            raise StructureTreeError("/ClassMap must be a dictionary")
        if class_map.is_indirect and not class_map.same_owner_as(self.pdf.Root):
            raise StructureTreeError("/ClassMap belongs to another PDF")
        return class_map

    @property
    def id_tree(self) -> NameTree | None:
        """The low-level identifier name tree (``/IDTree``), if present.

        Use :meth:`find_by_id` when an identifier may be an arbitrary PDF byte
        string; the generic :class:`NameTree` interface exposes text keys.
        """
        if Name.IDTree not in self.obj:
            return None
        id_tree = self.obj.get(Name.IDTree)
        if not isinstance(id_tree, Dictionary) or isinstance(id_tree, Stream):
            raise StructureTreeError("/IDTree must be a name-tree dictionary")
        if id_tree.is_indirect and not id_tree.same_owner_as(self.pdf.Root):
            raise StructureTreeError("/IDTree belongs to another PDF")
        try:
            result = NameTree(id_tree)
            list(result.keys())
        except Exception as error:
            raise StructureTreeError("/IDTree is not a valid name tree") from error
        return result

    def find_by_id(self, element_id: str | bytes) -> StructElem | None:
        """Look up a structure element by its exact text or byte-string ID."""
        if not isinstance(element_id, str | bytes):
            raise TypeError("element_id must be a str or bytes")
        entries, has_id_tree = self._id_entries_for_mutation()
        if not has_id_tree:
            return None
        key = bytes(String(element_id))
        target = entries.get(key)
        if target is None:
            return None
        reachable = self._reachable_id_entries()
        reachable_target = reachable.get(key)
        if (
            not isinstance(target, Dictionary)
            or not target.is_indirect
            or not target.same_owner_as(self.pdf.Root)
            or not _is_struct_elem(target)
            or reachable_target is None
            or not _same_object(target, reachable_target)
        ):
            raise StructureTreeError(
                "/IDTree entry does not name the reachable element with matching /ID"
            )
        return StructElem(target, self)

    def _id_entries_for_mutation(self) -> tuple[dict[bytes, Object], bool]:
        from pikepdf.models.structure._validation import _validation_id_entries

        problems: list[str] = []
        entries, has_id_tree = _validation_id_entries(self, self.obj, problems)
        for key, target in entries.items():
            if (
                not isinstance(target, Dictionary)
                or not target.is_indirect
                or not target.same_owner_as(self.pdf.Root)
                or not _is_struct_elem(target)
            ):
                problems.append(
                    f"/IDTree entry {str(String(key))!r} is not an owned "
                    "indirect structure element"
                )
        if problems:
            raise StructureTreeError(
                "/IDTree is not a valid name tree: " + "; ".join(problems)
            )
        return entries, has_id_tree

    def _reachable_id_entries(
        self,
        *,
        replacement: tuple[Dictionary, bytes | None] | None = None,
        excluded: set[_ObjectIdentity] | None = None,
    ) -> dict[bytes, Object]:
        entries: dict[bytes, Object] = {}
        excluded = excluded or set()
        for elem in self._walk_all():
            if _object_identity(elem.obj) in excluded:
                continue
            raw_id = elem.obj.get(Name.ID)
            if not elem.obj.is_indirect:
                if raw_id is None:
                    continue
                raise StructureTreeError(
                    "Element identifiers cannot reference a direct structure element"
                )
            if not elem.obj.same_owner_as(self.pdf.Root):
                raise StructureTreeError(
                    "Element identifiers cannot be rebuilt from a structure "
                    "tree containing foreign elements"
                )
            if replacement is not None and _same_object(elem.obj, replacement[0]):
                key = replacement[1]
            elif raw_id is None:
                key = None
            elif not isinstance(raw_id, String):
                raise StructureTreeError(
                    f"{elem!r} has an /ID that is not a PDF string"
                )
            else:
                key = bytes(raw_id)
            if key is None:
                continue
            owner = entries.get(key)
            if owner is not None and not _same_object(owner, elem.obj):
                display = str(String(key))
                raise StructureTreeError(
                    f"Element identifier {display!r} is not unique"
                )
            entries[key] = elem.obj
        return entries

    @staticmethod
    def _same_id_entries(
        first: Mapping[bytes, Object], second: Mapping[bytes, Object]
    ) -> bool:
        return first.keys() == second.keys() and all(
            _same_object(first[key], value) for key, value in second.items()
        )

    def _build_id_tree(self, entries: Mapping[bytes, Object]) -> Dictionary:
        names = Array()
        for key in sorted(entries):
            names.append(String(key))
            names.append(entries[key])
        return cast(
            Dictionary,
            self.pdf.make_indirect(Dictionary(Names=names)),
        )

    def _preflight_remove_element_ids(
        self, elements: list[StructElem]
    ) -> _IdRemovalPlan:
        self._id_entries_for_mutation()
        if any(
            not elem.obj.is_indirect or not elem.obj.same_owner_as(self.pdf.Root)
            for elem in elements
        ):
            raise StructureTreeError(
                "Cannot remove a subtree containing direct or foreign elements"
            )
        removed = {_object_identity(elem.obj) for elem in elements}
        return _IdRemovalPlan(self._reachable_id_entries(excluded=removed))

    def _remove_element_ids(self, plan: _IdRemovalPlan) -> None:
        if plan.entries:
            self.obj.IDTree = self._build_id_tree(plan.entries)
        elif Name.IDTree in self.obj:
            del self.obj[Name.IDTree]

    def element(self, obj: Dictionary) -> StructElem:
        """Wrap an existing ``/StructElem`` dictionary as a :class:`StructElem`."""
        _require_owned_indirect(obj, self.pdf, "Structure element")
        if not _is_struct_elem(obj):
            raise StructureTreeError(
                f"Not a structure element ({_safe_object_description(obj)})"
            )
        return StructElem(obj, self)

    def _validate_element_arguments(
        self,
        tag: Name,
        page: Page | Object | None,
        alt: str | None,
        actual_text: str | None,
        expansion: str | None,
        lang: str | None,
        title: str | None,
        attributes: Object | None,
    ) -> Object | None:
        if not isinstance(tag, Name):
            raise TypeError("Structure type must be a pikepdf.Name")
        page_obj = None if page is None else _require_page(page, self.pdf)
        for label, value in (
            ("alt", alt),
            ("actual_text", actual_text),
            ("expansion", expansion),
            ("lang", lang),
            ("title", title),
        ):
            if value is not None and not isinstance(value, str):
                raise TypeError(f"{label} must be a str or None")
        if attributes is not None:
            _require_attributes(attributes, self.pdf)
        return page_obj

    @property
    def kids(self) -> list[StructElem]:
        """The top-level structure elements (the root's ``/K``)."""
        if not self.exists:
            return []
        root = self.obj
        if Name.K not in root:
            return []
        raw_kids = root.get(Name.K)
        if raw_kids is None:
            raise StructureTreeError("/StructTreeRoot /K is null")
        result: list[StructElem] = []
        for index, item in enumerate(_kid_items(raw_kids)):
            if not _is_struct_elem(item):
                raise StructureTreeError(
                    f"/StructTreeRoot /K entry {index} is not a structure element"
                )
            result.append(StructElem(cast(Dictionary, item), self))
        return result

    def _claims_for(self, parent: Dictionary) -> dict[_ObjectIdentity, int]:
        """How many times *parent* claims each object in its ``/K``.

        Memoized per parent and invalidated whenever the length of ``/K``
        changes, so repeated ancestry checks against the same parent do not
        rescan its children.
        """
        identity = _object_identity(parent)
        existing = parent.get(Name.K)
        if existing is None:
            count = 0
        else:
            count = len(existing) if isinstance(existing, Array) else 1
        cached = self._claims.get(identity)
        if cached is not None and cached[0] == count:
            return cached[1]
        claims: dict[_ObjectIdentity, int] = {}
        for item in _kid_items(existing):
            if isinstance(item, Dictionary):
                child = _object_identity(item)
                claims[child] = claims.get(child, 0) + 1
        self._claims[identity] = (count, claims)
        return claims

    def _record_claim(self, parent: Dictionary, item: Object | int) -> None:
        """Keep the claim memo in step with an append made through this API."""
        identity = _object_identity(parent)
        cached = self._claims.get(identity)
        if cached is None:
            return
        _count, claims = cached
        existing = parent.get(Name.K)
        new_count = (
            0
            if existing is None
            else (len(existing) if isinstance(existing, Array) else 1)
        )
        if isinstance(item, Dictionary):
            child = _object_identity(item)
            claims[child] = claims.get(child, 0) + 1
        self._claims[identity] = (new_count, claims)

    def _invalidate_claims(self, parent: Dictionary) -> None:
        self._claims.pop(_object_identity(parent), None)

    def _preflight_attach(self, elem: StructElem, parent: Dictionary) -> None:
        """Validate an attachment before anything is written."""
        if not isinstance(elem, StructElem):
            raise TypeError("attach_child requires a StructElem")
        if elem.tree is not self and not _same_object(elem.tree.obj, self.obj):
            raise StructureTreeError(
                "Structure element belongs to another structure tree"
            )
        if not elem.obj.is_indirect:
            raise StructureTreeError(
                "Only an indirect structure element can be attached"
            )
        _require_owned_indirect(elem.obj, self.pdf, "Structure element")
        if not _is_struct_elem(elem.obj):
            raise StructureTreeError("Object to attach is not a structure element")
        if Name.P in elem.obj:
            raise StructureTreeError(
                "Structure element is already attached; remove() it first"
            )
        if _same_object(elem.obj, parent):
            raise StructureTreeError("A structure element cannot be its own parent")
        for descendant in self._walk_from(elem, None):
            if _same_object(descendant.obj, parent):
                raise StructureTreeError("Attaching this element would create a cycle")

    def _register_subtree(self, elem: StructElem) -> None:
        """Restore parent tree entries for a subtree that has just been attached."""
        parent_tree = self.parent_tree
        state = parent_tree._content_check_state()
        for descendant in self._walk_from(elem, None):
            default_page = _effective_page_obj(descendant.obj)
            for item in _kid_items(descendant.obj.get(Name.K)):
                mcid = _as_int(item)
                if mcid is not None:
                    if default_page is not None:
                        parent_tree._register_content(
                            default_page, mcid, descendant, state
                        )
                    continue
                if not isinstance(item, Dictionary):
                    continue
                item_type = item.get(Name.Type)
                if _is_name(item_type, Name.MCR):
                    ref = MarkedContentRef.from_object(item, default_page)
                    container = ref.stream if ref.stream is not None else ref.page
                    if container is not None:
                        parent_tree._register_content(
                            container, ref.mcid, descendant, state
                        )
                elif _is_name(item_type, Name.OBJR):
                    referent = item.get(Name.Obj)
                    if isinstance(referent, Dictionary | Stream):
                        parent_tree._register_object(referent, descendant)

    @_locked
    def attach(self, elem: StructElem) -> StructElem:
        """Attach a detached structure element at the top level of the tree.

        See :meth:`StructElem.attach_child`, of which this is the root-level
        equivalent.
        """
        self.create()
        self._preflight_attach(elem, self.obj)
        self._preflight_append_root()
        with self.pdf.lock():
            elem.obj.P = self.obj
            kids = self.obj.get(Name.K)
            if isinstance(kids, Array):
                kids.append(elem.obj)
            elif kids is None:
                self.obj.K = Array([elem.obj])
            else:
                self.obj.K = Array([kids, elem.obj])
            self._record_claim(self.obj, elem.obj)
            self._register_subtree(elem)
        return elem

    def _tolerant_root_children(self) -> Iterator[StructElem]:
        if not self.exists:
            return
        for item in _kid_items(self.obj.get(Name.K)):
            if _is_struct_elem(item):
                yield StructElem(cast(Dictionary, item), self)

    def _preflight_structure_links(self) -> list[Dictionary]:
        if not self.exists or Name.K not in self.obj:
            return []
        raw_kids = self.obj.get(Name.K)
        if raw_kids is None:
            raise StructureTreeError("/StructTreeRoot /K is null")
        pending: list[tuple[Dictionary, Dictionary]] = []
        for item in _kid_items(raw_kids):
            if not _is_struct_elem(item):
                raise StructureTreeError(
                    "/StructTreeRoot /K entry is not a structure element"
                )
            pending.append((cast(Dictionary, item), self.obj))
        seen: set[_ObjectIdentity] = set()
        elements: list[Dictionary] = []
        while pending:
            elem_obj, expected_parent = pending.pop()
            parent = elem_obj.get(Name.P)
            if not isinstance(parent, Dictionary) or not _same_object(
                parent, expected_parent
            ):
                raise StructureTreeError(
                    "Existing structure element /P does not name its /K parent"
                )
            if elem_obj.is_indirect:
                _require_owned_indirect(
                    elem_obj, self.pdf, "Existing structure element"
                )
                identity = _object_identity(elem_obj)
                if identity in seen:
                    raise StructureTreeError(
                        "Existing structure element is repeated or creates a cycle"
                    )
                seen.add(identity)
                elements.append(elem_obj)
                for child in StructElem(elem_obj, self)._child_elements():
                    pending.append((child.obj, elem_obj))
            elif Name.K in elem_obj:
                raise StructureTreeError(
                    "A direct structure element must be a terminal child"
                )
        return elements

    def _preflight_append_root(self) -> None:
        """Validate the root's own ``/K`` before appending to it.

        Only the root's direct entries are inspected. Defects deeper in the
        tree are reported by :meth:`validate`, which walks everything, rather
        than re-walked on each append.
        """
        if not self.exists or Name.K not in self.obj:
            return
        raw_kids = self.obj.get(Name.K)
        if raw_kids is None:
            raise StructureTreeError("/StructTreeRoot /K is null")
        seen: set[_ObjectIdentity] = set()
        for item in _kid_items(raw_kids):
            if not _is_struct_elem(item):
                raise StructureTreeError(
                    "/StructTreeRoot /K entry is not a structure element"
                )
            if not item.is_indirect:
                if Name.K in item:
                    raise StructureTreeError(
                        "A direct structure element must be a terminal child"
                    )
                continue
            _require_owned_indirect(item, self.pdf, "Existing structure element")
            identity = _object_identity(item)
            if identity in seen:
                raise StructureTreeError(
                    "/StructTreeRoot /K repeats a structure element"
                )
            seen.add(identity)
            parent = item.get(Name.P)
            if not isinstance(parent, Dictionary) or not _same_object(parent, self.obj):
                raise StructureTreeError(
                    "Existing structure element /P does not name its /K parent"
                )

    @_locked
    def add(
        self,
        tag: Name,
        *,
        page: Page | Object | None = None,
        alt: str | None = None,
        actual_text: str | None = None,
        expansion: str | None = None,
        lang: str | None = None,
        title: str | None = None,
        attributes: Object | None = None,
    ) -> StructElem:
        """Create a top-level structure element, creating the tree if needed.

        Takes the same keyword arguments as :meth:`StructElem.add_child`.

        Returns:
            The newly created :class:`StructElem`.
        """
        page_obj = self._validate_element_arguments(
            tag,
            page,
            alt,
            actual_text,
            expansion,
            lang,
            title,
            attributes,
        )
        if self.exists:
            self._preflight_append_root()
        self.create()
        elem = self._new_element(
            self.obj,
            tag,
            page=page_obj,
            alt=alt,
            actual_text=actual_text,
            expansion=expansion,
            lang=lang,
            title=title,
            attributes=attributes,
        )
        kids = self.obj.get(Name.K)
        if isinstance(kids, Array):
            kids.append(elem.obj)
        elif kids is None:
            self.obj.K = Array([elem.obj])
        else:
            self.obj.K = Array([kids, elem.obj])
        return elem

    def _new_element(
        self,
        parent: Dictionary,
        tag: Name,
        *,
        page: Object | None,
        alt: str | None,
        actual_text: str | None,
        expansion: str | None,
        lang: str | None,
        title: str | None,
        attributes: Object | None,
    ) -> StructElem:
        data = Dictionary(Type=Name.StructElem, S=tag, P=parent)
        if page is not None:
            data.Pg = page
        for key, value in (
            (Name.Alt, alt),
            (Name.ActualText, actual_text),
            (Name.E, expansion),
            (Name.Lang, lang),
            (Name.T, title),
        ):
            if value is not None:
                data[key] = String(value)
        if attributes is not None:
            data.A = attributes
        return StructElem(self.pdf.make_indirect(data), self)

    def _walk_from(
        self,
        elem: StructElem,
        max_depth: int | None,
        *,
        _seen: set[_ObjectIdentity] | None = None,
    ) -> Iterator[StructElem]:
        """Walk *elem* and its descendants; ``None`` means no depth limit."""
        stack: list[tuple[StructElem, int]] = [(elem, 0)]
        seen = set() if _seen is None else _seen
        visited = 0
        while stack:
            current, depth = stack.pop()
            visited += 1
            if visited > _MAX_STRUCTURE_TREE_ELEMENTS:
                raise StructureTreeError("Structure tree traversal limit exceeded")
            if not current.obj.is_indirect and Name.K in current.obj:
                raise StructureTreeError(
                    "A direct structure element must be a terminal child"
                )
            identity = _object_identity(current.obj)
            if identity in seen:
                raise StructureTreeError(
                    "Structure element is repeated or creates a cycle"
                )
            seen.add(identity)
            yield current
            if max_depth is None or depth < max_depth:
                stack.extend((child, depth + 1) for child in reversed(current.children))

    def walk(self) -> Iterator[StructElem]:
        """Iterate every structure element in the tree, depth first.

        Elements nested more deeply than the tree's ``max_depth`` are not
        visited.
        """
        seen: set[_ObjectIdentity] = set()
        for kid in self.kids:
            yield from self._walk_from(kid, self._max_depth, _seen=seen)

    def _walk_all(self) -> Iterator[StructElem]:
        """Walk every element regardless of depth, for internal consistency work."""
        seen: set[_ObjectIdentity] = set()
        for kid in self.kids:
            yield from self._walk_from(kid, None, _seen=seen)

    def _walk_all_tolerant(self) -> Iterator[StructElem]:
        stack = list(reversed(list(self._tolerant_root_children())))
        seen: set[_ObjectIdentity] = set()
        visited = 0
        while stack:
            current = stack.pop()
            visited += 1
            if visited > _MAX_STRUCTURE_TREE_ELEMENTS:
                return
            identity = _object_identity(current.obj)
            if identity in seen:
                continue
            seen.add(identity)
            yield current
            if not current.obj.is_indirect and Name.K in current.obj:
                continue
            stack.extend(reversed(current._child_elements()))

    def elements_with_tag(self, tag: Name) -> Iterator[StructElem]:
        """Iterate every element in the tree whose structure type is *tag*."""
        if not isinstance(tag, Name):
            raise TypeError("tag must be a pikepdf.Name")
        for elem in self.walk():
            if _is_name(elem.obj.get(Name.S), tag):
                yield elem

    @_locked
    def remove(self) -> None:
        """Delete the structure tree and every reference to it.

        Removes ``/StructTreeRoot`` and ``/MarkInfo /Marked`` from the catalog,
        deleting ``/MarkInfo`` only when it becomes empty. Also removes the
        ``/StructParents`` and ``/StructParent`` keys from every page,
        annotation, form XObject and other stream that carries one. Foreign
        objects named by malformed references are left untouched.
        """
        containers = list(_structure_key_containers(self.pdf))
        if isinstance(self.pdf.Root.get(Name.StructTreeRoot), Dictionary):
            elements = list(self._walk_all_tolerant())
            containers.extend(
                referent
                for referent in _referenced_objects(elements)
                if not referent.is_indirect or referent.same_owner_as(self.pdf.Root)
            )
            containers.extend(
                ref.stream
                for elem in elements
                for ref in _content_references(elem)
                if isinstance(ref.stream, Stream)
                and (
                    not ref.stream.is_indirect
                    or ref.stream.same_owner_as(self.pdf.Root)
                )
            )
        for container in containers:
            for key in (Name.StructParents, Name.StructParent):
                if key in container:
                    del container[key]
        if Name.StructTreeRoot in self.pdf.Root:
            del self.pdf.Root[Name.StructTreeRoot]
        mark_info = self.pdf.Root.get(Name.MarkInfo)
        if isinstance(mark_info, Dictionary):
            if Name.Marked in mark_info:
                del mark_info[Name.Marked]
            if len(mark_info) == 0:
                del self.pdf.Root[Name.MarkInfo]

    def validate(self, *, check_content: bool = True) -> list[str]:
        """Check the structure tree for inconsistencies.

        Checks structure-element links, the ID and parent trees, page and Form
        XObject ``/StructParents`` keys, object ``/StructParent`` references,
        and (optionally) marked content found in supported content streams.
        The result is positive evidence that these supported relationships are
        consistent; it is not a complete PDF/UA conformance check.

        Arguments:
            check_content: Also parse page and supported referenced content
                streams and check that their marked-content identifiers
                correspond to parent-tree entries. Set to ``False`` to skip
                the parsing cost.

        Returns:
            A list of human-readable problem descriptions, empty when no
            supported inconsistency was found.
        """
        from pikepdf.models.structure._validation import _validate_tree

        return _validate_tree(self, check_content=check_content)

    def __iter__(self) -> Iterator[StructElem]:
        return iter(self.kids)

    def __len__(self) -> int:
        return len(self.kids)

    def __repr__(self):
        if not self.exists:
            return '<pikepdf.StructTree: no structure tree>'
        if not isinstance(self.pdf.Root.get(Name.StructTreeRoot), Dictionary):
            return '<pikepdf.StructTree: malformed structure tree>'
        try:
            count = sum(1 for _ in self._tolerant_root_children())
            return f'<pikepdf.StructTree: {count} top-level elements>'
        except Exception:
            return '<pikepdf.StructTree: unavailable>'
