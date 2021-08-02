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

void PyParserCallbacks::handleObject(QPDFObjectHandle obj, size_t offset, size_t length)
{
    PYBIND11_OVERRIDE_NAME(void,
        QPDFObjectHandle::ParserCallbacks,
        "handle_object", /* Python name */
        handleObject,    /* C++ name */
        obj,
        offset,
        length);
}

void PyParserCallbacks::handleEOF()
{
    PYBIND11_OVERRIDE_PURE_NAME(void,
        QPDFObjectHandle::ParserCallbacks,
        "handle_eof", /* Python name */
        handleEOF,    /* C++ name; trailing comma needed for macro */
    );
}

ContentStreamInstruction::ContentStreamInstruction(
    ObjectList operands, QPDFObjectHandle operator_)
    : operands(operands), operator_(operator_)
{
}

std::ostream &operator<<(std::ostream &os, ContentStreamInstruction &csi)
{
    for (QPDFObjectHandle &obj : csi.operands) {
        os << obj.unparseBinary() << " ";
    }
    os << csi.operator_.unparseBinary();
    return os;
}

// ObjectList ContentStreamInstruction::getOperands() { return this->operands; }

// QPDFObjectHandle ContentStreamInstruction::getOperator() { return this->operator_; }

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
                kwargs["image_data"]   = this->tokens[0];
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
            ContentStreamInstruction csi(this->tokens, obj);
            this->instructions.append(csi);
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
        ss << delim;
        delim = "\n";

        try {
            auto csi = py::cast<ContentStreamInstruction>(item);
            ss << csi;
            continue;
        } catch (py::cast_error &) {
        }

        auto operands_op = py::reinterpret_borrow<py::sequence>(item);

        // First iteration: print nothing
        // All others: print "\n" to delimit previous
        // Result is no leading or trailing delimiter

        if (operands_op.size() != 2) {
            errmsg << "Wrong number of operands at content stream instruction " << n
                   << "; expected 2";
            throw py::value_error(errmsg.str());
        }

        auto operator_ = operands_op[1];

        QPDFObjectHandle op;
        if (py::isinstance<py::str>(operator_)) {
            py::str s = py::reinterpret_borrow<py::str>(operator_);
            op        = QPDFObjectHandle::newOperator(std::string(s).c_str());
        } else if (py::isinstance<py::bytes>(operator_)) {
            py::bytes s = py::reinterpret_borrow<py::bytes>(operator_);
            op          = QPDFObjectHandle::newOperator(std::string(s).c_str());
        } else {
            op = operator_.cast<QPDFObjectHandle>();
            if (!op.isOperator()) {
                errmsg
                    << "At content stream instruction " << n
                    << ", the operator is not of type pikepdf.Operator, bytes or str";
                throw py::type_error(errmsg.str());
            }
        }

        if (op.getOperatorValue() == std::string("INLINE IMAGE")) {
            auto operands     = py::reinterpret_borrow<py::sequence>(operands_op[0]);
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
            // try {
            //     // First try direct conversion...
            //     auto objectlist =
            //     operands_op[0].cast<std::vector<QPDFObjectHandle>>(); for
            //     (QPDFObjectHandle &obj : objectlist) {
            //         ss << obj.unparseBinary() << " ";
            //     }
            // } catch (const py::cast_error &) {
            auto operands = py::reinterpret_borrow<py::sequence>(operands_op[0]);
            for (const auto &operand : operands) {
                QPDFObjectHandle obj = objecthandle_encode(operand);
                ss << obj.unparseBinary() << " ";
            }
            // }
            ss << op.unparseBinary();
        }

        n++;
    }
    return py::bytes(ss.str());
}

void init_parsers(py::module_ &m)
{
    py::class_<ContentStreamInstruction>(m, "ContentStreamInstruction")
        .def_property(
            "operator",
            [](ContentStreamInstruction &csi) { return csi.operator_; },
            [](ContentStreamInstruction &csi, QPDFObjectHandle op) {
                csi.operator_ = op;
            })
        .def_property(
            "operands",
            [](ContentStreamInstruction &csi) { return csi.operands; },
            [](ContentStreamInstruction &csi, py::object objlist) {
                if (py::isinstance<ObjectList>(objlist)) {
                    csi.operands = py::cast<ObjectList>(objlist);
                } else {
                    ObjectList newlist;
                    for (auto &item : objlist) {
                        newlist.push_back(objecthandle_encode(item));
                    }
                    csi.operands = newlist;
                }
            })
        .def("__getitem__",
            [](ContentStreamInstruction &csi, int index) {
                if (index == 0 || index == -2)
                    return py::cast(csi.operands);
                else if (index == 1 || index == -1)
                    return py::cast(csi.operator_);
                throw py::index_error(
                    std::string("Invalid index ") + std::to_string(index));
            })
        .def("__repr__", [](ContentStreamInstruction &csi) {
            return "pikepdf.ContentStreamInstruction()";
        });
}