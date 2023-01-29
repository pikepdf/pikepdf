# SPDX-FileCopyrightText: 2022 James R. Barlow
# SPDX-License-Identifier: MPL-2.0

from __future__ import annotations

from warnings import warn

warn("pikepdf._qpdf is deprecated, use pikepdf._core instead.", DeprecationWarning)
del warn

from pikepdf._core import *  # pylint:disable=wildcard-import,unused-wildcard-import
