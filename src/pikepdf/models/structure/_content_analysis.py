# SPDX-FileCopyrightText: 2026 Khushwant Parihar
# SPDX-License-Identifier: MPL-2.0

"""Content-stream analysis used by tagged PDF structure operations."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any, NamedTuple

from pikepdf._core import Page, Pdf
from pikepdf.models._content_stream import parse_content_stream
from pikepdf.models.structure._common import (
    StructureTreeError,
    _as_int,
    _inherited_page_attribute,
    _is_name,
    _object_identity,
    _ObjectIdentity,
    _WrapperIdentity,
    _XObjectContextKey,
)
from pikepdf.objects import (
    Dictionary,
    Name,
    Object,
    Stream,
)

# Operators that open and close a nesting level a marked-content sequence may
# not straddle: graphics-state scopes, text objects, and compatibility sections.
_SCOPE_PAIRS = {'q': 'Q', 'BT': 'ET', 'BX': 'EX'}
_SCOPE_CLOSE_TO_OPEN = {closer: opener for opener, closer in _SCOPE_PAIRS.items()}
_OPEN_OPERATORS = frozenset(_SCOPE_PAIRS)
_CLOSE_OPERATORS = frozenset(_SCOPE_CLOSE_TO_OPEN)
_PATH_CLIPPING_OPERATORS = frozenset({'W', 'W*'})
_PATH_CONSTRUCTION_OPERATORS = frozenset({'l', 'c', 'v', 'y', 'h'})
_PATH_END_OPERATORS = frozenset({'S', 's', 'f', 'F', 'f*', 'B', 'B*', 'b', 'b*', 'n'})


def _path_object_scopes(instructions: list[Any]) -> list[tuple[int, int]]:
    scopes = []
    start = None
    for index, instruction in enumerate(instructions):
        operator = str(instruction.operator)
        if operator in {'m', 're'}:
            if start is None:
                start = index
        elif (
            operator in _PATH_CONSTRUCTION_OPERATORS
            or operator in _PATH_CLIPPING_OPERATORS
        ):
            if start is None:
                raise StructureTreeError(
                    f"Path operator {operator} appears outside a path object"
                )
        elif operator in _PATH_END_OPERATORS and start is not None:
            scopes.append((start, index + 1))
            start = None
    if start is not None:
        raise StructureTreeError(
            "The content stream contains an unterminated path object"
        )
    return scopes


class _MarkedScope(NamedTuple):
    start: int
    stop: int
    artifact: bool | None


class _ScopeFrame(NamedTuple):
    operator: str
    opened_at: int


class _MarkerAnalysis(NamedTuple):
    marked_contexts: list[tuple[tuple[int, bool | None], ...]]
    marked_scopes: list[_MarkedScope]
    scope_contexts: list[tuple[_ScopeFrame, ...]]
    path_scopes: list[tuple[int, int]]


def _marked_content_kind(
    operator: str,
    operands: list[Object],
    resources: Object | None,
    claimed_mcids: set[int] | frozenset[int] = frozenset(),
) -> bool | None:
    """Return True for artifact, False for structural, or None for other."""
    expected_arity = 1 if operator == 'BMC' else 2
    if len(operands) != expected_arity or not isinstance(operands[0], Name):
        return None
    if operands[0] == Name.Artifact:
        return True
    if operator != 'BDC':
        return None
    properties: Object | None = operands[1]
    named_properties = (
        resources.get(Name.Properties) if isinstance(resources, Dictionary) else None
    )
    if isinstance(properties, Name) and isinstance(named_properties, Dictionary):
        properties = named_properties.get(properties)
    if (
        isinstance(properties, Dictionary)
        and _as_int(properties.get(Name.MCID)) in claimed_mcids
    ):
        return False
    return None


def _analyze_marker_content(
    instructions: list[Any],
    resources: Object | None,
    *,
    claimed_mcids: set[int] | frozenset[int] = frozenset(),
) -> _MarkerAnalysis:
    marked_contexts: list[tuple[tuple[int, bool | None], ...]] = []
    marked_stack: list[tuple[int, bool | None]] = []
    marked_scopes: list[_MarkedScope] = []
    scope_contexts: list[tuple[_ScopeFrame, ...]] = []
    scope_stack: list[_ScopeFrame] = []
    for index, instruction in enumerate(instructions):
        marked_contexts.append(tuple(marked_stack))
        scope_contexts.append(tuple(scope_stack))
        operator = str(instruction.operator)
        if operator in {'BMC', 'BDC'}:
            kind = _marked_content_kind(
                operator,
                list(instruction.operands),
                resources,
                claimed_mcids,
            )
            marked_stack.append((index, kind))
        elif operator == 'EMC':
            if not marked_stack:
                raise StructureTreeError(
                    "The content stream contains an unmatched EMC operator"
                )
            opened, artifact = marked_stack.pop()
            marked_scopes.append(_MarkedScope(opened, index + 1, artifact))

        if operator in _OPEN_OPERATORS:
            scope_stack.append(_ScopeFrame(operator, index))
        elif operator in _CLOSE_OPERATORS:
            expected = _SCOPE_CLOSE_TO_OPEN[operator]
            if not scope_stack or scope_stack[-1].operator != expected:
                raise StructureTreeError(
                    f"The content stream contains an unmatched {operator} operator"
                )
            scope_stack.pop()

    marked_contexts.append(tuple(marked_stack))
    scope_contexts.append(tuple(scope_stack))
    if marked_stack:
        raise StructureTreeError(
            "The content stream contains an unclosed BMC or BDC operator"
        )
    if scope_stack:
        opener = scope_stack[-1].operator
        closer = _SCOPE_PAIRS[opener]
        raise StructureTreeError(
            f"The content stream contains an unclosed {opener}/{closer} scope"
        )
    return _MarkerAnalysis(
        marked_contexts,
        marked_scopes,
        scope_contexts,
        _path_object_scopes(instructions),
    )


def _resource_identity(resources: Object | None) -> _ObjectIdentity | None:
    return _object_identity(resources) if isinstance(resources, Object) else None


def _resolve_xobject(resources: Object | None, name: Name) -> Stream:
    if not isinstance(resources, Dictionary):
        raise StructureTreeError(f"Cannot resolve {name} Do without /Resources")
    xobjects = resources.get(Name.XObject)
    if not isinstance(xobjects, Dictionary):
        raise StructureTreeError(f"Cannot resolve {name} Do without /XObject resources")
    target = xobjects.get(name)
    if not isinstance(target, Stream):
        raise StructureTreeError(f"{name} Do does not resolve to an XObject stream")
    return target


def _xobject_content_kinds(
    xobject: Stream,
    *,
    top_resources: Object | None,
    cache: dict[_XObjectContextKey, frozenset[str]],
    visiting: set[_XObjectContextKey],
    claimed_mcids: Mapping[_ObjectIdentity, set[int] | frozenset[int]],
    structural_objects: set[_ObjectIdentity] | frozenset[_ObjectIdentity],
) -> frozenset[str]:
    kinds: set[str] = set()
    xobject_identity = _object_identity(xobject)
    if xobject_identity in structural_objects:
        kinds.add('structural')
    if not _is_name(xobject.get(Name.Subtype), Name.Form):
        return frozenset(kinds)

    raw_resources = xobject.get(Name.Resources)
    if Name.Resources in xobject and not isinstance(raw_resources, Dictionary):
        raise StructureTreeError("Form XObject /Resources must be a dictionary")
    effective_resources = (
        raw_resources if isinstance(raw_resources, Dictionary) else top_resources
    )
    key = (_object_identity(xobject), _resource_identity(top_resources))
    if key in cache:
        return frozenset(kinds | set(cache[key]))
    if key in visiting:
        raise StructureTreeError("Cyclic Form XObject invocation cannot be marked")
    visiting.add(key)
    try:
        try:
            instructions = list(parse_content_stream(xobject))
        except Exception as exc:
            raise StructureTreeError("Cannot parse a referenced Form XObject") from exc
        for instruction in instructions:
            operator = str(instruction.operator)
            operands = list(instruction.operands)
            if operator in {'BMC', 'BDC'}:
                kind = _marked_content_kind(
                    operator,
                    operands,
                    effective_resources,
                    claimed_mcids.get(xobject_identity, frozenset()),
                )
                if kind is True:
                    kinds.add('artifact')
                elif kind is False:
                    kinds.add('structural')
            elif operator == 'Do':
                if len(operands) != 1 or not isinstance(operands[0], Name):
                    raise StructureTreeError(
                        "A Form XObject contains a malformed Do instruction"
                    )
                nested = _resolve_xobject(effective_resources, operands[0])
                kinds.update(
                    _xobject_content_kinds(
                        nested,
                        top_resources=top_resources,
                        cache=cache,
                        visiting=visiting,
                        claimed_mcids=claimed_mcids,
                        structural_objects=structural_objects,
                    )
                )
    finally:
        visiting.remove(key)
    result = frozenset(kinds)
    cache[key] = result
    return result


def _form_do_wrappers(
    instructions: Iterable[Any],
    resources: Object | None,
    claimed_mcids: set[int] | frozenset[int],
    *,
    source_identity: _ObjectIdentity,
    top_resources: Object | None = None,
    claimed_mcids_by_identity: Mapping[_ObjectIdentity, set[int] | frozenset[int]]
    | None = None,
) -> dict[_ObjectIdentity, list[_WrapperIdentity | None]]:
    """Collect claimed wrappers for every reachable Form ``Do`` execution."""
    result: dict[_ObjectIdentity, list[_WrapperIdentity | None]] = {}
    nested_claims = (
        {} if claimed_mcids_by_identity is None else claimed_mcids_by_identity
    )
    page_resources = resources if top_resources is None else top_resources
    pending: list[
        tuple[
            _ObjectIdentity,
            list[Any],
            Object | None,
            _WrapperIdentity | None,
        ]
    ] = [(source_identity, list(instructions), resources, None)]
    scheduled: dict[tuple[_ObjectIdentity, _WrapperIdentity | None], int] = {
        (source_identity, None): 1
    }
    while pending:
        current_identity, current, current_resources, inherited_wrapper = pending.pop()
        current_claims = (
            claimed_mcids
            if current_identity == source_identity
            else nested_claims.get(current_identity, frozenset())
        )
        marked_scopes: list[tuple[int, bool]] = []
        for index, instruction in enumerate(current):
            operator = str(instruction.operator)
            operands = list(instruction.operands)
            if operator == 'BMC':
                marked_scopes.append((index, False))
                continue
            if operator == 'BDC':
                marked_scopes.append(
                    (
                        index,
                        _marked_content_kind(
                            operator,
                            operands,
                            current_resources,
                            current_claims,
                        )
                        is False,
                    )
                )
                continue
            if operator == 'EMC':
                if marked_scopes:
                    marked_scopes.pop()
                continue
            if (
                operator != 'Do'
                or len(operands) != 1
                or not isinstance(operands[0], Name)
            ):
                continue
            try:
                target = _resolve_xobject(current_resources, operands[0])
            except StructureTreeError:
                continue
            if not _is_name(target.get(Name.Subtype), Name.Form):
                continue
            local_wrapper = next(
                (
                    (current_identity, opened_at)
                    for opened_at, is_structural in reversed(marked_scopes)
                    if is_structural
                ),
                None,
            )
            wrapper = local_wrapper if local_wrapper is not None else inherited_wrapper
            target_identity = _object_identity(target)
            result.setdefault(target_identity, []).append(wrapper)
            raw_resources = target.get(Name.Resources)
            if Name.Resources in target and not isinstance(raw_resources, Dictionary):
                continue
            target_resources = (
                raw_resources
                if isinstance(raw_resources, Dictionary)
                else page_resources
            )
            execution_key = (target_identity, wrapper)
            count = scheduled.get(execution_key, 0)
            if count >= 2:
                continue
            try:
                target_instructions = list(parse_content_stream(target))
            except Exception:
                continue
            scheduled[execution_key] = count + 1
            pending.append(
                (target_identity, target_instructions, target_resources, wrapper)
            )
    return result


def _observed_form_execution_count(pdf: Pdf, target: Stream) -> int:
    """Return zero, one, or at least two observed ``Do`` executions of *target*."""
    target_identity = _object_identity(target)
    count = 0
    for page in pdf.pages:
        resources = _inherited_page_attribute(page, Name.Resources)
        try:
            instructions = list(parse_content_stream(page))
        except Exception:
            continue
        executions = _form_do_wrappers(
            instructions,
            resources,
            frozenset(),
            source_identity=_object_identity(page.obj),
            top_resources=resources,
        )
        count += len(executions.get(target_identity, ()))
        if count > 1:
            return 2
    return count


def _claims_create_structural_nesting(
    source: Page | Object,
    resources: Object | None,
    claimed_mcids: set[int] | frozenset[int],
) -> bool:
    """Return whether *claimed_mcids* make nested structural scopes in *source*."""
    try:
        instructions = parse_content_stream(source)
    except Exception:
        return False
    structural_stack: list[bool] = []
    for instruction in instructions:
        operator = str(getattr(instruction, "operator", ""))
        operands = list(getattr(instruction, "operands", ()))
        if operator == 'BMC':
            structural_stack.append(False)
            continue
        if operator == 'BDC':
            is_structural = (
                _marked_content_kind(
                    operator,
                    operands,
                    resources,
                    claimed_mcids,
                )
                is False
            )
            if is_structural and any(structural_stack):
                return True
            structural_stack.append(is_structural)
            continue
        if operator == 'EMC' and structural_stack:
            structural_stack.pop()
    return False
