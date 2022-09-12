// SPDX-FileCopyrightText: 2022 James R. Barlow
// SPDX-License-Identifier: MPL-2.0

#pragma once

#include <cstdio>
#include <cstring>

#include <qpdf/Constants.h>
#include <qpdf/Types.h>
#include <qpdf/DLL.h>
#include <qpdf/QPDFExc.hh>
#include <qpdf/Buffer.hh>
#include <qpdf/QPDF.hh>
#include <qpdf/Pipeline.hh>
#include <qpdf/QUtil.hh>

#include <pybind11/pybind11.h>
#include <pybind11/stl.h>

#include "pikepdf.h"

class Pl_PythonOutput : public Pipeline {
public:
    Pl_PythonOutput(const char *identifier, py::object stream)
        : Pipeline(identifier, nullptr), stream(stream)
    {
    }

    virtual ~Pl_PythonOutput()                          = default;
    Pl_PythonOutput(const Pl_PythonOutput &)            = delete;
    Pl_PythonOutput &operator=(const Pl_PythonOutput &) = delete;
    Pl_PythonOutput(Pl_PythonOutput &&)                 = delete;
    Pl_PythonOutput &operator=(Pl_PythonOutput &&)      = delete;

    void write(const unsigned char *buf, size_t len) override;
    void finish() override;

private:
    py::object stream;
};
