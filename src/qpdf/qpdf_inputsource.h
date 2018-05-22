/*
 * This Source Code Form is subject to the terms of the Mozilla Public
 * License, v. 2.0. If a copy of the MPL was not distributed with this
 * file, You can obtain one at http://mozilla.org/MPL/2.0/.
 *
 * Copyright (C) 2017, James R. Barlow (https://github.com/jbarlow83/)
 */

#include <cstdio>
#include <cstring>

#include <qpdf/Constants.h>
#include <qpdf/Types.h>
#include <qpdf/DLL.h>
#include <qpdf/QPDFExc.hh>
#include <qpdf/PointerHolder.hh>
#include <qpdf/Buffer.hh>
#include <qpdf/QPDF.hh>
#include <qpdf/InputSource.hh>
#include <qpdf/FileInputSource.hh>


#include <pybind11/pybind11.h>
#include <pybind11/stl.h>

#include "pikepdf.h"


class PythonIoInputSource : public FileInputSource
{
public:
    PythonIoInputSource(py::object stream) : stream(stream)
    {
        if (!stream.attr("seekable")())
            throw py::value_error("not seekable");
    }
    virtual ~PythonIoInputSource() {}

    virtual qpdf_offset_t findAndSkipNextEOL() = 0;

    std::string const& getName() const override
    {
        return py::repr(stream);
    }

    qpdf_offset_t tell() override
    {
        return static_cast<qpdf_offset_t>(stream.attr("tell")());
    }

    void seek(qpdf_offset_t offset, int whence) override
    {
        stream.attr("seek")(offset, whence);
    }

    void rewind() override
    {
        stream.attr("seek")(0, 0);
    }

    size_t read(char* buffer, size_t length) override
    {
        this->last_offset = this->tell();
        py::bytes chunk = stream.attr("read")(length);
        size_t bytes_read = chunk.attr("__len__")();

        if (bytes_read == 0) {
            if (length > 0) {
                // EOF
                this->seek(0, SEEK_END);
                this->last_offset = this->tell();
            }
        }

        char *chunk_buffer;
        Py_ssize_t *chunk_size;
        if (PYBIND11_BYTES_AS_STRING_AND_SIZE(chunk.ptr(), &chunk_buffer, &chunk_size))
            throw py::value_error("failed to read");
        memcpy(buffer, chunk_buffer, bytes_read);
        return bytes_read;
    }

    void unreadCh(char ch) override
    {
        this->seek(-1, SEEK_CUR);
    }

private:
    py::object stream;
};
