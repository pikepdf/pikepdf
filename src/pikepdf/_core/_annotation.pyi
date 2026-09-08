# SPDX-FileCopyrightText: 2022 James R. Barlow
# SPDX-License-Identifier: MPL-2.0

# Type stubs for the bindings in src/core/annotation.cpp.
# See pikepdf/_core/__init__.pyi for how this stub package is laid out.

# pylint: disable=no-method-argument,unused-argument,no-self-use,too-many-public-methods
# ruff: noqa: D418
# mypy: disable-error-code="misc"

from __future__ import annotations

from enum import IntFlag

from pikepdf._core._object import Object
from pikepdf._core._object_construct import Name
from pikepdf._core._rectangle import Rectangle

class AnnotationFlag(IntFlag):
    """Flag values for `pikepdf.Annotation.flags`."""

    invisible: ...
    """Do not attempt to display the appearance stream for this annotation.

    This flag is only to be used in cases where the annotation is not a standard type.
    For standard annotation types, use the ``hidden`` flag instead.
    """
    hidden: ...
    """This annotation should not be displayed to users.

    This flag overrides all other display-related flags, and applies in both print and
    screen versions of the PDF.
    """
    print: ...
    """If set, this annotation should also be included when the PDF is printed.
    Otherwise, it is only shown on screen but omitted when printing.
    """
    no_zoom: ...
    """When zooming in on the page, this annotation will not grow larger. It will remain
    anchored by the top-left corner.
    """
    no_rotate: ...
    """When rotating the page, this annotation will not rotate along with it. It will
    remain anchored by the top-left corner.
    """
    no_view: ...
    """Do not display this annotation on-screen. The annotation may still show when
    printing the PDF, depending on the value of the ``print`` flag.
    """
    read_only: ...
    """This annotation is non-interactive.

    This does not merely prevent editing, but all interactions. The annotation will not
    respond to any mouse or keyboard events, including hover."""
    locked: ...
    """This annotation cannot be altered or deleted.

    This does not restrict altering the annotation contents, or normal interaction with
    form widgets, but merely indicates that the annotation itself cannot be moved or
    otherwise altered.
    """
    toggle_no_view: ...
    """If set, the value of the ``no_view`` flag will be inverted on selection or hover.
    This can be used to create annotations that are only visible when hovered, or
    annotations that disappear when hovered."""
    locked_contents: ...
    """Prevent the contents of the annotation from being changed by the user.

    Opposite the ``locked`` flag, this *does not* prevent altering or deleting the
    annotation; but its contents.

    For form fields, use the ``read_only`` field flag rather than this annotation flag.
    """

class Annotation:
    """A PDF annotation. Wrapper around a PDF dictionary.

    Describes an annotation in a PDF, such as a comment, underline,
    copy editing marks, interactive widgets, redactions, 3D objects, sound
    and video clips.

    See the {{ pdfrm }} section 12.5.6 for the full list of annotation types
    and definition of terminology.

    .. versionadded:: 2.12
    """

    def __init__(self, obj: Object) -> None: ...
    def get_appearance_stream(
        self, which: Object, state: Object | None = ...
    ) -> Object:
        """Returns one of the appearance streams associated with an annotation.

        Args:
            which: Usually one of ``pikepdf.Name.N``, ``pikepdf.Name.R`` or
                ``pikepdf.Name.D``, indicating the normal, rollover or down
                appearance stream, respectively. If any other name is passed,
                an appearance stream with that name is returned.
            state: The appearance state. For checkboxes or radio buttons, the
                appearance state is usually whether the button is on or off.
        """
    def get_page_content_for_appearance(
        self,
        name: Name,
        rotate: int,
        required_flags: int = ...,
        forbidden_flags: int = ...,
    ) -> bytes:
        """Generate content stream text that draws this annotation as a Form XObject.

        Args:
            name: What to call the object we create.
            rotate: Should be set to the page's /Rotate value or 0.
            required_flags: The required appearance flags. See PDF reference manual.
            forbidden_flags: The forbidden appearance flags. See PDF reference manual.

        Note:
            This method is done mainly with qpdf. Its behavior may change when
            different qpdf versions are used.
        """
    @property
    def appearance_dict(self) -> Object:
        """Returns the annotations appearance dictionary."""
    @property
    def appearance_state(self) -> Object:
        """Returns the annotation's appearance state (or None).

        For a checkbox or radio button, the appearance state may be ``pikepdf.Name.On``
        or ``pikepdf.Name.Off``.
        """
    @property
    def rect(self) -> Rectangle:
        """Returns a rectangle defining the location of the annotation."""
    @property
    def flags(self) -> int:
        """Returns the annotation's flags."""
    @property
    def obj(self) -> Object: ...
    @property
    def subtype(self) -> str:
        """Returns the subtype of this annotation."""
