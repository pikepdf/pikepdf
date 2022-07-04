# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.
#
# Copyright (C) 2022, James R. Barlow (https://github.com/jbarlow83/)

from ._qpdf import (
    get_decimal_precision,
    set_decimal_precision,
    set_flate_compression_level,
)

__all__ = [
    'get_decimal_precision',
    'set_decimal_precision',
    'set_flate_compression_level',
]
