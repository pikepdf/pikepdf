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
#include <qpdf/Pipeline.hh>
#include <qpdf/QUtil.hh>

#include <pybind11/pybind11.h>
#include <pybind11/stl.h>

#include "pikepdf.h"


class Pl_PythonOutput : public Pipeline
{
public:
    Pl_PythonOutput(const char *identifier, py::object stream) :
        Pipeline(identifier, nullptr),
        stream(stream)
    {
    }

    virtual ~Pl_PythonOutput() = default;
    Pl_PythonOutput(const Pl_PythonOutput&) = delete;
    Pl_PythonOutput& operator= (const Pl_PythonOutput&) = delete;
    Pl_PythonOutput(Pl_PythonOutput&&) = delete;
    Pl_PythonOutput& operator= (Pl_PythonOutput&&) = delete;

    void write(unsigned char *buf, size_t len)
    {
        py::gil_scoped_acquire gil;
        size_t so_far = 0;
        while (len > 0) {
            py::buffer_info buffer(buf, len);
            py::memoryview view_buffer(buffer);
            py::object result = this->stream.attr("write")(view_buffer);
            try {
                so_far = result.cast<size_t>();
            } catch (const py::cast_error &e) {
                throw py::type_error("Unexpected return type of write()");
            }
            if (so_far == 0) {
                QUtil::throw_system_error(this->identifier);
            } else {
                buf += so_far;
                len -= so_far;
            }
        }
    }

    void finish()
    {
        py::gil_scoped_acquire gil;
        try {
            this->stream.attr("flush")();
        } catch (const py::attr_error &e) {
            // Suppress
        }
    }

private:
    py::object stream;
};
