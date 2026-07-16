# SPDX-FileCopyrightText: 2022 James R. Barlow, 2020 Matthias Erll

# SPDX-License-Identifier: MPL-2.0

"""Support for document outlines (e.g. table of contents)."""

from __future__ import annotations

from collections.abc import Iterable
from enum import Enum, IntFlag
from itertools import chain
from typing import TYPE_CHECKING, cast

from pikepdf._core import Page, Pdf
from pikepdf.objects import Array, Dictionary, Name, Object, String

if TYPE_CHECKING:
    from pikepdf.models.actions import Action


class PageLocation(Enum):
    """Page view location definitions, from PDF spec."""

    XYZ = 1
    Fit = 2
    FitH = 3
    FitV = 4
    FitR = 5
    FitB = 6
    FitBH = 7
    FitBV = 8


PAGE_LOCATION_ARGS = {
    PageLocation.XYZ: ('left', 'top', 'zoom'),
    PageLocation.FitH: ('top',),
    PageLocation.FitV: ('left',),
    PageLocation.FitR: ('left', 'bottom', 'right', 'top'),
    PageLocation.FitBH: ('top',),
    PageLocation.FitBV: ('left',),
}
ALL_PAGE_LOCATION_KWARGS = set(chain.from_iterable(PAGE_LOCATION_ARGS.values()))


class OutlineItemFlag(IntFlag):
    """Style flags for an outline item's displayed text, from PDF spec 12.3.3."""

    NONE = 0
    Italic = 1
    Bold = 2


def make_page_destination(
    pdf: Pdf,
    page_num: int,
    page_location: PageLocation | str | None = None,
    *,
    left: float | None = None,
    top: float | None = None,
    right: float | None = None,
    bottom: float | None = None,
    zoom: float | None = None,
) -> Array:
    """Create a destination ``Array`` with reference to a Pdf document's page number.

    Arguments:
        pdf: PDF document object.
        page_num: Page number (zero-based).
        page_location: Optional page location, as a string or :class:`PageLocation`.
        left: Specify page viewport rectangle.
        top: Specify page viewport rectangle.
        right: Specify page viewport rectangle.
        bottom: Specify page viewport rectangle.
        zoom: Specify page viewport rectangle's zoom level.

    left, top, right, bottom, zoom are used in conjunction with the page fit style
    specified by *page_location*.
    """
    return _make_page_destination(
        pdf,
        page_num,
        page_location=page_location,
        left=left,
        top=top,
        right=right,
        bottom=bottom,
        zoom=zoom,
    )


def _resolve_page_location(
    page_location: PageLocation | str,
) -> tuple[PageLocation, str]:
    """Resolve a :class:`PageLocation` or its name string to a canonical pair."""
    if isinstance(page_location, PageLocation):
        return page_location, page_location.name
    loc_str = page_location
    try:
        loc_key = PageLocation[loc_str]
    except KeyError:
        raise ValueError(
            f"Invalid or unsupported page location type {loc_str}"
        ) from None
    return loc_key, loc_str


def _build_destination_array(
    page: Object, loc_key: PageLocation, values: dict[str, float | None]
) -> Array:
    """Build a destination ``Array`` from a resolved page location and its args.

    Unlike ``_make_page_destination``, a value of ``None`` in *values* is
    written through as a PDF null (12.3.2.2: retains the viewer's current
    value), not defaulted to ``0``.
    """
    res: list = [page, Name(f'/{loc_key.name}')]
    dest_arg_names = PAGE_LOCATION_ARGS.get(loc_key)
    if dest_arg_names:
        res.extend(values.get(k) for k in dest_arg_names)
    return Array(res)


def _make_page_destination(
    pdf: Pdf,
    page_num: int,
    page_location: PageLocation | str | None = None,
    **kwargs,
) -> Array:
    kwargs = {k: v for k, v in kwargs.items() if v is not None}
    page_obj = pdf.pages[page_num].obj
    if page_location:
        loc_key, _ = _resolve_page_location(page_location)
        dest_arg_names = PAGE_LOCATION_ARGS.get(loc_key, ())
        values = {k: kwargs.get(k, 0) for k in dest_arg_names}
        return _build_destination_array(page_obj, loc_key, values)
    return _build_destination_array(page_obj, PageLocation.Fit, {})


class Destination:
    """Parse and build explicit destination arrays (PDF spec 12.3.2.2).

    Unlike :func:`make_page_destination`, which only builds a destination
    array from scratch, ``Destination`` can also parse an existing
    destination array (e.g. from ``OutlineItem.destination``) into named
    accessors for its page, fit type, and viewport parameters.

    Arguments:
        page: The page object (or page number, for remote/embedded
            destinations where the spec uses an integer) this destination
            refers to.
        page_location: The fit type, e.g. :attr:`PageLocation.Fit`. Defaults
            to :attr:`PageLocation.Fit` if not given.
        left, top, right, bottom, zoom: Viewport parameters applicable to
            *page_location*. An explicit ``None`` is written as a PDF null,
            meaning "retain the viewer's current value" per 12.3.2.2.
    """

    def __init__(
        self,
        page: Object,
        page_location: PageLocation | str | None = None,
        *,
        left: float | None = None,
        top: float | None = None,
        right: float | None = None,
        bottom: float | None = None,
        zoom: float | None = None,
    ):
        """Initialize Destination."""
        self.page = page
        if page_location is None:
            self.page_location = PageLocation.Fit
        else:
            self.page_location, _ = _resolve_page_location(page_location)
        self.left = left
        self.top = top
        self.right = right
        self.bottom = bottom
        self.zoom = zoom

    @property
    def fit_type(self) -> PageLocation:
        """The destination's fit type. Alias for ``page_location``."""
        return self.page_location

    @classmethod
    def from_array(cls, array: Array, *, strict: bool = False) -> Destination:
        """Parse an existing destination ``Array`` into a ``Destination``.

        Arguments:
            array: The destination array, e.g. from ``OutlineItem.destination``.
            strict: If ``True``, raise :class:`OutlineStructureError` on an
                unrecognized fit type name. If ``False`` (default), default
                to :attr:`PageLocation.Fit`.
        """
        if len(array) == 0:
            raise OutlineStructureError("Destination array is empty")
        page = array[0]
        if len(array) < 2:
            return cls(page)
        loc_name = array[1]
        loc_str = str(loc_name)[1:] if isinstance(loc_name, Name) else str(loc_name)
        try:
            page_location = PageLocation[loc_str]
        except KeyError:
            if strict:
                raise OutlineStructureError(
                    f"Unrecognized destination fit type: {loc_name!r}"
                ) from None
            page_location = PageLocation.Fit
        arg_names = PAGE_LOCATION_ARGS.get(page_location, ())
        arg_values = list(array[2:])
        kwargs = {
            name: (None if value is None else float(value))
            for name, value in zip(arg_names, arg_values)
        }
        return cls(page, page_location, **kwargs)

    def to_array(self) -> Array:
        """Build the destination ``Array`` for this ``Destination``."""
        values = {
            'left': self.left,
            'top': self.top,
            'right': self.right,
            'bottom': self.bottom,
            'zoom': self.zoom,
        }
        return _build_destination_array(self.page, self.page_location, values)

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Destination):
            return NotImplemented
        return (
            self.page == other.page
            and self.page_location == other.page_location
            and self.left == other.left
            and self.top == other.top
            and self.right == other.right
            and self.bottom == other.bottom
            and self.zoom == other.zoom
        )

    def __repr__(self):
        return (
            f'<pikepdf.Destination: page={self.page!r} '
            f'page_location={self.page_location!r}>'
        )


class OutlineStructureError(Exception):
    """Indicates an error in the outline data structure."""


class OutlineItem:
    """Manage a single item in a PDF document outlines structure.

    Includes nested items.

    Arguments:
        title: Title of the outlines item.
        destination: Page number, destination name, or any other PDF object
            to be used as a reference when clicking on the outlines entry. Note
            this should be ``None`` if an action is used instead. If set to a
            page number, it will be resolved to a reference at the time of
            writing the outlines back to the document.
        page_location: Supplemental page location for a page number
            in ``destination``, e.g. ``PageLocation.Fit``. May also be
            a simple string such as ``'FitH'``.
        action: Action to perform when clicking on this item. Will be ignored
           during writing if ``destination`` is also set.
        obj: ``Dictionary`` object representing this outlines item in a ``Pdf``.
            May be ``None`` for creating a new object. If present, an existing
            object is modified in-place during writing and original attributes
            are retained.
        left, top, bottom, right, zoom: Describes the viewport position associated
            with a destination.
        color: The color, as an RGB tuple with each component in ``0.0`` to
            ``1.0``, used to display the outline item's text. If ``None``
            (default), no ``/C`` entry is written and viewers use black.
        flags: Style flags (:class:`OutlineItemFlag`) for displaying the
            outline item's text, e.g. italic or bold.
        structure_element: The structure element (:attr:`Object`) that this
            item refers to, for tagged PDF/accessibility purposes. Per PDF
            spec, this is not intended for navigation.

    This object does not contain any information about higher-level or
    neighboring elements.

    Valid destination arrays:
        [page /XYZ left top zoom]
        generally
        [page, PageLocationEntry, 0 to 4 ints]
    """

    def __init__(
        self,
        title: str,
        destination: Array | String | Name | int | None = None,
        page_location: PageLocation | str | None = None,
        action: Dictionary | None = None,
        obj: Dictionary | None = None,
        *,
        left: float | None = None,
        top: float | None = None,
        right: float | None = None,
        bottom: float | None = None,
        zoom: float | None = None,
        color: tuple[float, float, float] | None = None,
        flags: OutlineItemFlag = OutlineItemFlag.NONE,
        structure_element: Object | None = None,
    ):
        """Initialize OutlineItem."""
        self.title = title
        if isinstance(destination, Destination):
            destination = destination.to_array()
        self.destination = destination
        self.page_location = page_location
        self.page_location_kwargs = {}
        if action is not None and not isinstance(action, Dictionary):
            from pikepdf.models.actions import Action as _Action

            if isinstance(action, _Action):
                action = action.obj
        self.action = action
        if self.destination is not None and self.action is not None:
            raise ValueError("Only one of destination and action may be set")
        self.obj = obj
        kwargs = dict(left=left, top=top, right=right, bottom=bottom, zoom=zoom)
        self.page_location_kwargs = {k: v for k, v in kwargs.items() if v is not None}
        self.is_closed = False
        self.children: list[OutlineItem] = []
        self.color = color
        self.flags = flags
        self.structure_element = structure_element

    @property
    def italic(self) -> bool:
        """Whether the outline item's text is displayed in italic."""
        return bool(self.flags & OutlineItemFlag.Italic)

    @italic.setter
    def italic(self, value: bool) -> None:
        if value:
            self.flags |= OutlineItemFlag.Italic
        else:
            self.flags &= ~OutlineItemFlag.Italic

    @property
    def bold(self) -> bool:
        """Whether the outline item's text is displayed in bold."""
        return bool(self.flags & OutlineItemFlag.Bold)

    @bold.setter
    def bold(self, value: bool) -> None:
        if value:
            self.flags |= OutlineItemFlag.Bold
        else:
            self.flags &= ~OutlineItemFlag.Bold

    def __str__(self):
        if self.children:
            if self.is_closed:
                oc_indicator = '[+]'
            else:
                oc_indicator = '[-]'
        else:
            oc_indicator = '[ ]'
        if self.destination is not None:
            if isinstance(self.destination, Array):
                # 12.3.2.2 Explicit destination
                # [raw_page, /PageLocation.SomeThing, integer parameters for viewport]
                raw_page = self.destination[0]
                page = Page(raw_page)
                dest = page.label
            elif isinstance(self.destination, String):
                # 12.3.2.2 Named destination, byte string reference to Names
                dest = (
                    f"<Named Destination in document .Root.Names dictionary: "
                    f"{self.destination}>"
                )
            elif isinstance(self.destination, Name):
                # 12.3.2.2 Named destination, name object (PDF 1.1)
                dest = (
                    f"<Named Destination in document .Root.Dests dictionary: "
                    f"{self.destination}>"
                )
            elif isinstance(self.destination, int):
                # Page number
                dest = f'<Page {self.destination}>'
        else:
            dest = '<Action>'
        return f'{oc_indicator} {self.title} -> {dest}'

    def __repr__(self):
        return f'<pikepdf.{self.__class__.__name__}: "{self.title}">'

    @classmethod
    def from_dictionary_object(cls, obj: Dictionary, *, strict: bool = False):
        """Create a ``OutlineItem`` from a ``Dictionary``.

        Does not process nested items.

        Arguments:
            obj: ``Dictionary`` object representing a single outline node.
            strict: If ``True``, raise :class:`OutlineStructureError` on any
                structural problem (such as a missing required ``/Title``).
                If ``False`` (default), quietly correct such problems where the
                repair is known; a missing ``/Title`` becomes an empty string.
        """
        try:
            title = str(obj.Title)
        except AttributeError as e:
            # 12.3.3: /Title is required, but some real-world PDFs omit it.
            if strict:
                raise OutlineStructureError(
                    "Outline node is missing required /Title"
                ) from e
            title = ""
        destination = obj.get(Name.Dest)
        if destination is not None and not isinstance(
            destination, Array | String | Name
        ):
            # 12.3.3: /Dest may be a name, byte string or array
            raise OutlineStructureError(
                f"Unexpected object type in Outline's /Dest: {destination!r}"
            )
        action = obj.get(Name.A)
        if action is not None and not isinstance(action, Dictionary):
            raise OutlineStructureError(
                f"Unexpected object type in Outline's /A: {action!r}"
            )

        color = None
        c_val = obj.get(Name.C)
        if c_val is not None:
            if isinstance(c_val, Array) and len(c_val) == 3:
                try:
                    color = (float(c_val[0]), float(c_val[1]), float(c_val[2]))
                except (TypeError, ValueError) as e:
                    if strict:
                        raise OutlineStructureError(
                            f"Malformed values in Outline's /C: {c_val!r}"
                        ) from e
            elif strict:
                raise OutlineStructureError(
                    f"Unexpected object type in Outline's /C: {c_val!r}"
                )

        flags = OutlineItemFlag.NONE
        f_val = obj.get(Name.F)
        if f_val is not None:
            if isinstance(f_val, int):
                flags = OutlineItemFlag(f_val)
            elif strict:
                raise OutlineStructureError(
                    f"Unexpected object type in Outline's /F: {f_val!r}"
                )

        structure_element = obj.get(Name.SE)

        return cls(
            title,
            destination=destination,
            action=action,
            obj=obj,
            color=color,
            flags=flags,
            structure_element=structure_element,
        )

    def to_dictionary_object(self, pdf: Pdf, create_new: bool = False) -> Dictionary:
        """Create/update a ``Dictionary`` object from this outline node.

        Page numbers are resolved to a page reference on the input
        ``Pdf`` object.

        Arguments:
            pdf: PDF document object.
            create_new: If set to ``True``, creates a new object instead of
                modifying an existing one in-place.
        """
        if create_new or self.obj is None:
            self.obj = obj = pdf.make_indirect(Dictionary())
        else:
            obj = self.obj
        obj.Title = self.title
        if self.destination is not None:
            if isinstance(self.destination, int):
                self.destination = make_page_destination(
                    pdf,
                    self.destination,
                    self.page_location,
                    **self.page_location_kwargs,
                )
            obj.Dest = self.destination
            if Name.A in obj:
                del obj.A
        elif self.action is not None:
            obj.A = self.action
            if Name.Dest in obj:
                del obj.Dest

        if self.color is not None:
            obj.C = Array([float(c) for c in self.color])
        elif Name.C in obj:
            del obj.C

        if self.flags:
            obj.F = int(self.flags)
        elif Name.F in obj:
            del obj.F

        if self.structure_element is not None:
            obj.SE = self.structure_element
        elif Name.SE in obj:
            del obj.SE

        return obj

    def resolved_destination(self, pdf: Pdf) -> Destination | None:
        """Resolve this item's destination to a parsed :class:`Destination`.

        Handles every form ``self.destination`` may take: an explicit
        ``Array``, an ``int`` page number (resolved the same way a save
        would resolve it), or a named destination (a ``String`` looked up
        in the ``Root.Names.Dests`` name tree, or a ``Name`` looked up in
        the legacy ``Root.Dests`` dictionary, per 12.3.2.4).

        Arguments:
            pdf: The PDF document ``self.destination`` refers to.

        Returns:
            The parsed destination, or ``None`` if there is no destination
            set, or a named destination could not be resolved.
        """
        dest = self.destination
        if dest is None:
            return None
        if isinstance(dest, int):
            dest = make_page_destination(
                pdf, dest, self.page_location, **self.page_location_kwargs
            )
        return _resolve_destination_value(pdf, dest)

    @property
    def parsed_action(self) -> Action | None:
        """Lazily wrap ``self.action`` as a typed ``Action``, or ``None``.

        See Also:
            :class:`pikepdf.models.actions.Action`
        """
        if self.action is None:
            return None
        from pikepdf.models.actions import Action as _Action

        return _Action.from_dictionary(self.action)


def _resolve_destination_value(
    pdf: Pdf, dest: Array | String | Name
) -> Destination | None:
    """Resolve a ``/Dest``-shaped value (explicit array or named destination)."""
    from pikepdf._named_dests import resolve_named_destination

    if isinstance(dest, Array):
        return Destination.from_array(dest)
    if isinstance(dest, String):
        arr = resolve_named_destination(pdf, str(dest), 'string')
    elif isinstance(dest, Name):
        arr = resolve_named_destination(pdf, str(dest), 'name')
    else:
        return None
    return Destination.from_array(arr) if arr is not None else None


class Outline:
    """Maintains a intuitive interface for creating and editing PDF document outlines.

    See {{ pdfrm }} section 12.3.

    Arguments:
        pdf: PDF document object.
        max_depth: Maximum recursion depth to consider when reading the outline.
        strict: When ``False`` (default), pikepdf quietly corrects minor
            structural problems in the outline where the correct repair is
            known. For example, a missing required ``/Title`` is treated as an
            empty string, and object references that re-occur while reading or
            writing are recovered without raising. When ``True``, any such
            structural problem raises a :class:`pikepdf.OutlineStructureError`.

    See Also:
        :meth:`pikepdf.Pdf.open_outline`
    """

    def __init__(self, pdf: Pdf, max_depth: int = 15, strict: bool = False):
        """Initialize Outline."""
        self._root: list[OutlineItem] | None = None
        self._pdf = pdf
        self._max_depth = max_depth
        self._strict = strict
        self._updating = False

    def __str__(self):
        return str(self.root)

    def __repr__(self):
        return f'<pikepdf.{self.__class__.__name__}: {len(self.root)} items>'

    def _repr_pretty_(self, p, cycle):
        if cycle:
            p.text("...")
        else:
            with p.group(2, "pikepdf.models.outlines.Outline<\n", "\n>"):
                for _, item in enumerate(self.root):
                    p.breakable()
                    p.pretty(str(item))

    def __enter__(self):
        self._updating = True
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        try:
            if exc_type is not None:
                return
            self._save()
        finally:
            self._updating = False

    def _save_level_outline(
        self,
        parent: Dictionary,
        outline_items: Iterable[OutlineItem],
        level: int,
        visited_objs: set[tuple[int, int]],
    ):
        count = 0
        prev: Dictionary | None = None
        first: Dictionary | None = None
        for item in outline_items:
            out_obj = item.to_dictionary_object(self._pdf)
            objgen = out_obj.objgen
            if objgen in visited_objs:
                if self._strict:
                    raise OutlineStructureError(
                        f"Outline object {objgen} reoccurred in structure"
                    )
                out_obj = item.to_dictionary_object(self._pdf, create_new=True)
            else:
                visited_objs.add(objgen)

            out_obj.Parent = parent
            count += 1
            if prev is not None:
                prev.Next = out_obj
                out_obj.Prev = prev
            else:
                first = out_obj
                if Name.Prev in out_obj:
                    del out_obj.Prev
            prev = out_obj
            if level < self._max_depth:
                sub_items: Iterable[OutlineItem] = item.children
            else:
                sub_items = ()
            self._save_level_outline(out_obj, sub_items, level + 1, visited_objs)
            if item.is_closed:
                out_obj.Count = -cast(int, out_obj.Count)
            else:
                count += cast(int, out_obj.Count)
        if count:
            assert prev is not None and first is not None
            if Name.Next in prev:
                del prev.Next
            parent.First = first
            parent.Last = prev
        else:
            if Name.First in parent:
                del parent.First
            if Name.Last in parent:
                del parent.Last
        parent.Count = count

    def _load_level_outline(
        self,
        first_obj: Dictionary,
        outline_items: list[Object],
        level: int,
        visited_objs: set[tuple[int, int]],
    ):
        current_obj: Dictionary | None = first_obj
        while current_obj:
            objgen = current_obj.objgen
            if objgen in visited_objs:
                if self._strict:
                    raise OutlineStructureError(
                        f"Outline object {objgen} reoccurred in structure"
                    )
                return
            visited_objs.add(objgen)

            item = OutlineItem.from_dictionary_object(current_obj, strict=self._strict)
            first_child = current_obj.get(Name.First)
            if isinstance(first_child, Dictionary) and level < self._max_depth:
                self._load_level_outline(
                    first_child, item.children, level + 1, visited_objs
                )
                count = current_obj.get(Name.Count)
                if isinstance(count, int) and count < 0:
                    item.is_closed = True
            outline_items.append(item)
            next_obj = current_obj.get(Name.Next)
            if next_obj is None or isinstance(next_obj, Dictionary):
                current_obj = next_obj
            else:
                raise OutlineStructureError(
                    f"Outline object {objgen} points to non-dictionary"
                )

    def _save(self):
        if self._root is None:
            return
        if Name.Outlines in self._pdf.Root:
            outlines = self._pdf.Root.Outlines
        else:
            self._pdf.Root.Outlines = outlines = self._pdf.make_indirect(
                Dictionary(Type=Name.Outlines)
            )
        self._save_level_outline(outlines, self._root, 0, set())
        if not self._root and Name.Count in outlines:
            del outlines.Count

    def _load(self):
        self._root = root = []
        if Name.Outlines not in self._pdf.Root:
            return
        outlines = self._pdf.Root.Outlines or {}
        first_obj = outlines.get(Name.First)
        if first_obj:
            self._load_level_outline(first_obj, root, 0, set())

    def add(self, title: str, destination: Array | int | None) -> OutlineItem:
        """Add an item to the outline.

        Arguments:
            title: Title of the outline item.
            destination: Destination to jump to when the item is selected.

        Returns:
            The newly created :class:`OutlineItem`.
        """
        if self._root is None:
            self._load()
        item = OutlineItem(title, destination)
        if self._root is None:
            self._root = [item]
        else:
            self._root.append(item)
        if not self._updating:
            self._save()
        return item

    @property
    def root(self) -> list[OutlineItem]:
        """Return the root node of the outline."""
        if self._root is None:
            self._load()
        return cast(list[OutlineItem], self._root)

    @root.setter
    def root(self, new_root: list[OutlineItem]):
        """Set the root node of the outline."""
        if not isinstance(new_root, list):
            raise ValueError("Root must be a list of OutlineItem objects.")
        for item in new_root:
            if not isinstance(item, OutlineItem):
                raise ValueError("Each item in root must be an OutlineItem.")

        self._root = new_root
