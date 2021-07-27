/*
 * This Source Code Form is subject to the terms of the Mozilla Public
 * License, v. 2.0. If a copy of the MPL was not distributed with this
 * file, You can obtain one at http://mozilla.org/MPL/2.0/.
 *
 * Copyright (C) 2021, James R. Barlow (https://github.com/jbarlow83/)
 */

#pragma once

#include <pybind11/pybind11.h>
#include <pybind11/stl.h>
#include <qpdf/QPDFObjectHandle.hh>
#include <qpdf/QPDFTokenizer.hh>

class PyParserCallbacks : public QPDFObjectHandle::ParserCallbacks {
public:
    using QPDFObjectHandle::ParserCallbacks::ParserCallbacks;
    virtual ~PyParserCallbacks() = default;

    void handleObject(QPDFObjectHandle h) override;
    void handleEOF() override;
};

class OperandGrouper : public QPDFObjectHandle::ParserCallbacks {
public:
    OperandGrouper(const std::string &operators);
    void handleObject(QPDFObjectHandle obj) override;
    void handleEOF() override;

    py::list getInstructions() const;
    std::string getWarning() const;

private:
    std::set<std::string> whitelist;
    std::vector<QPDFObjectHandle> tokens;
    bool parsing_inline_image;
    std::vector<QPDFObjectHandle> inline_metadata;
    py::list instructions;
    uint count;
    std::string warning;
};

py::bytes unparse_content_stream(py::iterable contentstream);