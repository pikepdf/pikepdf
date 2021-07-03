from decimal import Decimal

import pytest

from pikepdf import Array, Name, Rectangle


def test_rect_properties():
    r = Rectangle(1, 2, 101, 302)
    assert r.llx == 1.0
    assert r.lly == 2.0
    assert r.urx == 101.0
    assert r.ury == 302.0
    assert r.width == 100.0
    assert r.height == 300.0
    assert r.lower_left == (r.llx, r.lly)
    assert r.lower_right == (r.urx, r.lly)
    assert r.upper_right == (r.urx, r.ury)
    assert r.upper_left == (r.llx, r.ury)
    assert r.as_array() == Array([Decimal(coord) for coord in [1, 2, 101, 302]])


def test_rect_creation():
    assert Rectangle(Array([1, 2, 3, 4])).width == 2


def test_rect_from_invalid():
    with pytest.raises(TypeError):
        Rectangle('foo')
    with pytest.raises(TypeError):
        Rectangle(Name.Foo)
    with pytest.raises(TypeError):
        Rectangle(Array([1, 2]))
    with pytest.raises(TypeError):
        Rectangle(Array(['one', 'two', 'three', 'four']))
