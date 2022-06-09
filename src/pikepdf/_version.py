# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.
#
# Copyright (C) 2017, James R. Barlow (https://github.com/jbarlow83/)


try:
    from importlib_metadata import version as _package_version  # type: ignore
except ImportError:
    from importlib.metadata import version as _package_version

__version__ = _package_version('pikepdf')

__all__ = ['__version__']
