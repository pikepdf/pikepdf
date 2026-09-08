# SPDX-FileCopyrightText: 2022 James R. Barlow
# SPDX-License-Identifier: MPL-2.0

# Type stubs for the bindings in src/core/page.cpp.
# See pikepdf/_core/__init__.pyi for how this stub package is laid out.

# pylint: disable=no-method-argument,unused-argument,no-self-use,too-many-public-methods
# ruff: noqa: D418
# mypy: disable-error-code="misc"

from __future__ import annotations

from collections.abc import Iterable
from typing import Any, overload

from pikepdf._core._matrix import Matrix
from pikepdf._core._object import Object, StreamParser, _ObjectMapping
from pikepdf._core._object_construct import Array, Dictionary, Name, Stream
from pikepdf._core._rectangle import Rectangle
from pikepdf._core._tokenfilter import TokenFilter
from pikepdf._core._typing import T

class Page:
    """Support model wrapper around a page dictionary object."""

    def _repr_mimebundle_(self, include: Any = ..., exclude: Any = ...) -> Any:
        """Present options to IPython or Jupyter for rich display of this object.

        See:
        https://ipython.readthedocs.io/en/stable/config/integrating.html#rich-display
        """
    @overload
    def __init__(self, arg0: Object, /) -> None: ...
    @overload
    def __init__(self, arg0: Page, /) -> None: ...
    def __contains__(self, key: Any, /) -> bool: ...
    def __delattr__(self, name: Any, /) -> None: ...
    def __delitem__(self, name: Any, /) -> None: ...
    def __eq__(self, other: Any, /) -> bool: ...
    def __getattr__(self, name: Any, /) -> Object: ...
    def __getitem__(self, name: Any, /) -> Object: ...
    def __setattr__(self, name: Any, value: Any, /) -> None: ...
    def __setitem__(self, name: Any, value: Any, /) -> None: ...
    def add_content_token_filter(self, tf: TokenFilter) -> None:
        """Attach a :class:`pikepdf.TokenFilter` to a page's content stream.

        This function applies token filters lazily, if/when the page's
        content stream is read for any reason, such as when the PDF is
        saved. If never access, the token filter is not applied.

        Multiple token filters may be added to a page/content stream.

        Token filters may not be removed after being attached to a Pdf.
        Close and reopen the Pdf to remove token filters.

        If the page's contents is an array of streams, it is coalesced.

        Args:
            tf: The token filter to attach.
        """
    def add_overlay(
        self,
        other: Object | Page,
        rect: Rectangle | None,
        *,
        push_stack: bool | None = ...,
    ):
        """Overlay another object on this page.

        Overlays will be drawn after all previous content, potentially drawing on top
        of existing content.

        Args:
            other: A Page or Form XObject to render as an overlay on top of this
                page.
            rect: The PDF rectangle (in PDF units) in which to draw the overlay.
                If omitted, this page's trimbox, cropbox or mediabox (in that order)
                will be used.
            push_stack: If True (default), push the graphics stack of the existing
                content stream to ensure that the overlay is rendered correctly.
                Officially PDF limits the graphics stack depth to 32. Most
                viewers will tolerate more, but excessive pushes may cause problems.
                Multiple content streams may also be coalesced into a single content
                stream where this parameter is True, since the PDF specification
                permits PDF writers to coalesce streams as they see fit.
            shrink: If True (default), allow the object to shrink to fit inside the
                rectangle. The aspect ratio will be preserved.
            expand: If True (default), allow the object to expand to fit inside the
                rectangle. The aspect ratio will be preserved.

        Returns:
            The name of the Form XObject that contains the overlay.

        .. versionadded:: 2.14

        .. versionchanged:: 4.0.0
            Added the *push_stack* parameter. Previously, this method behaved
            as if *push_stack* were False.

        .. versionchanged:: 4.2.0
            Added the *shrink* and *expand* parameters. Previously, this method
            behaved as if ``shrink=True, expand=False``.

        .. versionchanged:: 4.3.0
            Returns the name of the overlay in the resources dictionary instead
            of returning None.
        """
    def add_underlay(self, other: Object | Page, rect: Rectangle | None):
        """Underlay another object beneath this page.

        Underlays will be drawn before all other content, so they may be overdrawn
        partially or completely.

        There is no *push_stack* parameter for this function, since adding an
        underlay can be done without manipulating the graphics stack.

        Args:
            other: A Page or Form XObject to render as an underlay underneath this
                page.
            rect: The PDF rectangle (in PDF units) in which to draw the underlay.
                If omitted, this page's trimbox, cropbox or mediabox (in that order)
                will be used.
            shrink: If True (default), allow the object to shrink to fit inside the
                rectangle. The aspect ratio will be preserved.
            expand: If True (default), allow the object to expand to fit inside the
                rectangle. The aspect ratio will be preserved.

        Returns:
            The name of the Form XObject that contains the underlay.

        .. versionadded:: 2.14

        .. versionchanged:: 4.2.0
            Added the *shrink* and *expand* parameters. Previously, this method
            behaved as if ``shrink=True, expand=False``. Fixed issue with wrong
            page rect being selected.
        """
    def as_form_xobject(self, handle_transformations: bool = ...) -> Object:
        """Return a form XObject that draws this page.

        This is useful for
        n-up operations, underlay, overlay, thumbnail generation, or
        any other case in which it is useful to replicate the contents
        of a page in some other context. The dictionaries are shallow
        copies of the original page dictionary, and the contents are
        coalesced from the page's contents. The resulting object handle
        is not referenced anywhere.

        Args:
            handle_transformations: If True (default), the resulting form
                XObject's ``/Matrix`` will be set to replicate rotation
                (``/Rotate``) and scaling (``/UserUnit``) in the page's
                dictionary. In this way, the page's transformations will
                be preserved when placing this object on another page.
        """
    def calc_form_xobject_placement(
        self,
        formx: Object,
        name: Name,
        rect: Rectangle,
        *,
        invert_transformations: bool,
        allow_shrink: bool,
        allow_expand: bool,
    ) -> bytes:
        """Generate content stream segment to place a Form XObject on this page.

        The content stream segment must then be added to the page's
        content stream.

        The default keyword parameters will preserve the aspect ratio.

        Args:
            formx: The Form XObject to place.
            name: The name of the Form XObject in this page's /Resources
                dictionary.
            rect: Rectangle describing the desired placement of the Form
                XObject.
            invert_transformations: Apply /Rotate and /UserUnit scaling
                when determining FormX Object placement.
            allow_shrink: Allow the Form XObject to take less than the
                full dimensions of rect.
            allow_expand: Expand the Form XObject to occupy all of rect.

        .. versionadded:: 2.14
        """
    def get_matrix_for_form_xobject_placement(
        self,
        fo: Object,
        rect: Rectangle,
        *,
        invert_transformations: bool = ...,
        allow_shrink: bool = ...,
        allow_expand: bool = ...,
    ) -> Matrix:
        """Return the matrix that places a Form XObject within a rectangle.

        This is the transformation matrix used by
        :meth:`calc_form_xobject_placement`. The parameters have the same
        meaning as for that method.

        .. versionadded:: 10.9
        """
    def get_matrix_for_transformations(self, invert: bool = ...) -> Matrix:
        """Return the matrix equivalent to this page's /Rotate and /UserUnit.

        Args:
            invert: If True, return the inverse matrix (suitable for placing
                something else onto this page). If False (default), return the
                matrix suitable for taking content from this page elsewhere.

        .. versionadded:: 10.9
        """
    def flatten_rotation(self) -> None:
        """Bake this page's /Rotate value into its content stream.

        If a page is rotated using ``/Rotate`` in the page dictionary, instead
        rotate the page by the same amount by altering the content stream and
        removing the ``/Rotate`` key, adjusting the page bounding boxes so the
        page has the same appearance. This can work around problems with PDF
        applications that cannot properly handle rotated pages.

        .. versionadded:: 10.9
        """
    def copy_annotations(self, from_page: Page, matrix: Matrix = ...) -> None:
        """Copy annotations from another page onto this page.

        The other page may belong to the same or a different
        :class:`pikepdf.Pdf`. Each annotation's rectangle is transformed by the
        given matrix. If an annotation is a form field widget, the form field is
        copied into this document's AcroForm as well.

        Args:
            from_page: The page to copy annotations from.
            matrix: A transformation matrix applied to each annotation's
                rectangle. Defaults to the identity matrix.

        .. versionadded:: 10.9
        """
    def get_images(self, recursive: bool = ...) -> _ObjectMapping:
        """Return the images used by this page.

        Args:
            recursive: If True (the default), also report images nested inside
                form XObjects referenced by this page, recursing to any depth.
                This is usually what you want, since a page's visible content is
                often drawn through one or more form XObjects. If two images in
                different XObject scopes share a resource name, only one is
                reported. If False, report only images referenced directly by
                this page's resources.

        .. versionadded:: 10.9
        """
    def contents_add(self, contents: Stream | bytes, *, prepend: bool = ...) -> None:
        """Append or prepend to an existing page's content stream.

        Args:
            contents: An existing content stream to append or prepend.
            prepend: Prepend if true, append if false (default).

        .. versionadded:: 2.14
        """
    def contents_coalesce(self) -> None:
        """Coalesce a page's content streams.

        A page's content may be a
        stream or an array of streams. If this page's content is an
        array, concatenate the streams into a single stream. This can
        be useful when working with files that split content streams in
        arbitrary spots, such as in the middle of a token, as that can
        confuse some software.
        """
    def emplace(self, other: Page, retain: Iterable[Name] = ...) -> None: ...
    def externalize_inline_images(
        self, min_size: int = ..., shallow: bool = ...
    ) -> None:
        """Convert inline image to normal (external) images.

        Args:
            min_size: minimum size in bytes
            shallow: If False, recurse into nested Form XObjects.
                If True, do not recurse.
        """
    def form_xobjects(self) -> _ObjectMapping:
        """Return all Form XObjects associated with this page.

        This method does not recurse into nested Form XObjects.

        .. versionadded:: 7.0.0
        """
    @overload
    def get(self, key: str | Name, /) -> Object | None: ...
    @overload
    def get(self, key: str | Name, default: T, /) -> Object | T: ...
    def get_filtered_contents(self, tf: TokenFilter) -> bytes:
        """Apply a :class:`pikepdf.TokenFilter` to a content stream.

        This may be used when the results of a token filter do not need
        to be applied, such as when filtering is being used to retrieve
        information rather than edit the content stream.

        Note that it is possible to create a subclassed ``TokenFilter``
        that saves information of interest to its object attributes; it
        is not necessary to return data in the content stream.

        To modify the content stream, use :meth:`pikepdf.Page.add_content_token_filter`.

        Returns:
            The result of modifying the content stream with ``tf``.
            The existing content stream is not modified.
        """
    def index(self) -> int:
        """Returns the zero-based index of this page in the pages list.

        That is, returns ``n`` such that ``pdf.pages[n] == this_page``.
        A ``ValueError`` exception is thrown if the page is not attached
        to this ``Pdf``.

        .. versionadded:: 2.2
        """
    def label(self) -> str:
        """Returns the page label for this page, accounting for section numbers.

        For example, if the PDF defines a preface with lower case Roman
        numerals (i, ii, iii...), followed by standard numbers, followed
        by an appendix (A-1, A-2, ...), this function returns the appropriate
        label as a string.

        It is possible for a PDF to define page labels such that multiple
        pages have the same labels. Labels are not guaranteed to
        be unique.

        .. versionadded:: 2.2

        .. versionchanged:: 2.9
            Returns the ordinary page number if no special rules for page
            numbers are defined.
        """
    def parse_contents(self, stream_parser: StreamParser) -> None:
        """Parse a page's content streams using a :class:`pikepdf.StreamParser`.

        The content stream may be interpreted by the StreamParser but is
        not altered.

        If the page's contents is an array of streams, it is coalesced.

        Args:
            stream_parser: A :class:`pikepdf.StreamParser` instance.
        """
    def remove_unreferenced_resources(self) -> None:
        """Removes resources not referenced by content stream.

        A page's resources (``page.resources``) dictionary maps names to objects.
        This method walks through a page's contents and
        keeps tracks of which resources are referenced somewhere in the
        contents. Then it removes from the resources dictionary any
        object that is not referenced in the contents. This
        method is used by page splitting code to avoid copying unused
        objects in files that use shared resource dictionaries across
        multiple pages.
        """
    def rotate(self, angle: int, *, relative: bool = False) -> None:
        """Rotate a page.

        If ``relative`` is ``False`` (the default), set the rotation of the
        page to angle. Otherwise, add angle to the rotation of the
        page. ``angle`` must be a multiple of ``90``. Adding ``90`` to
        the rotation rotates clockwise by ``90`` degrees.

        Args:
            angle: Rotation angle in degrees.
            relative: If ``True``, add ``angle`` to the current
                rotation. If ``False``, set the rotation of the page
                to ``angle``.

        .. deprecated:: 10.9
            Passing ``relative`` as a positional argument is deprecated; pass
            it as a keyword argument instead, e.g.
            ``page.rotate(90, relative=True)``. Positional support will be
            removed in pikepdf 11.
        """
    @property
    def images(self) -> _ObjectMapping:
        """Return images directly referenced by this page's resources.

        This property does not search Form XObjects that contain images, and
        does not attempt to find inline images.

        .. deprecated:: 10.9
            Use :meth:`get_images` instead, which recurses into Form XObjects by
            default. Because it is not visually obvious when a page's content is
            wrapped in a Form XObject, this property often appears as if a page
            "has no images" when it clearly does.
        """
    @property
    def artbox(self) -> Array:
        """Return page's effective /ArtBox, in PDF units.

        According to the PDF specification:
        "The art box defines the page's meaningful content area, including
        white space."

        If the /ArtBox is not defined, the /CropBox is returned.
        """
    @artbox.setter
    def artbox(self, val: Array | Rectangle) -> None: ...
    @property
    def bleedbox(self) -> Array:
        """Return page's effective /BleedBox, in PDF units.

        According to the PDF specification:
        "The bleed box defines the region to which the contents of the page
        should be clipped when output in a print production environment."

        If the /BleedBox is not defined, the /CropBox is returned.
        """
    @bleedbox.setter
    def bleedbox(self, val: Array | Rectangle) -> None: ...
    @property
    def cropbox(self) -> Array:
        """Return page's effective /CropBox, in PDF units.

        According to the PDF specification:
        "The crop box defines the region to which the contents of the page
        shall be clipped (cropped) when displayed or printed. It has no
        defined meaning in the context of the PDF imaging model; it merely
        imposes clipping on the page contents."

        If the /CropBox is not defined, the /MediaBox is returned.
        """
    @cropbox.setter
    def cropbox(self, val: Array | Rectangle) -> None: ...
    @property
    def mediabox(self) -> Array:
        """Return page's /MediaBox, in PDF units.

        According to the PDF specification:
        "The media box defines the boundaries of the physical medium on which
        the page is to be printed."
        """
    @mediabox.setter
    def mediabox(self, val: Array | Rectangle) -> None: ...
    @property
    def obj(self) -> Dictionary: ...
    @property
    def rotation(self) -> int:
        """The page's clockwise rotation in degrees, normalized to ``[0, 360)``.

        Unlike the raw ``page.Rotate`` attribute, this property reports the
        *effective* rotation: it resolves a ``/Rotate`` value inherited from the
        page tree and reports ``0`` when no rotation is set, instead of raising.
        Assigning to this property sets the absolute rotation; to rotate
        relative to the current value, use :meth:`rotate` with ``relative=True``.

        .. versionadded:: 10.9
        """
    @rotation.setter
    def rotation(self, angle: int) -> None: ...
    @property
    def trimbox(self) -> Array:
        """Return page's effective /TrimBox, in PDF units.

        According to the PDF specification:
        "The trim box defines the intended dimensions of the finished page
        after trimming. It may be smaller than the media box to allow for
        production-related content, such as printing instructions, cut marks,
        or color bars."

        If the /TrimBox is not defined, the /CropBox is returned (and if
        /CropBox is not defined, /MediaBox is returned).
        """
    @trimbox.setter
    def trimbox(self, val: Array | Rectangle) -> None: ...
    @property
    def resources(self) -> Dictionary:
        """Return this page's resources dictionary.

        .. versionchanged:: 7.0.0
            If the resources dictionary does not exist, an empty one will be created.
            A TypeError is raised if a page has a /Resources key but it is not a
            dictionary.
        """
    def add_resource(
        self,
        res: Object,
        res_type: Name,
        name: Name | None = None,
        *,
        prefix: str = '',
        replace_existing: bool = True,
    ) -> Name:
        """Add a new resource to the page's Resources dictionary.

        If the Resources dictionaries do not exist, they will be created.

        Args:
            self: The object to add to the resources dictionary.
            res: The dictionary object to insert into the resources
                dictionary.
            res_type: Should be one of the following Resource dictionary types:
                ExtGState, ColorSpace, Pattern, Shading, XObject, Font, Properties.
            name: The name of the object. If omitted, a random name will be
                generated with enough randomness to be globally unique.
            prefix: A prefix for the name of the object. Allows conveniently
                namespacing when using random names, e.g. prefix="Im" for images.
                Mutually exclusive with name parameter.
            replace_existing: If the name already exists in one of the resource
                dictionaries, remove it.

        Example:
            >>> pdf = pikepdf.Pdf.new()
            >>> pdf.add_blank_page(page_size=(100, 100))
            <pikepdf.Page({
              "/Contents": pikepdf.Stream(owner=<...>, data=<...>, {
            <BLANKLINE>
              }),
              "/MediaBox": [ 0, 0, 100, 100 ],
              "/Parent": <reference to /Pages>,
              "/Resources": {
            <BLANKLINE>
              },
              "/Type": "/Page"
            })>
            >>> formxobj = pikepdf.Dictionary(
            ...     Type=Name.XObject,
            ...     Subtype=Name.Form
            ... )
            >>> resource_name = pdf.pages[0].add_resource(formxobj, Name.XObject)

        .. versionadded:: 2.3

        .. versionchanged:: 2.14
            If *res* does not belong to the same `Pdf` that owns this page,
            a copy of *res* is automatically created and added instead. In previous
            versions, it was necessary to change for this case manually.

        .. versionchanged:: 4.3.0
            Returns the name of the overlay in the resources dictionary instead
            of returning None.
        """
