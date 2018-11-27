/*
 * This Source Code Form is subject to the terms of the Mozilla Public
 * License, v. 2.0. If a copy of the MPL was not distributed with this
 * file, You can obtain one at http://mozilla.org/MPL/2.0/.
 *
 * Copyright (C) 2017, James R. Barlow (https://github.com/jbarlow83/)
 */

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


/* Open a file, accounting for encoding of the filename (hopefully)
 *
 * First use fspath to resolve the object to a str/bytes, if it is a fancy
 * path like pathlib.Path. Then ask Python to open it and hope for the best.
 *
 * If the path is a str on Windows then it probably needs to be converted to
 * a wide character string and opened with _wfopen.  If it's bytes on Windows
 * then the bytes probably express a UTF-16LE encoding of the path already in
 * which case we still want.
 *
 * Also the behavior of Python differs between 3.5 and 3.6, and further differs
 * based on what environment variables are set and what the current code page.
 * See PEP 529.
 *
 * On POSIX it's "easier": encode str to native filesystem encoding, and use
 * fopen(). With any luck, it's UTF-8 and everything will be okay.
 */
FILE *portable_fopen(py::object filename, const char* mode)
{
    auto path = fspath(filename);
    FILE *file;
    file = _Py_fopen_obj(path.ptr(), mode);
    if (!file)
        throw py::error_already_set();
    return file;
}
