# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.
#
# Copyright (C) 2017, James R. Barlow (https://github.com/jbarlow83/)

from pkg_resources import DistributionNotFound
from pkg_resources import get_distribution as _get_distribution

try:
    __version__ = _get_distribution(__package__).version
except DistributionNotFound:  # pragma: no cover
    __version__ = "Not installed"

__all__ = ['__version__']
