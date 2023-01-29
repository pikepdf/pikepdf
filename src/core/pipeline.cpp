// SPDX-FileCopyrightText: 2022 James R. Barlow
// SPDX-License-Identifier: MPL-2.0

#include <qpdf/Constants.h>
#include <qpdf/Types.h>
#include <qpdf/DLL.h>
#include <qpdf/QPDFExc.hh>
#include <qpdf/QPDF.hh>
#include <qpdf/Pipeline.hh>
#include <qpdf/QUtil.hh>

#include <pybind11/pybind11.h>
#include <pybind11/stl.h>

#include "pikepdf.h"
#include "pipeline.h"
#include "utils.h"

void Pl_PythonOutput::write(const unsigned char *buf, size_t len)
{
    py::gil_scoped_acquire gil;
    py::ssize_t so_far = 0;
    while (len > 0) {
        auto view_buffer  = py::memoryview::from_memory(buf, len);
        py::object result = this->stream.attr("write")(view_buffer);
        try {
            so_far = result.cast<py::ssize_t>();
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
    this->stream.attr("flush")();
}
