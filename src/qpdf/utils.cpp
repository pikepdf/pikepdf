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

/* Convert a Python object to a filesystem encoded path
 * Use Python's os.fspath() which accepts os.PathLike (str, bytes, pathlib.Path)
 * and returns bytes encoded in the filesystem encoding.
 * Cast to a string without transcoding.
 */

#if PY_VERSION_HEX < 0x03060000

    py::object fspath(py::object filename)
    {
        auto py_fspath = py::module::import("pikepdf._cpphelpers").attr("fspath");
        return py_fspath(filename);
    }

#else

    py::object fspath(py::object filename)
    {
        py::handle handle = PyOS_FSPath(filename.ptr());
        if (!handle)
            throw py::error_already_set();
        return py::reinterpret_steal<py::object>(handle);
    }

#endif


/* Open a file, accounting for encoding of the filename
 *
 * First use fspath to resolve the object to a str/bytes, if it is a fancy
 * path like pathlib.Path. Then ask Python to open it.
 *
 * This is surprisingly hard to get right. Filename could be PathLike or str
 * or bytes. If on Windows, filename needs to be wchar_t and we need to use
 * _wfopen. Some environment variables factor in. So this awkward approach
 * let us delegate all the details to Python.
 *
 * Ideally we would just use _Py_fopen_obj, but that is a private API.
 */
FILE *portable_fopen(py::object filename, const char* mode)
{
    auto path = fspath(filename);
    auto io_open = py::module::import("io").attr("open");
    py::object pyfile;
    py::int_ filedes = {-1};
    py::int_ filedes_dup = {-1};

    // Use Python's builtin open to open the file, since it takes care of
    // all of filename encoding issues and interprets mode
    pyfile = io_open(path, mode);
    try {
        // Get file descriptor, and dup() it
        filedes = pyfile.attr("fileno")();
        filedes_dup = py::module::import("os").attr("dup")(filedes);
    } catch (const std::exception &e) {
        pyfile.attr("close")();
        throw;
    }

    try {
        // Close original, releasing Python's buffers. We still have the duplicate
        // descriptor.
        pyfile.attr("close")();

        // Now use stdlib to wrap descriptor as a FILE
        FILE *file = fdopen(filedes_dup, mode);
        if (!file)
            throw std::system_error(errno, std::generic_category());
        return file;
    } catch (const std::exception &e) {
        if (filedes_dup.cast<int>() >= 0)
            close(filedes_dup);
        throw;
    }
}

/* Delete a filename
 *
 * equivalent to
 * with suppress(FileNotFoundError):
 *     os.unlink(f)
 */
void portable_unlink(py::object filename)
{
    auto path = fspath(filename);
    auto os_unlink = py::module::import("os").attr("unlink");
    try {
        os_unlink(path);
    } catch (const std::exception &e) {  // py::filenotfound_error doesn't work; pybind11 issue?
        // Discard exception
    }
}
