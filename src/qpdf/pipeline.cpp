/*
 * This Source Code Form is subject to the terms of the Mozilla Public
 * License, v. 2.0. If a copy of the MPL was not distributed with this
 * file, You can obtain one at http://mozilla.org/MPL/2.0/.
 *
 * Copyright (C) 2017, James R. Barlow (https://github.com/jbarlow83/)
 */


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
#include "pipeline.h"
#include "utils.h"


void Pl_PythonOutput::write(unsigned char *buf, size_t len)
{
    py::gil_scoped_acquire gil;
    ssize_t so_far = 0;
    while (len > 0) {
        py::memoryview view_buffer = memoryview_from_memory(buf, len);
        py::object result = this->stream.attr("write")(view_buffer);
        try {
            so_far = result.cast<ssize_t>();
        } catch (const py::cast_error &e) {
            throw py::type_error("Unexpected return type of write()");
        }
        if (so_far <= 0) {
            QUtil::throw_system_error(this->identifier);
        } else {
            auto diff = len - so_far;
            if (diff > len)
                throw py::value_error("Wrote more bytes than requested");
            buf += so_far;
            len -= so_far;
        }
    }
}

void Pl_PythonOutput::finish()
{
    py::gil_scoped_acquire gil;
    try {
        this->stream.attr("flush")();
    } catch (const py::attr_error &e) {
        // Suppress
    }
}
