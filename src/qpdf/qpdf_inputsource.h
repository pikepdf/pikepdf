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
        if (!stream.attr("readable")())
            throw py::value_error("not readable");
        if (!stream.attr("seekable")())
            throw py::value_error("not seekable");
        this->name = py::cast<std::string>(py::repr(stream));
    }
    virtual ~PythonInputSource() = default;
    PythonInputSource(const PythonInputSource&) = delete;
    PythonInputSource& operator= (const PythonInputSource&) = delete;
    PythonInputSource(PythonInputSource&&) = delete;
    PythonInputSource& operator= (PythonInputSource&&) = delete;

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
        this->seek(0, SEEK_SET);
    }

    size_t read(char* buffer, size_t length) override
    {
        py::gil_scoped_acquire gil;

        py::buffer_info buffer_info(buffer, length);
        py::memoryview view_buffer_info(buffer_info);

        this->last_offset = this->tell();
        py::object result = this->stream.attr("readinto")(view_buffer_info);
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

        qpdf_offset_t result = 0;
        bool done = false;
        bool eol_straddles_buf = false;
        std::string buf(4096, '\0');
        std::string line_endings = "\r\n";

        while (!done) {
            qpdf_offset_t cur_offset = this->tell();
            size_t len = this->read(const_cast<char *>(buf.data()), buf.size());
            if (len == 0) {
                done = true;
                result = this->tell();
            } else {
                size_t found;
                if (!eol_straddles_buf) {
                    found = buf.find_first_of(line_endings);
                    if (found == std::string::npos)
                        continue;
                } else {
                    found = 0;
                }

                size_t found_end = buf.find_first_not_of(line_endings, found);
                if (found_end == std::string::npos) {
                    eol_straddles_buf = true;
                    continue;
                }
                result = cur_offset + found_end;
                this->seek(result, SEEK_SET);
                done = true;
            }
        }
        return result;
    }

private:
    py::object stream;
    std::string name;
};
