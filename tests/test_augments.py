# SPDX-FileCopyrightText: 2022 James R. Barlow
# SPDX-License-Identifier: CC0-1.0

from __future__ import annotations

import pytest

from pikepdf._augments import augment_if_no_cpp, augment_override_cpp, augments


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


def test_override_cpp():
    class PretendCpp:
        def fn(self):
            return 'fn c++'

    @augments(PretendCpp)
    class _Extend_PretendCpp:
        @augment_override_cpp
        def fn(self):
            return 'fn py'

    p = PretendCpp()
    assert p.fn() == 'fn py'
