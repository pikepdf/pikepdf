# SPDX-FileCopyrightText: 2021 James R. Barlow <james@purplerock.ca>
# SPDX-License-Identifier: MPL-2.0

from pkg_resources import DistributionNotFound
from pkg_resources import get_distribution as _get_distribution

try:
    __version__ = _get_distribution(__package__).version
except DistributionNotFound:  # pragma: no cover
    __version__ = "Not installed"

__all__ = ['__version__']
