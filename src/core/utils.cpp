// SPDX-FileCopyrightText: 2022 James R. Barlow
// SPDX-License-Identifier: MPL-2.0

#include <cstdlib>
#include <system_error>

#include "utils.h"

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
