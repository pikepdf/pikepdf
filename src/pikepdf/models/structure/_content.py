# SPDX-FileCopyrightText: 2026 Khushwant Parihar
# SPDX-License-Identifier: MPL-2.0

"""Content discovery and marking for tagged PDF logical structure."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from decimal import Decimal
from typing import Any, NamedTuple

from pikepdf._core import ContentStreamInstruction, NumberTree, Page
from pikepdf.models._content_stream import parse_content_stream, unparse_content_stream
from pikepdf.models.structure._common import (
    StructureTreeError,
    _as_decimal,
    _as_int,
    _inherited_page_attribute,
    _object_identity,
    _ObjectIdentity,
    _property_list,
    _require_direct_object_graph,
    _require_page,
    _safe_object_description,
    _same_object,
    _validate_mcid,
    _XObjectContextKey,
)
from pikepdf.models.structure._content_analysis import (
    _analyze_marker_content,
    _form_do_wrappers,
    _MarkerAnalysis,
    _resolve_xobject,
    _xobject_content_kinds,
)
from pikepdf.models.structure._tree import (
    ParentTree,
    StructElem,
    StructTree,
    _content_references,
    _ContentCheckState,
    _referenced_objects,
)
from pikepdf.objects import (
    Array,
    Dictionary,
    Name,
    Object,
    Operator,
    Stream,
)


@dataclass(frozen=True, repr=False)
class MarkedContent:
    """A marked-content sequence found in, or added to, a content stream."""

    tag: Name
    mcid: int | None
    properties: Object | None = None

    def __repr__(self) -> str:
        display_tag = str(self.tag) if isinstance(self.tag, Name) else '<malformed>'
        display_mcid = (
            str(self.mcid)
            if self.mcid is None or type(self.mcid) is int
            else '<malformed>'
        )
        properties = (
            'None'
            if self.properties is None
            else _safe_object_description(self.properties)
        )
        return (
            f'MarkedContent(tag={display_tag}, mcid={display_mcid}, '
            f'properties={properties})'
        )


def find_marked_content(page: Page) -> list[MarkedContent]:
    """Report the marked-content sequences in a page's content stream.

    Sequences inside form XObjects drawn by the page are not included; those
    have their own marked-content identifier space.

    Arguments:
        page: The page to scan.

    Returns:
        The sequences in the order they begin, including ``BMC`` sequences,
        whose :attr:`MarkedContent.mcid` is ``None``.
    """
    if not isinstance(page, Page):
        raise TypeError("page must be a pikepdf.Page")
    result = []
    resources = _inherited_page_attribute(page, Name.Resources)
    properties = None
    if isinstance(resources, Dictionary):
        properties = resources.get(Name.Properties)
    for instruction in parse_content_stream(page, 'BMC BDC'):
        operands = list(instruction.operands)
        operator = str(instruction.operator)
        expected_arity = 1 if operator == 'BMC' else 2
        if len(operands) != expected_arity or not isinstance(operands[0], Name):
            continue
        tag = operands[0]
        if operator == 'BMC':
            result.append(MarkedContent(tag, None))
            continue
        proplist = operands[1]
        if isinstance(proplist, Name) and isinstance(properties, Dictionary):
            proplist = properties.get(proplist, proplist)
        mcid = (
            _as_int(proplist.get(Name.MCID))
            if isinstance(proplist, Dictionary)
            else None
        )
        result.append(MarkedContent(tag, mcid, proplist))
    return result


def next_mcid(page: Page) -> int:
    """Return a marked-content identifier not already used by *page*.

    Arguments:
        page: The page whose content stream will receive the new sequence.
    """
    used = [
        mc.mcid
        for mc in find_marked_content(page)
        if mc.mcid is not None and mc.mcid >= 0
    ]
    return max(used) + 1 if used else 0


@dataclass(frozen=True)
class FontUsage:
    """One occurrence of a font selection (``Tf``) in a content stream."""

    font: Name
    size: Decimal
    index: int
    base_font: Name | None = None


def find_font_usage(page: Page) -> list[FontUsage]:
    """Report usable, well-formed font selections in page-content order.

    Intended for deciding which structure type suits which text: collect the
    distinct ``(font, size)`` pairs, decide on a tag for each, and pass the
    result to :func:`mark_text_runs`. Malformed ``Tf`` instructions whose font
    name or size cannot be interpreted are skipped. A selection whose font
    resource cannot be resolved is retained with ``base_font=None``.

    Arguments:
        page: The page to scan.
    """
    if not isinstance(page, Page):
        raise TypeError("page must be a pikepdf.Page")
    fonts = None
    resources = _inherited_page_attribute(page, Name.Resources)
    if isinstance(resources, Dictionary):
        fonts = resources.get(Name.Font)
    result = []
    for index, instruction in enumerate(parse_content_stream(page)):
        if instruction.operator != Operator('Tf'):
            continue
        operands = list(instruction.operands)
        if len(operands) != 2 or not isinstance(operands[0], Name):
            continue
        size = _as_decimal(operands[1])
        if size is None:
            continue
        base_font = None
        if isinstance(fonts, Dictionary):
            font_dict = fonts.get(operands[0])
            if isinstance(font_dict, Dictionary):
                candidate = font_dict.get(Name.BaseFont)
                if isinstance(candidate, Name):
                    base_font = candidate
        result.append(
            FontUsage(
                operands[0],
                size,
                index,
                base_font,
            )
        )
    return result


class _Span(NamedTuple):
    start: int
    stop: int
    tag: Name
    properties: Dictionary | None
    element: StructElem | None
    order: int


class ContentMarker:
    """Insert marked-content sequences into a page's existing content stream.

    Wraps chosen ranges of an already-parsed content stream in ``BDC``/``EMC``
    operators, allocating marked-content identifiers that do not collide with
    any already present on the page. Nothing is written until :meth:`apply` is
    called.

    Ranges are half-open index pairs into :attr:`instructions`. Ranges bound to
    structure elements may not nest inside one another. No range may partially
    overlap another range, split a path object, or straddle a ``q``/``Q``,
    ``BT``/``ET``, ``BX``/``EX``, or existing marked-content boundary. Invoked
    Form XObjects are checked recursively so claimed structural content is not
    nested inside claimed structural content.

    Arguments:
        page: The page whose content stream will be rewritten.
        first_mcid: The first identifier to allocate. Defaults to one past the
            highest already used by the page. :meth:`mark` refuses to hand out
            an identifier the page already uses.
    """

    def __init__(self, page: Page, *, first_mcid: int | None = None):
        """Initialize ContentMarker."""
        if not isinstance(page, Page):
            raise TypeError("page must be a pikepdf.Page")
        if first_mcid is not None:
            first_mcid = _validate_mcid(first_mcid)
        self.page = page
        self._instructions = list(parse_content_stream(page))
        resources = _inherited_page_attribute(page, Name.Resources)
        self._resources = resources
        self._analysis = _analyze_marker_content(self._instructions, resources)
        self._xobject_cache: dict[_XObjectContextKey, frozenset[str]] = {}
        self._used_mcids = {
            mc.mcid for mc in find_marked_content(page) if mc.mcid is not None
        }
        if (
            first_mcid is not None
            and first_mcid > 0
            and not any(mcid >= 0 for mcid in self._used_mcids)
        ):
            raise ValueError(
                "first_mcid must be 0 when the content stream has no MCIDs"
            )
        self._next_mcid = (
            max(0, max(self._used_mcids) + 1)
            if first_mcid is None and self._used_mcids
            else (0 if first_mcid is None else first_mcid)
        )
        self._spans: list[_Span] = []

    @property
    def instructions(self) -> tuple[Any, ...]:
        """The page's content stream instructions, as parsed."""
        return tuple(self._instructions)

    def mark(
        self,
        tag: Name,
        start: int,
        stop: int,
        *,
        element: StructElem | None = None,
        properties: Mapping[Any, Any] | Dictionary | None = None,
    ) -> MarkedContent:
        """Mark instructions ``[start:stop)`` as a marked-content sequence.

        Arguments:
            tag: The marked-content tag, e.g. ``Name.P``. Normally the same as
                the structure type of the element that will own the content.
            start: Index of the first instruction to include.
            stop: Index one past the last instruction to include.
            element: If given, :meth:`apply` attaches the new sequence to this
                structure element and updates the parent tree.
            properties: Additional entries for the ``BDC`` property list. This
                is written as an inline dictionary, so it must not contain
                indirect references.

        Returns:
            The :class:`MarkedContent` that :meth:`apply` will write.
        """
        if not isinstance(tag, Name):
            raise TypeError("Marked-content tags must be pikepdf.Name objects")
        if tag == Name.Artifact:
            raise ValueError("Use mark_artifact() to mark artifact content")
        if element is not None:
            if not isinstance(element, StructElem):
                raise TypeError("element must be a StructElem or None")
            element._require_owned()
            _require_page(self.page, element.tree.pdf)
        proplist = _property_list(properties)
        self._check_range(start, stop, structural=element is not None)
        mcid = self._next_mcid
        if mcid in self._used_mcids:
            raise StructureTreeError(
                f"Marked content identifier {mcid} is already used by this page"
            )
        proplist.MCID = mcid
        self._spans.append(_Span(start, stop, tag, proplist, element, len(self._spans)))
        self._used_mcids.add(mcid)
        self._next_mcid += 1
        return MarkedContent(tag, mcid, proplist)

    def mark_artifact(
        self,
        start: int,
        stop: int,
        *,
        properties: Mapping[Any, Any] | Dictionary | None = None,
    ) -> None:
        """Mark instructions ``[start:stop)`` as an artifact.

        Wrap content that the caller has designated as an artifact or otherwise
        non-structural, such as decorative rules or background graphics. The
        caller is responsible for deciding which content should be treated as
        an artifact.
        """
        proplist = _property_list(properties) if properties is not None else None
        mcid = None
        if proplist is not None and Name.MCID in proplist:
            mcid = _as_int(proplist.get(Name.MCID))
            if mcid is None:
                raise TypeError("Artifact /MCID must be an integer")
            _validate_mcid(mcid)
            if mcid in self._used_mcids:
                raise StructureTreeError(
                    f"Marked content identifier {mcid} is already used by this page"
                )
            if mcid > 0 and not any(value >= 0 for value in self._used_mcids):
                raise ValueError(
                    "Artifact /MCID must be 0 when the content stream has no MCIDs"
                )
        self._check_range(start, stop, structural=False)
        self._spans.append(
            _Span(start, stop, Name.Artifact, proplist, None, len(self._spans))
        )
        if mcid is not None:
            self._used_mcids.add(mcid)
            self._next_mcid = max(self._next_mcid, mcid + 1)

    def _check_range(self, start: int, stop: int, *, structural: bool) -> None:
        if type(start) is not int or type(stop) is not int:
            raise TypeError("Instruction range indices must be integers")
        if not 0 <= start < stop <= len(self._instructions):
            raise IndexError(
                f"Invalid instruction range [{start}:{stop}) for a content stream "
                f"of {len(self._instructions)} instructions"
            )
        for other in self._spans:
            disjoint = stop <= other.start or other.stop <= start
            nested = (start <= other.start and other.stop <= stop) or (
                other.start <= start and stop <= other.stop
            )
            if not disjoint and not nested:
                raise StructureTreeError(
                    f"Range [{start}:{stop}) partially overlaps "
                    f"[{other.start}:{other.stop})"
                )
            if not disjoint and structural and other.element is not None:
                raise StructureTreeError(
                    "Tagged marked-content sequences must not be nested"
                )
        self._validate_range_against_content(
            start,
            stop,
            structural=False,
            instructions=self._instructions,
            analysis=self._analysis,
            resources=self._resources,
            xobject_cache=self._xobject_cache,
            claimed_mcids={},
            structural_objects=set(),
        )

    @staticmethod
    def _validate_range_against_content(
        start: int,
        stop: int,
        *,
        structural: bool,
        instructions: list[Any],
        analysis: _MarkerAnalysis,
        resources: Object | None,
        xobject_cache: dict[_XObjectContextKey, frozenset[str]],
        claimed_mcids: Mapping[_ObjectIdentity, set[int] | frozenset[int]],
        structural_objects: set[_ObjectIdentity] | frozenset[_ObjectIdentity],
    ) -> None:
        contexts = analysis.marked_contexts
        if contexts[start] != contexts[stop]:
            raise StructureTreeError(
                f"Range [{start}:{stop}) straddles an existing marked-content sequence"
            )
        for _, existing_artifact in contexts[start]:
            if structural and existing_artifact is False:
                raise StructureTreeError(
                    "Tagged marked-content sequences must not be nested"
                )
        for scope in analysis.marked_scopes:
            contains_scope = start <= scope.start and scope.stop <= stop
            if contains_scope and structural and scope.artifact is False:
                raise StructureTreeError(
                    "Tagged marked-content sequences must not be nested"
                )

        for path_start, path_stop in analysis.path_scopes:
            if path_start < start < path_stop or path_start < stop < path_stop:
                raise StructureTreeError(f"Range [{start}:{stop}) splits a path object")

        if analysis.scope_contexts[start] != analysis.scope_contexts[stop]:
            raise StructureTreeError(
                f"Range [{start}:{stop}) straddles a q/Q, BT/ET, or BX/EX pair"
            )

        for instruction in instructions[start:stop]:
            operator = str(instruction.operator)
            if operator != 'Do':
                continue
            operands = list(instruction.operands)
            if len(operands) != 1 or not isinstance(operands[0], Name):
                raise StructureTreeError(
                    "The range contains a malformed Do instruction"
                )
            xobject = _resolve_xobject(resources, operands[0])
            kinds = _xobject_content_kinds(
                xobject,
                top_resources=resources,
                cache=xobject_cache,
                visiting=set(),
                claimed_mcids=claimed_mcids,
                structural_objects=structural_objects,
            )
            if structural and 'structural' in kinds:
                raise StructureTreeError(
                    "The range invokes an XObject that contains structural content"
                )

    def _preflight(
        self,
    ) -> tuple[
        bytes,
        list[tuple[_Span, int]],
        list[MarkedContent],
        _ContentCheckState | None,
        Object | None,
    ]:
        current = list(parse_content_stream(self.page))
        if unparse_content_stream(current) != unparse_content_stream(
            self._instructions
        ):
            raise StructureTreeError(
                "The page content stream changed after this ContentMarker was created"
            )

        target_tree: StructTree | None = None
        target_elements: dict[_ObjectIdentity, StructElem] = {}
        for span in self._spans:
            if span.element is None:
                continue
            if not isinstance(span.element, StructElem):
                raise TypeError("element must be a StructElem or None")
            span.element._require_owned()
            _require_page(self.page, span.element.tree.pdf)
            if target_tree is None:
                target_tree = span.element.tree
            elif not _same_object(target_tree.obj, span.element.tree.obj):
                raise StructureTreeError(
                    "All target elements must belong to the same structure tree"
                )
            target_elements.setdefault(_object_identity(span.element.obj), span.element)

        if target_tree is not None:
            target_tree._preflight_structure_links()
            for element in target_elements.values():
                element._preflight_append_kid(_check_structure=False)

        content_state: _ContentCheckState | None = None
        registration_page: Object | None = None
        parent_tree: ParentTree | None = None
        claimed_mcids: dict[_ObjectIdentity, set[int]] = {}
        structural_objects: set[_ObjectIdentity] = set()
        if target_tree is not None:
            registration_page = _require_page(self.page, target_tree.pdf)
            parent_tree = target_tree.parent_tree
            content_state = parent_tree._content_check_state()
            content_state.validated_containers.add(_object_identity(registration_page))
            for claimant in target_tree._walk_all():
                for ref in _content_references(claimant):
                    if not _same_object(ref.page, registration_page):
                        continue
                    container = ref.stream if ref.stream is not None else ref.page
                    if isinstance(container, Object):
                        claimed_mcids.setdefault(
                            _object_identity(container), set()
                        ).add(ref.mcid)
            structural_objects = {
                _object_identity(referent)
                for referent in _referenced_objects(target_tree._walk_all())
            }

        current_resources = _inherited_page_attribute(self.page, Name.Resources)
        current_analysis = _analyze_marker_content(
            current,
            current_resources,
            claimed_mcids=claimed_mcids.get(
                _object_identity(self.page.obj), frozenset()
            ),
        )
        current_xobject_cache: dict[_XObjectContextKey, frozenset[str]] = {}
        current_mcids = {
            mc.mcid for mc in find_marked_content(self.page) if mc.mcid is not None
        }
        registrations: list[tuple[_Span, int]] = []
        result: list[MarkedContent] = []
        planned_mcids: set[int] = set()
        for span in self._spans:
            self._validate_range_against_content(
                span.start,
                span.stop,
                structural=span.element is not None,
                instructions=current,
                analysis=current_analysis,
                resources=current_resources,
                xobject_cache=current_xobject_cache,
                claimed_mcids=claimed_mcids,
                structural_objects=structural_objects,
            )
            if span.properties is not None:
                _require_direct_object_graph(
                    span.properties, "Marked-content properties"
                )
            raw_mcid = (
                None if span.properties is None else span.properties.get(Name.MCID)
            )
            mcid = _as_int(raw_mcid)
            if span.tag == Name.Artifact:
                if raw_mcid is not None and mcid is None:
                    raise StructureTreeError("Artifact /MCID must be an integer")
            else:
                if mcid is None:
                    raise StructureTreeError(
                        "Tagged content must have an integer marked-content identifier"
                    )
            if mcid is not None:
                _validate_mcid(mcid)
                if mcid in current_mcids:
                    raise StructureTreeError(
                        f"Marked content identifier {mcid} is already used by this page"
                    )
                if mcid in planned_mcids:
                    raise StructureTreeError(
                        f"Marked content identifier {mcid} is requested more than once"
                    )
                planned_mcids.add(mcid)
            if span.tag != Name.Artifact:
                assert mcid is not None
                if span.element is not None:
                    registrations.append((span, mcid))
            result.append(MarkedContent(span.tag, mcid, span.properties))

        resulting_mcids = {mcid for mcid in current_mcids | planned_mcids if mcid >= 0}
        if resulting_mcids and min(resulting_mcids) != 0:
            raise StructureTreeError(
                "Marked content identifiers must start at 0 in a content stream"
            )

        opens: dict[int, list[_Span]] = {}
        closes: dict[int, int] = {}
        for span in self._spans:
            opens.setdefault(span.start, []).append(span)
            closes[span.stop] = closes.get(span.stop, 0) + 1
        for spans in opens.values():
            spans.sort(key=lambda span: (-span.stop, span.order))

        output: list[Any] = []
        for index in range(len(self._instructions) + 1):
            for _ in range(closes.get(index, 0)):
                output.append(ContentStreamInstruction([], Operator('EMC')))
            for span in opens.get(index, []):
                operator = 'BMC' if span.properties is None else 'BDC'
                operands = (
                    [span.tag]
                    if span.properties is None
                    else [span.tag, span.properties]
                )
                output.append(ContentStreamInstruction(operands, Operator(operator)))
            if index < len(self._instructions):
                output.append(self._instructions[index])

        if content_state is not None:
            page_identity = _object_identity(self.page.obj)
            resulting_page_claims = set(claimed_mcids.get(page_identity, set()))
            resulting_page_claims.update(mcid for _, mcid in registrations)
            for wrappers in _form_do_wrappers(
                output,
                current_resources,
                resulting_page_claims,
                source_identity=page_identity,
                top_resources=current_resources,
                claimed_mcids_by_identity=claimed_mcids,
            ).values():
                if len(wrappers) < 2:
                    continue
                claimed_wrappers = [
                    wrapper for wrapper in wrappers if wrapper is not None
                ]
                if claimed_wrappers and (
                    len(claimed_wrappers) != len(wrappers)
                    or len(set(claimed_wrappers)) != len(claimed_wrappers)
                ):
                    raise StructureTreeError(
                        "Repeated Form XObject invocations must each be enclosed "
                        "by a distinct claimed marked-content sequence"
                    )
        serialized = unparse_content_stream(output)

        if registrations:
            assert parent_tree is not None
            assert content_state is not None
            assert registration_page is not None
            for span, mcid in registrations:
                assert span.element is not None
                parent_tree._check_content(
                    self.page.obj,
                    mcid,
                    span.element,
                    _state=content_state,
                )
        return (
            serialized,
            registrations,
            result,
            content_state,
            registration_page,
        )

    @staticmethod
    def _copy_kid_value(value: Object | None) -> Object | None:
        return Array(value) if isinstance(value, Array) else value

    def apply(self) -> list[MarkedContent]:
        """Write the marked content to the page and update the structure tree.

        Replaces the page's content stream with a re-serialized copy that
        includes the new operators, then attaches each sequence created with an
        ``element`` argument to that element.

        Returns:
            The sequences written, in the order they were requested.
        """
        if not self._spans:
            return []
        (
            serialized,
            registrations,
            result,
            content_state,
            registration_page,
        ) = self._preflight()
        had_contents = Name.Contents in self.page.obj
        old_contents = self.page.obj.get(Name.Contents)
        had_struct_parents = Name.StructParents in self.page.obj
        old_struct_parents = self.page.obj.get(Name.StructParents)
        kid_states = {
            span.element.obj.objgen: (
                span.element,
                Name.K in span.element.obj,
                self._copy_kid_value(span.element.obj.get(Name.K)),
            )
            for span, _ in registrations
            if span.element is not None
        }

        parent_tree = None
        if registrations:
            first_element = registrations[0][0].element
            assert first_element is not None
            parent_tree = first_element._tree.parent_tree
        old_key = _as_int(old_struct_parents)
        old_entry_present = False
        old_entry: Object | None = None
        next_key_present = False
        old_next_key: Object | None = None
        had_parent_tree = False
        number_tree: NumberTree | None = None
        if parent_tree is not None:
            root = parent_tree._tree.obj
            had_parent_tree = Name.ParentTree in root
            number_tree = parent_tree._existing_number_tree()
            old_entry_present = (
                old_key is not None
                and number_tree is not None
                and old_key in number_tree
            )
            if old_entry_present:
                assert old_key is not None
                assert number_tree is not None
                old_entry = self._copy_kid_value(number_tree[old_key])
            next_key_present = Name.ParentTreeNextKey in root
            old_next_key = root.get(Name.ParentTreeNextKey)

        try:
            for span, mcid in registrations:
                assert span.element is not None
                assert content_state is not None
                assert registration_page is not None
                span.element._add_content_prechecked(
                    registration_page,
                    mcid,
                    stream_obj=None,
                    state=content_state,
                    prechecked_k=True,
                )
            self.page.obj.Contents = Array([])
            self.page.contents_add(serialized)
            self.page.contents_coalesce()
            new_instructions = list(parse_content_stream(self.page))
        except Exception:
            for element, had_kids, old_kids in kid_states.values():
                if had_kids:
                    assert old_kids is not None
                    element.obj.K = old_kids
                elif Name.K in element.obj:
                    del element.obj[Name.K]
            if parent_tree is not None:
                root = parent_tree._tree.obj
                current_key = _as_int(self.page.obj.get(Name.StructParents))
                if had_parent_tree:
                    assert number_tree is not None
                    if old_key is not None:
                        if old_entry_present:
                            assert old_entry is not None
                            number_tree[old_key] = old_entry
                        elif old_key in number_tree:
                            del number_tree[old_key]
                    elif current_key is not None and current_key in number_tree:
                        del number_tree[current_key]
                elif Name.ParentTree in root:
                    del root[Name.ParentTree]
                if next_key_present:
                    assert old_next_key is not None
                    root.ParentTreeNextKey = old_next_key
                elif Name.ParentTreeNextKey in root:
                    del root[Name.ParentTreeNextKey]
            if had_struct_parents:
                assert old_struct_parents is not None
                self.page.obj.StructParents = old_struct_parents
            elif Name.StructParents in self.page.obj:
                del self.page.obj[Name.StructParents]
            if had_contents:
                assert old_contents is not None
                self.page.obj.Contents = old_contents
            elif Name.Contents in self.page.obj:
                del self.page.obj[Name.Contents]
            raise

        self._spans = []
        self._instructions = new_instructions
        self._resources = _inherited_page_attribute(self.page, Name.Resources)
        self._analysis = _analyze_marker_content(self._instructions, self._resources)
        self._xobject_cache = {}
        self._used_mcids = {
            mc.mcid for mc in find_marked_content(self.page) if mc.mcid is not None
        }
        self._next_mcid = (
            max((mcid for mcid in self._used_mcids if mcid >= 0), default=-1) + 1
        )
        return result


def mark_text_runs(
    page: Page,
    tag_for_font: Mapping[tuple[Name, Decimal], Name]
    | Callable[[FontUsage], Name | None],
    *,
    parent: StructElem | None = None,
) -> list[MarkedContent]:
    """Tag a page's text according to the font it is set in.

    Tracks ``Tf`` font selections across text objects and ``q``/``Q`` graphics
    state save/restore pairs, then marks the text shown with each mapped font.
    Adjacent complete text objects with the same tag are merged, while graphics
    outside text objects are left alone. A font selected through an extended
    graphics state is conservatively left untagged until a later ``Tf``.
    Font selections that map to ``None`` and text with no usable font selection
    are not marked.

    Which font means which tag is the caller's decision; use
    :func:`find_font_usage` to discover what a page contains. For control over
    where sequences begin and end, use :class:`ContentMarker` directly.

    Arguments:
        page: The page to tag.
        tag_for_font: Either a mapping from ``(font, size)`` to a structure
            type, or a callable taking a :class:`FontUsage` and returning a
            structure type or ``None``.
        parent: If given, a child structure element is created under *parent*
            for each marked sequence and wired to it.

    Returns:
        The sequences written, in page order.
    """
    if not isinstance(page, Page):
        raise TypeError("page must be a pikepdf.Page")
    if parent is not None:
        if not isinstance(parent, StructElem):
            raise TypeError("parent must be a StructElem or None")
        parent._require_owned()
        _require_page(page, parent.tree.pdf)
    if callable(tag_for_font):
        resolve = tag_for_font
    else:
        if not isinstance(tag_for_font, Mapping):
            raise TypeError("tag_for_font must be a mapping or callable")
        mapping = tag_for_font

        def resolve(usage: FontUsage) -> Name | None:
            return mapping.get((usage.font, usage.size))

    marker = ContentMarker(page)
    instructions = list(marker.instructions)
    usage_at = {usage.index: usage for usage in find_font_usage(page)}

    runs: list[tuple[int, int, Name]] = []
    font_state: tuple[FontUsage, Name | None] | None = None
    font_stack: list[tuple[FontUsage, Name | None] | None] = []
    text_start: int | None = None
    segment_start: int | None = None
    segment_tag: Name | None = None
    segment_has_text = False
    segments: list[tuple[int, int, Name | None, bool]] = []

    def append_run(start: int, stop: int, tag: Name) -> None:
        if runs and runs[-1][1] == start and runs[-1][2] == tag:
            runs[-1] = (runs[-1][0], stop, tag)
        else:
            runs.append((start, stop, tag))

    def finish_segment(stop: int) -> None:
        nonlocal segment_start, segment_tag, segment_has_text
        if segment_start is not None:
            segments.append((segment_start, stop, segment_tag, segment_has_text))
        segment_start = None
        segment_tag = None
        segment_has_text = False

    def start_segment(start: int) -> None:
        nonlocal segment_start, segment_tag, segment_has_text
        segment_start = start
        segment_tag = None if font_state is None else font_state[1]
        segment_has_text = False

    def select_font(index: int) -> None:
        nonlocal font_state
        usage = usage_at.get(index)
        if usage is None:
            font_state = None
            return
        tag = resolve(usage)
        if tag is not None and not isinstance(tag, Name):
            raise TypeError("Structure type must be a pikepdf.Name")
        if tag == Name.Artifact:
            raise ValueError("Text runs cannot use the /Artifact structure type")
        font_state = (usage, tag)

    def extended_graphics_state_may_set_font(operands: list[Object]) -> bool:
        if len(operands) != 1 or not isinstance(operands[0], Name):
            return True
        if not isinstance(marker._resources, Dictionary):
            return True
        states = marker._resources.get(Name.ExtGState)
        if not isinstance(states, Dictionary):
            return True
        state = states.get(operands[0])
        if not isinstance(state, Dictionary) or isinstance(state, Stream):
            return True
        return Name.Font in state

    for index, instruction in enumerate(instructions):
        operator = str(instruction.operator)
        if operator == 'q':
            if text_start is not None:
                finish_segment(index)
            font_stack.append(font_state)
            if text_start is not None:
                start_segment(index + 1)
            continue
        if operator == 'Q':
            if text_start is not None:
                finish_segment(index)
            font_state = font_stack.pop() if font_stack else None
            if text_start is not None:
                start_segment(index + 1)
            continue
        if operator == 'Tf':
            if text_start is not None:
                finish_segment(index)
            select_font(index)
            if text_start is not None:
                start_segment(index)
            continue
        if operator == 'gs' and extended_graphics_state_may_set_font(
            list(instruction.operands)
        ):
            if text_start is not None:
                finish_segment(index)
            font_state = None
            if text_start is not None:
                start_segment(index)
            continue
        if operator == 'BT':
            text_start = index
            segments = []
            start_segment(index + 1)
            continue
        if text_start is None:
            continue
        if operator in {'Tj', 'TJ', "'", '"'}:
            segment_has_text = True
        elif operator == 'ET':
            finish_segment(index)
            shown = [segment for segment in segments if segment[3]]
            tags = {segment[2] for segment in shown}
            if shown and len(tags) == 1 and None not in tags:
                only_tag = shown[0][2]
                assert isinstance(only_tag, Name)
                append_run(text_start, index + 1, only_tag)
            else:
                for start, stop, tag, has_text in shown:
                    if has_text and tag is not None:
                        append_run(start, stop, tag)
            text_start = None

    if not runs:
        return []

    for start, stop, tag in runs:
        marker.mark(tag, start, stop)

    if parent is None:
        return marker.apply()

    original_spans = marker._spans
    marker._spans = [span._replace(element=parent) for span in original_spans]
    try:
        marker._preflight()
    finally:
        marker._spans = original_spans

    had_parent_k = Name.K in parent.obj
    old_parent_k = ContentMarker._copy_kid_value(parent.obj.get(Name.K))
    try:
        for index, (_, _, tag) in enumerate(runs):
            element = parent.add_child(tag, page=page)
            marker._spans[index] = marker._spans[index]._replace(element=element)
        return marker.apply()
    except Exception:
        if had_parent_k:
            assert old_parent_k is not None
            parent.obj.K = old_parent_k
        elif Name.K in parent.obj:
            del parent.obj[Name.K]
        raise
