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


#include <pybind11/pybind11.h>
#include <pybind11/stl.h>

#include "pikepdf.h"


class PythonInputSource : public InputSource
{
public:
    PythonInputSource(py::object stream) : stream(stream)
    {
        if (!stream.attr("seekable")())
            throw py::value_error("not seekable");
        this->name = py::cast<std::string>(py::repr(stream));
    }
    virtual ~PythonInputSource() {}

    std::string const& getName() const override
    {
        return this->name;
    }

    qpdf_offset_t tell() override
    {
        py::gil_scoped_acquire gil;
        return py::cast<qpdf_offset_t>(this->stream.attr("tell")());
    }

    void seek(qpdf_offset_t offset, int whence) override
    {
        py::gil_scoped_acquire gil;
        this->stream.attr("seek")(offset, whence);
    }

    void rewind() override
    {
        py::gil_scoped_acquire gil;
        this->stream.attr("seek")(0, 0);
    }

    size_t read(char* buffer, size_t length) override
    {
        py::gil_scoped_acquire gil;

        py::buffer_info buf_info(buffer, length);
        py::memoryview memview(buf_info);

        this->last_offset = this->tell();
        py::object result = this->stream.attr("readinto")(memview);
        if (result.is_none())
            return 0;
        size_t bytes_read = py::cast<size_t>(result);

        if (bytes_read == 0) {
            if (length > 0) {
                // EOF
                this->seek(0, SEEK_END);
                this->last_offset = this->tell();
            }
        }
        return bytes_read;
    }

    void unreadCh(char ch) override
    {
        this->seek(-1, SEEK_CUR);
    }

    qpdf_offset_t findAndSkipNextEOL() override
    {
        py::gil_scoped_acquire gil;
        this->stream.attr("readline")();
        return this->tell();
    }

private:
    py::object stream;
    std::string name;
};
