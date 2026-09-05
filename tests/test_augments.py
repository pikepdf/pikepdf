# SPDX-FileCopyrightText: 2022 James R. Barlow
# SPDX-License-Identifier: CC0-1.0

from __future__ import annotations

from collections.abc import MutableMapping

import pytest

from pikepdf._augments import augment_if_no_cpp, augments


def test_no_duplicate_definition():
    class PretendCpp:
        def fn(self):
            return 'fn c++'

    with pytest.raises(RuntimeError, match="both define the same"):

        @augments(PretendCpp)
        class _Extend_PretendCpp:
            def fn(self):
                return 'fn py'


def test_if_no_cpp():
    class PretendCpp:
        def fn1(self):
            return 'fn1 c++'

        def fn2(self):
            return 'fn2 c++'

    @augments(PretendCpp)
    class _Extend_PretendCpp:
        @augment_if_no_cpp
        def fn2(self):
            return 'fn2 py'

        @augment_if_no_cpp
        def fn3(self):
            return 'fn3 py'

    p = PretendCpp()
    assert p.fn1() == 'fn1 c++'
    assert p.fn2() == 'fn2 c++'
    assert p.fn3() == 'fn3 py'  # pylint: disable=no-member


def test_abstract_method_does_not_replace_cpp():
    """A support class may subclass an ABC purely for its mixin methods.

    The abstract methods it inherits are implemented in C++; installing the
    abstract stubs over them would break the class.
    """

    class PretendCpp:
        def __getitem__(self, key):
            return {'a': 1}[key]

        def __iter__(self):
            return iter(['a'])

        def __len__(self):
            return 1

    @augments(PretendCpp)
    class _Extend_PretendCpp(MutableMapping):
        def __setitem__(self, key, value):
            raise NotImplementedError()

        def __delitem__(self, key):
            raise NotImplementedError()

    p = PretendCpp()
    assert p['a'] == 1
    assert list(p) == ['a']
    assert len(p) == 1
    # the concrete mixin methods still arrive from the ABC
    assert p.get('missing', 42) == 42  # pylint: disable=no-member
    assert 'a' in p
