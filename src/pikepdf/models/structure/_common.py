# SPDX-FileCopyrightText: 2026 Khushwant Parihar
# SPDX-License-Identifier: MPL-2.0

"""Shared implementation helpers for tagged PDF logical structure."""

from __future__ import annotations

from collections.abc import Callable, Iterator, Mapping
from decimal import Decimal
from functools import wraps
from typing import Any, TypeVar, cast

from pikepdf._core import Page, Pdf
from pikepdf.objects import (
    Array,
    Dictionary,
    Integer,
    Name,
    Object,
    Stream,
    String,
)


class StructureTreeError(Exception):
    """Indicates an error in the logical structure data structure."""


_ObjectKey = tuple[str, int, int]
_ObjectIdentity = tuple[int, int] | int
_XObjectContextKey = tuple[_ObjectIdentity, _ObjectIdentity | None]
_WrapperIdentity = tuple[_ObjectIdentity, int]

# Direct cyclic objects can yield a fresh Python wrapper at every step, so identity
# tracking alone cannot bound these API-facing traversals.
_MAX_OBJECT_GRAPH_CONTAINERS = 10_000
_MAX_OBJECT_GRAPH_DEPTH = 100
_MAX_STRUCTURE_TREE_ELEMENTS = 100_000


def _as_int(value: Any) -> int | None:
    """Return *value* as an ``int``, in either object conversion mode."""
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, Integer):
        return int(value)
    return None


def _as_bool(value: Any) -> bool | None:
    """Return *value* as a PDF boolean, in either object conversion mode."""
    if isinstance(value, bool):
        return value
    if isinstance(value, Object):
        return value.as_bool(None)
    return None


def _validate_mcid(value: Any) -> int:
    return _validate_nonnegative_int(value, "Marked content identifiers")


def _validate_integer(value: Any, description: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{description} must be integers")
    return value


def _validate_nonnegative_int(value: Any, description: str) -> int:
    value = _validate_integer(value, description)
    if value < 0:
        raise ValueError(f"{description} must be non-negative")
    return value


def _as_decimal(value: Any) -> Decimal | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, Decimal):
        return value
    if isinstance(value, int):
        return Decimal(value)
    if isinstance(value, Object):
        try:
            as_integer = value.as_int(None)
            if as_integer is not None:
                return Decimal(as_integer)
            return value.as_decimal(None)
        except (TypeError, ValueError):
            return None
    return None


def _property_list(properties: Mapping[Any, Any] | Dictionary | None) -> Dictionary:
    if properties is None:
        return Dictionary()
    if not isinstance(properties, Mapping | Dictionary):
        raise TypeError("properties must be a mapping or pikepdf.Dictionary")
    result = Dictionary({str(key): value for key, value in properties.items()})
    _require_direct_object_graph(result, "Marked-content properties")
    return result


def _require_direct_object_graph(value: Object, description: str) -> None:
    """Require an object graph that can legally be written inline."""
    pending: list[tuple[Object, int, bool]] = [(value, 0, False)]
    active: list[Object] = []
    completed: set[int] = set()
    containers = 0
    while pending:
        current, depth, exiting = pending.pop()
        if current.is_indirect:
            raise ValueError(f"{description} must not contain indirect objects")
        if isinstance(current, Stream):
            raise ValueError(f"{description} must not contain streams")
        if not isinstance(current, Array | Dictionary):
            continue
        if exiting:
            active.pop()
            completed.add(id(current))
            continue
        if any(_same_graph_node(current, candidate) for candidate in active):
            raise ValueError(f"{description} object graph is cyclic")
        if id(current) in completed:
            continue
        if depth > _MAX_OBJECT_GRAPH_DEPTH:
            raise ValueError(f"{description} object graph is too large")
        containers += 1
        if containers > _MAX_OBJECT_GRAPH_CONTAINERS:
            raise ValueError(f"{description} object graph is too large")
        active.append(current)
        pending.append((current, depth, True))
        if isinstance(current, Array):
            pending.extend(
                (item, depth + 1, False) for item in current if isinstance(item, Object)
            )
        else:
            pending.extend(
                (current[key], depth + 1, False)
                for key in current.keys()
                if isinstance(current[key], Object)
            )


def _same_object(first: Any, second: Any) -> bool:
    """Compare by identity, since ``Object.__eq__`` compares by value."""
    if first is None or second is None:
        return first is second
    if not isinstance(first, Object) or not isinstance(second, Object):
        return first is second
    if first.is_indirect and second.is_indirect:
        return first.same_owner_as(second) and first.objgen == second.objgen
    return first is second


def _same_graph_node(first: Object, second: Object) -> bool:
    """Compare object-graph nodes, including direct-object handle aliases."""
    if first.is_indirect or second.is_indirect:
        return _same_object(first, second)
    try:
        return bool(first == second)
    except Exception:
        return first is second


def _direct_object_graph_references(root: Object, target: Object) -> bool:
    """Return whether *root* directly owns a reference to *target*."""
    pending: list[tuple[Object, int]] = []

    def add_children(value: Object, depth: int) -> None:
        if isinstance(value, Array):
            pending.extend(
                (item, depth + 1) for item in value if isinstance(item, Object)
            )
        elif isinstance(value, Dictionary | Stream):
            pending.extend(
                (value[key], depth + 1)
                for key in value.keys()
                if isinstance(value[key], Object)
            )

    add_children(root, 0)
    seen: set[int] = set()
    containers = 0
    while pending:
        current, depth = pending.pop()
        if _same_object(current, target):
            return True
        if current.is_indirect:
            continue
        if not isinstance(current, Array | Dictionary | Stream):
            continue
        identity = id(current)
        if identity in seen:
            continue
        seen.add(identity)
        containers += 1
        if containers > _MAX_OBJECT_GRAPH_CONTAINERS or depth > _MAX_OBJECT_GRAPH_DEPTH:
            return False
        add_children(current, depth)
    return False


def _object_identity(obj: Object) -> _ObjectIdentity:
    return obj.objgen if obj.is_indirect else id(obj)


def _is_name(value: Any, expected: Name) -> bool:
    """Compare an untrusted PDF object to a name without leaking PdfError."""
    return isinstance(value, Name) and value == expected


def _safe_object_description(value: Any) -> str:
    """Describe an untrusted PDF value without invoking its potentially unsafe repr."""
    kind = type(value).__name__
    if isinstance(value, Object) and value.is_indirect:
        object_number, generation = value.objgen
        return f"{kind} {object_number} {generation}"
    return kind


def _as_page_obj(page: Page | Object | None) -> Object | None:
    if page is None:
        return None
    return page.obj if isinstance(page, Page) else page


def _require_same_owner(
    value: Page | Object, owner: Object, description: str
) -> Object:
    obj = _as_page_obj(value)
    if not isinstance(obj, Object):
        raise TypeError(f"{description} must be a PDF object")
    if not obj.is_indirect:
        raise StructureTreeError(
            f"{description} must be an indirect object belonging to this PDF"
        )
    if not obj.same_owner_as(owner):
        raise StructureTreeError(f"{description} belongs to a different PDF")
    return obj


def _require_owned_indirect(value: Page | Object, pdf: Pdf, description: str) -> Object:
    return _require_same_owner(value, pdf.Root, description)


def _require_page(value: Page | Object, pdf: Pdf) -> Object:
    obj = _require_owned_indirect(value, pdf, "Page")
    if not isinstance(obj, Dictionary) or not _is_name(obj.get(Name.Type), Name.Page):
        raise TypeError("Page must be a PDF page dictionary")
    if not any(_same_object(obj, page.obj) for page in pdf.pages):
        raise StructureTreeError("Page is not in this PDF's page tree")
    return obj


def _require_stream(value: Object, pdf: Pdf) -> Stream:
    if not isinstance(value, Stream):
        raise TypeError("Content stream must be a pikepdf.Stream")
    return cast(Stream, _require_owned_indirect(value, pdf, "Content stream"))


def _require_content_container(value: Page | Object, pdf: Pdf) -> Object:
    obj = _as_page_obj(value)
    assert obj is not None
    if isinstance(obj, Stream):
        return _require_owned_indirect(obj, pdf, "Content stream")
    if isinstance(obj, Dictionary) and _is_name(obj.get(Name.Type), Name.Page):
        return _require_page(obj, pdf)
    raise TypeError("Content container must be a PDF page or pikepdf.Stream")


def _require_referent(value: Object, pdf: Pdf) -> Object:
    if not isinstance(value, Dictionary | Stream):
        raise TypeError("Referenced object must be a Dictionary or Stream")
    return _require_owned_indirect(value, pdf, "Referenced object")


def _require_namespace(value: Object, pdf: Pdf) -> Dictionary:
    if not isinstance(value, Dictionary) or isinstance(value, Stream):
        raise TypeError("namespace must be a namespace Dictionary")
    namespace = _require_owned_indirect(value, pdf, "Namespace")
    assert isinstance(namespace, Dictionary)
    namespace_type = namespace.get(Name.Type)
    if namespace_type is not None and not _is_name(namespace_type, Name.Namespace):
        raise StructureTreeError(
            "Namespace dictionary /Type must be /Namespace when present"
        )
    if not isinstance(namespace.get(Name.NS), String):
        raise StructureTreeError("Namespace dictionary must have a string /NS")
    return namespace


def _require_object_graph_owner(value: Object, pdf: Pdf, description: str) -> None:
    pending: list[tuple[Any, int, bool]] = [(value, 0, False)]
    active: list[Object] = []
    completed: set[_ObjectIdentity] = set()
    containers = 0
    while pending:
        current, depth, exiting = pending.pop()
        if not isinstance(current, Object):
            continue
        if current.is_indirect:
            if not current.same_owner_as(pdf.Root):
                raise StructureTreeError(f"{description} belongs to a different PDF")
            identity: _ObjectIdentity = current.objgen
        else:
            identity = id(current)
        if not isinstance(current, Array | Dictionary | Stream):
            continue
        if exiting:
            active.pop()
            completed.add(identity)
            continue
        if any(_same_graph_node(current, candidate) for candidate in active):
            raise StructureTreeError(f"{description} object graph is cyclic")
        if identity in completed:
            continue
        if depth > _MAX_OBJECT_GRAPH_DEPTH:
            raise StructureTreeError(f"{description} object graph is too large")
        containers += 1
        if containers > _MAX_OBJECT_GRAPH_CONTAINERS:
            raise StructureTreeError(f"{description} object graph is too large")
        active.append(current)
        pending.append((current, depth, True))
        if isinstance(current, Array):
            pending.extend((item, depth + 1, False) for item in current)
        elif isinstance(current, Dictionary | Stream):
            pending.extend((current[key], depth + 1, False) for key in current.keys())


def _require_attributes(value: Object, pdf: Pdf) -> None:
    if isinstance(value, Dictionary | Stream):
        if not isinstance(value.get(Name.O), Name):
            raise TypeError("attribute objects must contain a name-valued /O")
        _require_object_graph_owner(value, pdf, "Attributes")
        return
    if not isinstance(value, Array) or len(value) == 0:
        raise TypeError(
            "attributes must be a Dictionary, Stream, or a valid attribute Array"
        )
    may_have_revision = False
    for item in value:
        if isinstance(item, Dictionary | Stream):
            if not isinstance(item.get(Name.O), Name):
                raise TypeError("attribute objects must contain a name-valued /O")
            may_have_revision = True
            continue
        revision = _as_int(item)
        if revision is None or revision < 0 or not may_have_revision:
            raise TypeError(
                "attributes must be a Dictionary, Stream, or a valid attribute Array"
            )
        may_have_revision = False
    _require_object_graph_owner(value, pdf, "Attributes")


def _inherited_page_attribute(page: Page | Object, key: Name) -> Object | None:
    """Return an inheritable page attribute without modifying the page tree."""
    current = _as_page_obj(page)
    seen: set[tuple[int, int] | int] = set()
    while isinstance(current, Dictionary):
        identity: tuple[int, int] | int = (
            current.objgen if current.is_indirect else id(current)
        )
        if identity in seen:
            return None
        seen.add(identity)
        if key in current:
            return current.get(key)
        parent = current.get(Name.Parent)
        current = parent if isinstance(parent, Dictionary) else None
    return None


def _kid_items(value: Object | None) -> Iterator[Object]:
    """Iterate the entries of a ``/K`` value, which may or may not be an array."""
    if value is None:
        return
    if isinstance(value, Array):
        yield from value
    else:
        yield value


def _is_struct_elem(obj: Any) -> bool:
    if not isinstance(obj, Dictionary):
        return False
    obj_type = obj.get(Name.Type)
    if obj_type is not None:
        return _is_name(obj_type, Name.StructElem)
    return Name.S in obj


def _effective_page_obj(elem_obj: Dictionary) -> Object | None:
    """Return the nearest ``/Pg`` on an element or its structure ancestors."""
    current: Dictionary | None = elem_obj
    seen: set[tuple[int, int] | int] = set()
    while current is not None:
        identity: tuple[int, int] | int = (
            current.objgen if current.is_indirect else id(current)
        )
        if identity in seen:
            return None
        seen.add(identity)
        page = current.get(Name.Pg)
        if page is not None:
            return page
        parent = current.get(Name.P)
        current = (
            cast(Dictionary, parent)
            if isinstance(parent, Dictionary) and _is_struct_elem(parent)
            else None
        )
    return None


def _appearance_dictionary_references_stream(owner: Dictionary, stream: Stream) -> bool:
    appearances = owner.get(Name.AP)
    if not isinstance(appearances, Dictionary) or isinstance(appearances, Stream):
        return False
    for appearance_type in (Name.N, Name.R, Name.D):
        appearance = appearances.get(appearance_type)
        if isinstance(appearance, Stream):
            if _same_object(appearance, stream):
                return True
        elif isinstance(appearance, Dictionary):
            if any(
                isinstance(appearance[state], Stream)
                and _same_object(appearance[state], stream)
                for state in appearance.keys()
            ):
                return True
    return False


def _stream_owner_references_stream(
    owner: Object, stream: Stream, pdf: Pdf | None = None
) -> bool:
    """Check a ``/StmOwn`` link using the owner's PDF semantics."""
    appearance_references_stream = (
        isinstance(owner, Dictionary)
        and not isinstance(owner, Stream)
        and _appearance_dictionary_references_stream(owner, stream)
    )
    is_annotation = (
        isinstance(owner, Dictionary)
        and not isinstance(owner, Stream)
        and (
            _is_name(owner.get(Name.Type), Name.Annot)
            or (pdf is not None and _is_page_annotation(pdf, owner))
        )
    )
    if is_annotation:
        return appearance_references_stream
    if appearance_references_stream:
        return True
    return _direct_object_graph_references(owner, stream)


def _page_has_annotation(page: Object, annotation: Object) -> bool:
    annots = page.get(Name.Annots)
    return isinstance(annots, Array) and any(
        isinstance(candidate, Dictionary) and _same_object(candidate, annotation)
        for candidate in annots
    )


def _is_page_annotation(pdf: Pdf, annotation: Object) -> bool:
    return any(_page_has_annotation(page.obj, annotation) for page in pdf.pages)


def _form_xobjects(resources: Object | None) -> Iterator[Stream]:
    """Walk Form XObjects reachable through nested resource dictionaries."""
    pending = [resources]
    seen: set[tuple[int, int] | int] = set()
    while pending:
        current = pending.pop()
        if not isinstance(current, Dictionary):
            continue
        xobjects = current.get(Name.XObject)
        if not isinstance(xobjects, Dictionary):
            continue
        for name in xobjects.keys():
            xobject = xobjects[name]
            if not isinstance(xobject, Stream) or not _is_name(
                xobject.get(Name.Subtype), Name.Form
            ):
                continue
            identity: tuple[int, int] | int = (
                xobject.objgen if xobject.is_indirect else id(xobject)
            )
            if identity in seen:
                continue
            seen.add(identity)
            yield xobject
            pending.append(xobject.get(Name.Resources))


_F = TypeVar('_F', bound=Callable[..., Any])


def _locked(method: _F) -> _F:
    """Hold the owning ``Pdf``'s lock for the duration of a mutating method.

    Structure edits are multi-step read-modify-write sequences across ``/K``,
    ``/StructParents`` and the parent tree, which are not atomic on a
    free-threaded interpreter. The lock is re-entrant and compiles to nothing
    on GIL-enabled builds, so nesting these calls is free.
    """

    @wraps(method)
    def wrapper(self, *args: Any, **kwargs: Any):
        pdf = self._lock_pdf
        if pdf is None:
            # No owning Pdf is reachable (pikepdf exposes no owner accessor on
            # Page). The remaining writes are single C++ calls, which are
            # already serialized.
            return method(self, *args, **kwargs)
        with pdf.lock():
            return method(self, *args, **kwargs)

    return cast('_F', wrapper)
