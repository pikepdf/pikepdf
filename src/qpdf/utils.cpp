/*
 * This Source Code Form is subject to the terms of the Mozilla Public
 * License, v. 2.0. If a copy of the MPL was not distributed with this
 * file, You can obtain one at http://mozilla.org/MPL/2.0/.
 *
 * Copyright (C) 2017, James R. Barlow (https://github.com/jbarlow83/)
 */

#include <cstdlib>
#include <system_error>

#include "utils.h"

/* POSIX functions on Windows have a leading underscore
 */
#if defined(_WIN32)
#   define posix_fdopen _fdopen
#   define posix_close  _close
#else
#   define posix_fdopen fdopen
#   define posix_close  close
#endif

/* Convert a Python object to a filesystem encoded path
 * Use Python's os.fspath() which accepts os.PathLike (str, bytes, pathlib.Path)
 * and returns bytes encoded in the filesystem encoding.
 * Cast to a string without transcoding.
 */

py::object fspath(py::object filename)
{
    py::handle handle = PyOS_FSPath(filename.ptr());
    if (!handle)
        throw py::error_already_set();
    return py::reinterpret_steal<py::object>(handle);
}
