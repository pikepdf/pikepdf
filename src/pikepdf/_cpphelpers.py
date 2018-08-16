# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.
#
# Copyright (C) 2017, James R. Barlow (https://github.com/jbarlow83/)

"""
Support functions called by the C++ library binding layer. Not intended to be
called from Python, and subject to change at any time.
"""

import os
import sys


# Provide os.fspath equivalent for Python <3.6
if sys.version_info[0:2] <= (3, 5):  # pragma: no cover
    def fspath(path):
        '''https://www.python.org/dev/peps/pep-0519/#os'''
        import pathlib
        if isinstance(path, (str, bytes)):
            return path

        # Work from the object's type to match method resolution of other magic
        # methods.
        path_type = type(path)
        try:
            path = path_type.__fspath__(path)
        except AttributeError:
            # Added for Python 3.5 support.
            if isinstance(path, pathlib.Path):
                return str(path)
            elif hasattr(path_type, '__fspath__'):
                raise
        else:
            if isinstance(path, (str, bytes)):
                return path
            else:
                raise TypeError("expected __fspath__() to return str or bytes, "
                                "not " + type(path).__name__)

        raise TypeError(
            "expected str, bytes, pathlib.Path or os.PathLike object, not "
            + path_type.__name__)

else:
    fspath = os.fspath
