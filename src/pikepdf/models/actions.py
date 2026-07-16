# SPDX-FileCopyrightText: 2026 James R. Barlow
# SPDX-License-Identifier: MPL-2.0
"""Typed wrappers for PDF action dictionaries (ISO 32000-2 12.6)."""

from __future__ import annotations

from typing import cast

from pikepdf._core import Pdf
from pikepdf.models.outlines import Destination, _resolve_destination_value
from pikepdf.objects import Array, Dictionary, Name, Object, String


class Action:
    """Wrapper around a PDF action dictionary (spec 12.6).

    Use :meth:`from_dictionary` to get a typed subclass (e.g.
    :class:`GoToAction`) dispatched by the action's ``/S`` subtype. Subtypes
    without a dedicated wrapper are returned as a plain ``Action``, whose
    ``.obj`` gives raw access to the underlying dictionary.
    """

    def __init__(self, obj: Dictionary):
        """Initialize Action."""
        self.obj = obj

    @property
    def subtype(self) -> Name | None:
        """The action's ``/S`` subtype, e.g. ``Name.GoTo``."""
        return cast('Name | None', self.obj.get(Name.S))

    @property
    def next(self) -> list[Action]:
        """The ``/Next`` chain: actions to additionally perform after this one."""
        nxt = self.obj.get(Name.Next)
        if nxt is None:
            return []
        if isinstance(nxt, Array):
            return [Action.from_dictionary(cast(Dictionary, item)) for item in nxt]
        return [Action.from_dictionary(cast(Dictionary, nxt))]

    @classmethod
    def from_dictionary(cls, obj: Dictionary) -> Action:
        """Wrap an action dictionary, dispatching to a typed subclass by ``/S``."""
        subtype = cast('Name | None', obj.get(Name.S))
        if subtype is None:
            return Action(obj)
        return _ACTION_CLASSES.get(subtype, Action)(obj)

    def __repr__(self):
        return f'<pikepdf.{self.__class__.__name__}: {self.subtype}>'


class GoToAction(Action):
    """A ``GoTo`` action: navigate to a destination in this document (12.6.4.2)."""

    @property
    def destination(self) -> Array | String | Name | None:
        """The target destination (``/D``)."""
        return cast('Array | String | Name | None', self.obj.get(Name.D))

    @destination.setter
    def destination(self, value: Array | String | Name | None) -> None:
        if value is None:
            if Name.D in self.obj:
                del self.obj.D
        else:
            self.obj.D = value

    @property
    def structure_destination(self) -> Array | None:
        """The target structure destination (``/SD``, PDF 2.0)."""
        return cast('Array | None', self.obj.get(Name.SD))

    @structure_destination.setter
    def structure_destination(self, value: Array | None) -> None:
        if value is None:
            if Name.SD in self.obj:
                del self.obj.SD
        else:
            self.obj.SD = value

    def resolve_destination(self, pdf: Pdf) -> Destination | None:
        """Resolve ``destination`` to a parsed :class:`~pikepdf.Destination`."""
        dest = self.destination
        if dest is None:
            return None
        return _resolve_destination_value(pdf, dest)


class GoToRAction(Action):
    """A ``GoToR`` action: navigate to a destination in another document (12.6.4.3)."""

    @property
    def file_spec(self) -> Object | None:
        """The target file (``/F``)."""
        return self.obj.get(Name.F)

    @file_spec.setter
    def file_spec(self, value: Object | None) -> None:
        if value is None:
            if Name.F in self.obj:
                del self.obj.F
        else:
            self.obj.F = value

    @property
    def destination(self) -> Array | String | Name | None:
        """The target destination (``/D``) in the remote file.

        If an array, its first element is an integer page number, not an
        indirect reference to a page in this document (12.6.4.3).
        """
        return cast('Array | String | Name | None', self.obj.get(Name.D))

    @destination.setter
    def destination(self, value: Array | String | Name | None) -> None:
        if value is None:
            if Name.D in self.obj:
                del self.obj.D
        else:
            self.obj.D = value

    @property
    def new_window(self) -> bool | None:
        """Whether to open the target document in a new window (``/NewWindow``)."""
        return cast('bool | None', self.obj.get(Name.NewWindow))

    @new_window.setter
    def new_window(self, value: bool | None) -> None:
        if value is None:
            if Name.NewWindow in self.obj:
                del self.obj.NewWindow
        else:
            self.obj.NewWindow = value


class GoToEAction(Action):
    """A ``GoToE`` action: navigate to a destination in an embedded file (12.6.4.4)."""

    @property
    def file_spec(self) -> Object | None:
        """The root document of the target file (``/F``)."""
        return self.obj.get(Name.F)

    @file_spec.setter
    def file_spec(self, value: Object | None) -> None:
        if value is None:
            if Name.F in self.obj:
                del self.obj.F
        else:
            self.obj.F = value

    @property
    def destination(self) -> Array | String | Name | None:
        """The target destination (``/D``) in the embedded file."""
        return cast('Array | String | Name | None', self.obj.get(Name.D))

    @destination.setter
    def destination(self, value: Array | String | Name | None) -> None:
        if value is None:
            if Name.D in self.obj:
                del self.obj.D
        else:
            self.obj.D = value

    @property
    def new_window(self) -> bool | None:
        """Whether to open the target document in a new window (``/NewWindow``)."""
        return cast('bool | None', self.obj.get(Name.NewWindow))

    @new_window.setter
    def new_window(self, value: bool | None) -> None:
        if value is None:
            if Name.NewWindow in self.obj:
                del self.obj.NewWindow
        else:
            self.obj.NewWindow = value

    @property
    def target(self) -> Dictionary | None:
        """The target dictionary locating the embedded file (``/T``)."""
        return cast('Dictionary | None', self.obj.get(Name.T))

    @target.setter
    def target(self, value: Dictionary | None) -> None:
        if value is None:
            if Name.T in self.obj:
                del self.obj.T
        else:
            self.obj.T = value


class GoToDpAction(Action):
    """A ``GoToDp`` action: navigate to a document part (12.6.4.5, PDF 2.0)."""

    @property
    def dpart(self) -> Object | None:
        """The target DPart dictionary (``/Dp``)."""
        return self.obj.get(Name.Dp)

    @dpart.setter
    def dpart(self, value: Object | None) -> None:
        if value is None:
            if Name.Dp in self.obj:
                del self.obj.Dp
        else:
            self.obj.Dp = value


class LaunchAction(Action):
    """A ``Launch`` action: launch an application (12.6.4.6)."""

    @property
    def file_spec(self) -> Object | None:
        """The application/file to launch (``/F``)."""
        return self.obj.get(Name.F)

    @file_spec.setter
    def file_spec(self, value: Object | None) -> None:
        if value is None:
            if Name.F in self.obj:
                del self.obj.F
        else:
            self.obj.F = value

    @property
    def new_window(self) -> bool | None:
        """Whether to open the target document in a new window (``/NewWindow``)."""
        return cast('bool | None', self.obj.get(Name.NewWindow))

    @new_window.setter
    def new_window(self, value: bool | None) -> None:
        if value is None:
            if Name.NewWindow in self.obj:
                del self.obj.NewWindow
        else:
            self.obj.NewWindow = value


class URIAction(Action):
    """A ``URI`` action: resolve a URI (12.6.4.8)."""

    @property
    def uri(self) -> str | None:
        """The URI to resolve (``/URI``)."""
        val = self.obj.get(Name.URI)
        return str(val) if val is not None else None

    @uri.setter
    def uri(self, value: str | None) -> None:
        if value is None:
            if Name.URI in self.obj:
                del self.obj.URI
        else:
            self.obj.URI = String(value)

    @property
    def is_map(self) -> bool:
        """Whether mouse click coordinates are appended to the URI (``/IsMap``).

        Per spec, this flag is ignored for actions associated with outline
        items (it only applies to annotation mouse clicks).
        """
        return bool(self.obj.get(Name.IsMap, False))

    @is_map.setter
    def is_map(self, value: bool) -> None:
        self.obj.IsMap = bool(value)


class NamedAction(Action):
    """A ``Named`` action: execute a predefined named action (12.6.4.12)."""

    @property
    def name(self) -> Name | None:
        """The name of the action to execute (``/N``), e.g. ``Name.NextPage``."""
        return cast('Name | None', self.obj.get(Name.N))

    @name.setter
    def name(self, value: Name | None) -> None:
        if value is None:
            if Name.N in self.obj:
                del self.obj.N
        else:
            self.obj.N = value


class SetOCGStateAction(Action):
    """A ``SetOCGState`` action: set optional content group states (12.6.4.13)."""

    @property
    def state(self) -> Array | None:
        """The ``/ON``/``/OFF``/``/Toggle`` sequence of OCG dicts (``/State``)."""
        return cast('Array | None', self.obj.get(Name.State))

    @state.setter
    def state(self, value: Array | None) -> None:
        if value is None:
            if Name.State in self.obj:
                del self.obj.State
        else:
            self.obj.State = value

    @property
    def preserve_rb(self) -> bool:
        """Whether to preserve radio-button OCG relationships (``/PreserveRB``)."""
        return bool(self.obj.get(Name.PreserveRB, True))

    @preserve_rb.setter
    def preserve_rb(self, value: bool) -> None:
        self.obj.PreserveRB = bool(value)


class JavaScriptAction(Action):
    """A ``JavaScript`` action: execute an ECMAScript script."""

    @property
    def javascript(self) -> str | None:
        """The script to execute (``/JS``)."""
        val = self.obj.get(Name.JS)
        return str(val) if val is not None else None

    @javascript.setter
    def javascript(self, value: str | None) -> None:
        if value is None:
            if Name.JS in self.obj:
                del self.obj.JS
        else:
            self.obj.JS = String(value)


_ACTION_CLASSES: dict[Name, type[Action]] = {
    Name.GoTo: GoToAction,
    Name.GoToR: GoToRAction,
    Name.GoToE: GoToEAction,
    Name.GoToDp: GoToDpAction,
    Name.Launch: LaunchAction,
    Name.URI: URIAction,
    Name.Named: NamedAction,
    Name.SetOCGState: SetOCGStateAction,
    Name.JavaScript: JavaScriptAction,
}
