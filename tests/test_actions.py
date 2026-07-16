# SPDX-FileCopyrightText: 2026 James R. Barlow
# SPDX-License-Identifier: CC0-1.0

from __future__ import annotations

import pytest

from pikepdf import Array, Dictionary, Name, Pdf, String
from pikepdf.models.actions import (
    Action,
    GoToAction,
    GoToDpAction,
    GoToEAction,
    GoToRAction,
    JavaScriptAction,
    LaunchAction,
    NamedAction,
    SetOCGStateAction,
    URIAction,
)


@pytest.mark.parametrize(
    ('subtype', 'cls'),
    [
        (Name.GoTo, GoToAction),
        (Name.GoToR, GoToRAction),
        (Name.GoToE, GoToEAction),
        (Name.GoToDp, GoToDpAction),
        (Name.Launch, LaunchAction),
        (Name.URI, URIAction),
        (Name.Named, NamedAction),
        (Name.SetOCGState, SetOCGStateAction),
        (Name.JavaScript, JavaScriptAction),
    ],
)
def test_action_dispatch_by_subtype(subtype, cls):
    obj = Dictionary(S=subtype)
    action = Action.from_dictionary(obj)
    assert isinstance(action, cls)
    assert action.subtype == subtype


def test_action_dispatch_unknown_subtype_falls_back_to_base():
    obj = Dictionary(S=Name.Rendition)
    action = Action.from_dictionary(obj)
    assert type(action) is Action
    assert action.subtype == Name.Rendition


def test_action_dispatch_missing_subtype_falls_back_to_base():
    obj = Dictionary()
    action = Action.from_dictionary(obj)
    assert type(action) is Action
    assert action.subtype is None


def test_goto_action_destination_field(resources):
    with Pdf.open(resources / 'outlines.pdf') as pdf:
        page_ref = pdf.pages[0].obj
        obj = Dictionary(S=Name.GoTo, D=Array([page_ref, Name.Fit]))
        action = Action.from_dictionary(obj)
        assert isinstance(action, GoToAction)
        assert action.destination == [page_ref, Name.Fit]

        action.destination = Array([page_ref, Name.FitH, 100])
        assert obj.D == [page_ref, Name.FitH, 100]

        action.destination = None
        assert Name.D not in obj


def test_goto_action_structure_destination():
    obj = Dictionary(S=Name.GoTo)
    action = GoToAction(obj)
    assert action.structure_destination is None
    action.structure_destination = Array([1, 2])
    assert obj.SD == [1, 2]
    action.structure_destination = None
    assert Name.SD not in obj


def test_goto_action_resolve_destination(resources):
    with Pdf.open(resources / 'outlines.pdf') as pdf:
        page_ref = pdf.pages[0].obj
        obj = Dictionary(S=Name.GoTo, D=Array([page_ref, Name.Fit]))
        action = Action.from_dictionary(obj)
        dest = action.resolve_destination(pdf)
        assert dest.page == page_ref


def test_goto_action_resolve_destination_none_when_unset():
    obj = Dictionary(S=Name.GoTo)
    action = GoToAction(obj)
    pdf = Pdf.new()
    pdf.add_blank_page()
    assert action.resolve_destination(pdf) is None


def test_gotor_action_fields():
    obj = Dictionary(
        S=Name.GoToR,
        F=String('other.pdf'),
        D=Array([0, Name.Fit]),
        NewWindow=True,
    )
    action = Action.from_dictionary(obj)
    assert isinstance(action, GoToRAction)
    assert action.destination == [0, Name.Fit]
    assert action.new_window is True
    action.new_window = False
    assert obj.NewWindow is False
    assert str(action.file_spec) == 'other.pdf'


def test_gotoe_action_fields():
    obj = Dictionary(S=Name.GoToE, D=Array([0, Name.Fit]))
    action = Action.from_dictionary(obj)
    assert isinstance(action, GoToEAction)
    assert action.destination == [0, Name.Fit]
    assert action.target is None
    action.target = Dictionary(R=Name.C)
    assert obj.T.R == Name.C


def test_gotodp_action_field():
    dp = Dictionary(Type=Name.DPart)
    obj = Dictionary(S=Name.GoToDp, Dp=dp)
    action = Action.from_dictionary(obj)
    assert isinstance(action, GoToDpAction)
    assert action.dpart == dp


def test_launch_action_fields():
    fs = Dictionary(Type=Name.Filespec, F=String('app.exe'))
    obj = Dictionary(S=Name.Launch, F=fs)
    action = Action.from_dictionary(obj)
    assert isinstance(action, LaunchAction)
    assert action.file_spec == fs
    assert action.new_window is None


def test_uri_action_fields():
    obj = Dictionary(S=Name.URI, URI=String('https://example.com'))
    action = Action.from_dictionary(obj)
    assert isinstance(action, URIAction)
    assert action.uri == 'https://example.com'
    assert action.is_map is False

    action.uri = 'https://example.org'
    assert str(obj.URI) == 'https://example.org'
    action.is_map = True
    assert obj.IsMap is True


def test_named_action_field():
    obj = Dictionary(S=Name.Named, N=Name.NextPage)
    action = Action.from_dictionary(obj)
    assert isinstance(action, NamedAction)
    assert action.name == Name.NextPage
    action.name = Name.PrevPage
    assert obj.N == Name.PrevPage


def test_setocgstate_action_fields():
    obj = Dictionary(S=Name.SetOCGState, State=Array([Name.ON]))
    action = Action.from_dictionary(obj)
    assert isinstance(action, SetOCGStateAction)
    assert action.state == [Name.ON]
    assert action.preserve_rb is True  # default per spec
    action.preserve_rb = False
    assert obj.PreserveRB is False


def test_javascript_action_field():
    obj = Dictionary(S=Name.JavaScript, JS=String('app.alert(1)'))
    action = Action.from_dictionary(obj)
    assert isinstance(action, JavaScriptAction)
    assert action.javascript == 'app.alert(1)'
    action.javascript = 'app.alert(2)'
    assert str(obj.JS) == 'app.alert(2)'


def test_action_next_chain_single_dict():
    inner = Dictionary(S=Name.URI, URI=String('https://example.com'))
    obj = Dictionary(S=Name.GoTo, Next=inner)
    action = Action.from_dictionary(obj)
    nxt = action.next
    assert len(nxt) == 1
    assert isinstance(nxt[0], URIAction)


def test_action_next_chain_array():
    inner1 = Dictionary(S=Name.URI, URI=String('https://example.com'))
    inner2 = Dictionary(S=Name.Named, N=Name.NextPage)
    obj = Dictionary(S=Name.GoTo, Next=Array([inner1, inner2]))
    action = Action.from_dictionary(obj)
    nxt = action.next
    assert len(nxt) == 2
    assert isinstance(nxt[0], URIAction)
    assert isinstance(nxt[1], NamedAction)


def test_action_next_chain_empty_when_absent():
    obj = Dictionary(S=Name.GoTo)
    action = Action.from_dictionary(obj)
    assert action.next == []


def test_action_repr():
    obj = Dictionary(S=Name.GoTo)
    action = Action.from_dictionary(obj)
    assert 'GoToAction' in repr(action)
