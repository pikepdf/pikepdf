# SPDX-FileCopyrightText: 2026 James R. Barlow
# SPDX-License-Identifier: CC0-1.0

from __future__ import annotations

import pytest

import pikepdf


@pytest.fixture
def mapping():
    """An _ObjectMapping with a numeric value and an Object value."""
    return pikepdf.Dictionary(A=1, B=pikepdf.Name.Foo).as_dict()


def test_objectmapping_eq_dict(mapping):
    assert mapping == {'/A': 1, '/B': pikepdf.Name.Foo}
    assert mapping == dict(mapping)
    assert mapping != {'/A': 1}
    assert mapping != {'/A': 2, '/B': pikepdf.Name.Foo}
    assert mapping != {'/A': 1, '/C': pikepdf.Name.Foo}


def test_objectmapping_eq_mapping(mapping):
    assert mapping == pikepdf.Dictionary(A=1, B=pikepdf.Name.Foo).as_dict()
    assert mapping != pikepdf.Dictionary(A=1, B=pikepdf.Name.Bar).as_dict()
    assert mapping == mapping


def test_objectmapping_eq_name_keys(mapping):
    assert mapping == {pikepdf.Name.A: 1, pikepdf.Name.B: pikepdf.Name.Foo}


def test_objectmapping_eq_other_type(mapping):
    assert not (mapping == 'foo')
    assert not (mapping == 42)
    assert mapping != 'foo'
    assert not (mapping == {'/A': object(), '/B': pikepdf.Name.Foo})
    assert not (mapping == {42: 1})


def test_objectmapping_no_implicit_conversion_warning(mapping, capfd):
    mapping == {'/A': 1, '/B': pikepdf.Name.Foo}
    mapping == {}
    mapping == 'foo'
    assert 'implicit conversion' not in capfd.readouterr().err


def test_objectmapping_setitem(mapping):
    mapping['/C'] = 5
    assert mapping['/C'] == 5
    mapping['/D'] = pikepdf.Name.Bar
    assert mapping['/D'] == pikepdf.Name.Bar
    with pytest.raises(RuntimeError):
        mapping['/E'] = object()


def test_objectmapping_name_keys(mapping):
    mapping[pikepdf.Name.C] = 5
    assert pikepdf.Name.C in mapping
    assert mapping[pikepdf.Name.C] == 5
    del mapping[pikepdf.Name.C]
    assert pikepdf.Name.C not in mapping
    del mapping[pikepdf.Name.A]
    assert mapping == {'/B': pikepdf.Name.Foo}


def test_objectmapping_rejects_other_key_types(mapping):
    """Only str and Name can name an entry; anything else is a TypeError."""
    for op in (
        lambda: mapping[42],
        lambda: mapping.__setitem__(42, 1),
        lambda: mapping.__delitem__(42),
        lambda: mapping.get(42),
    ):
        with pytest.raises(TypeError, match="str or pikepdf.Name"):
            op()
    # __contains__ answers rather than raising, the same way list's does
    assert 42 not in mapping


def test_objectmapping_get_accepts_none_default(mapping):
    assert mapping.get('/Zed', None) is None
    assert mapping.get('/Zed', default=None) is None
    assert mapping.get(pikepdf.Name.A, None) == 1


def test_objectmapping_missing_key_names_the_key(mapping):
    with pytest.raises(KeyError, match='/Zed'):
        mapping['/Zed']
    with pytest.raises(KeyError, match='/Zed'):
        del mapping[pikepdf.Name.Zed]


def test_objectmapping_update(mapping):
    mapping.update({'/A': 2, '/C': 3})
    assert mapping == {'/A': 2, '/B': pikepdf.Name.Foo, '/C': 3}
    mapping.update(pikepdf.Dictionary(D=4).as_dict())
    assert mapping['/D'] == 4
    with pytest.raises(TypeError):
        mapping.update([('/E', 1)])
