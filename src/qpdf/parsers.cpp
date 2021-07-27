/*
 * This Source Code Form is subject to the terms of the Mozilla Public
 * License, v. 2.0. If a copy of the MPL was not distributed with this
 * file, You can obtain one at http://mozilla.org/MPL/2.0/.
 *
 * Copyright (C) 2021, James R. Barlow (https://github.com/jbarlow83/)
 */

#include <sstream>
#include <locale>

#include "pikepdf.h"
#include "parsers.h"

void PyParserCallbacks::handleObject(QPDFObjectHandle h)
{
    PYBIND11_OVERLOAD_PURE_NAME(void,
        QPDFObjectHandle::ParserCallbacks,
        "handle_object", /* Python name */
        handleObject,    /* C++ name */
        h);
}

void PyParserCallbacks::handleEOF()
{
    PYBIND11_OVERLOAD_PURE_NAME(void,
        QPDFObjectHandle::ParserCallbacks,
        "handle_eof", /* Python name */
        handleEOF,    /* C++ name; trailing comma needed for macro */
    );
}

OperandGrouper::OperandGrouper(const std::string &operators)
    : parsing_inline_image(false), count(0)
{
    std::istringstream f(operators);
    f.imbue(std::locale::classic());
    std::string s;
    while (std::getline(f, s, ' ')) {
        this->whitelist.insert(s);
    }
}

void OperandGrouper::handleObject(QPDFObjectHandle obj)
{
    this->count++;
    if (obj.getTypeCode() == QPDFObject::object_type_e::ot_operator) {
        std::string op = obj.getOperatorValue();

        // If we have a whitelist and this operator is not on the whitelist,
        // discard it and all the tokens we collected
        if (!this->whitelist.empty()) {
            if (op[0] == 'q' || op[0] == 'Q') {
                // We have token with multiple stack push/pops
                if (this->whitelist.count("q") == 0 &&
                    this->whitelist.count("Q") == 0) {
                    this->tokens.clear();
                    return;
                }
            } else if (this->whitelist.count(op) == 0) {
                this->tokens.clear();
                return;
            }
        }
        if (op == "BI") {
            this->parsing_inline_image = true;
        } else if (this->parsing_inline_image) {
            if (op == "ID") {
                this->inline_metadata = this->tokens;
            } else if (op == "EI") {
                auto PdfInlineImage =
                    py::module_::import("pikepdf").attr("PdfInlineImage");
                auto kwargs            = py::dict();
                kwargs["image_data"]   = this->tokens.at(0);
                kwargs["image_object"] = this->inline_metadata;
                auto iimage            = PdfInlineImage(**kwargs);

                // Package as list with single element for consistency
                auto iimage_list = py::list();
                iimage_list.append(iimage);

                auto instruction = py::make_tuple(
                    iimage_list, QPDFObjectHandle::newOperator("INLINE IMAGE"));
                this->instructions.append(instruction);

                this->parsing_inline_image = false;
                this->inline_metadata.clear();
            }
        } else {
            py::list operand_list = py::cast(this->tokens);
            auto instruction      = py::make_tuple(operand_list, obj);
            this->instructions.append(instruction);
        }
        this->tokens.clear();
    } else {
        this->tokens.push_back(obj);
    }
}

void OperandGrouper::handleEOF()
{
    if (!this->tokens.empty())
        this->warning = "Unexpected end of stream";
}

py::list OperandGrouper::getInstructions() const { return this->instructions; }
std::string OperandGrouper::getWarning() const { return this->warning; }

py::bytes unparse_content_stream(py::iterable contentstream)
{
    uint n = 0;
    std::ostringstream ss, errmsg;
    const char *delim = "";
    ss.imbue(std::locale::classic());

    for (const auto &item : contentstream) {
        auto operands_op = py::reinterpret_borrow<py::sequence>(item);
        auto operands    = py::reinterpret_borrow<py::sequence>(operands_op[0]);

        // First iteration: print nothing
        // All others: print "\n" to delimit previous
        // Result is no leading or trailing delimiter
        ss << delim;
        delim = "\n";

        if (operands_op.size() != 2) {
            errmsg << "Wrong number of operands at content stream instruction " << n
                   << "; expected 2";
            throw py::value_error(errmsg.str());
        }

        QPDFObjectHandle operator_;
        if (py::isinstance<py::str>(operands_op[1])) {
            py::str s = py::reinterpret_borrow<py::str>(operands_op[1]);
            operator_ = QPDFObjectHandle::newOperator(std::string(s).c_str());
        } else if (py::isinstance<py::bytes>(operands_op[1])) {
            py::bytes s = py::reinterpret_borrow<py::bytes>(operands_op[1]);
            operator_   = QPDFObjectHandle::newOperator(std::string(s).c_str());
        } else {
            operator_ = operands_op[1].cast<QPDFObjectHandle>();
            if (!operator_.isOperator()) {
                errmsg
                    << "At content stream instruction " << n
                    << ", the operator is not of type pikepdf.Operator, bytes or str";
                throw py::type_error(errmsg.str());
            }
        }

        if (operator_.getOperatorValue() == std::string("INLINE IMAGE")) {
            py::object iimage = operands[0];
            py::handle PdfInlineImage =
                py::module::import("pikepdf").attr("PdfInlineImage");
            if (!py::isinstance(iimage, PdfInlineImage)) {
                errmsg << "Expected PdfInlineImage as operand for instruction " << n;
                throw py::value_error(errmsg.str());
            }
            py::object iimage_unparsed_bytes = iimage.attr("unparse")();
            ss << std::string(py::bytes(iimage_unparsed_bytes));
        } else {
            for (const auto &operand : operands) {
                QPDFObjectHandle obj = objecthandle_encode(operand);
                ss << obj.unparseBinary() << " ";
            }
            ss << operator_.unparseBinary();
        }

        n++;
    }
    return py::bytes(ss.str());
}