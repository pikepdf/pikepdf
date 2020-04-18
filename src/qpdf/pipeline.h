/*
 * This Source Code Form is subject to the terms of the Mozilla Public
 * License, v. 2.0. If a copy of the MPL was not distributed with this
 * file, You can obtain one at http://mozilla.org/MPL/2.0/.
 *
 * Copyright (C) 2017, James R. Barlow (https://github.com/jbarlow83/)
 */

#pragma once

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

    void write(unsigned char *buf, size_t len) override;
    void finish() override;

private:
    py::object stream;
};
