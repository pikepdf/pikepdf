// SPDX-FileCopyrightText: 2022 James R. Barlow
// SPDX-License-Identifier: MPL-2.0

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
    if (!this->operator_.isOperator())
        throw py::type_error("operator parameter must be a pikepdf.Operator");
}

std::ostream &operator<<(std::ostream &os, ContentStreamInstruction &csi)
{
    for (QPDFObjectHandle &obj : csi.operands) {
        os << obj.unparseBinary() << " ";
    }
    os << csi.operator_.unparseBinary();
    return os;
}

ContentStreamInlineImage::ContentStreamInlineImage(
    ObjectList image_metadata, QPDFObjectHandle image_data)
    : image_metadata(image_metadata), image_data(image_data)
{
}

py::object ContentStreamInlineImage::get_inline_image() const
{
    auto PdfInlineImage    = py::module_::import("pikepdf").attr("PdfInlineImage");
    auto kwargs            = py::dict();
    kwargs["image_data"]   = this->image_data;
    kwargs["image_object"] = this->image_metadata;
    auto iimage            = PdfInlineImage(**kwargs);
    return iimage;
}

py::list ContentStreamInlineImage::get_operands() const
{
    auto list = py::list();
    list.append(this->get_inline_image());
    return list;
}

QPDFObjectHandle ContentStreamInlineImage::get_operator() const
{
    return QPDFObjectHandle::newOperator("INLINE IMAGE");
}

std::ostream &operator<<(std::ostream &os, ContentStreamInlineImage &csii)
{
    py::bytes ii_bytes = csii.get_inline_image().attr("unparse")();

    os << std::string(ii_bytes);
    return os;
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
    if (obj.getTypeCode() == qpdf_object_type_e::ot_operator) {
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
                ContentStreamInlineImage csii(this->inline_metadata, this->tokens[0]);
                this->instructions.append(csii);
                this->inline_metadata      = ObjectList();
                this->parsing_inline_image = false;
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
    ss.imbue(std::locale::classic());
    errmsg.imbue(std::locale::classic());
    const char *delim = "";

    for (const auto &item : contentstream) {
        // First iteration: print nothing
        // All others: print "\n" to delimit previous
        // Result is no leading or trailing delimiter
        ss << delim;
        delim = "\n";

        try {
            auto csi = py::cast<ContentStreamInstruction>(item);
            ss << csi;
            continue;
        } catch (py::cast_error &) {
        }

        try {
            auto csii = py::cast<ContentStreamInlineImage>(item);
            ss << csii;
            continue;
        } catch (py::cast_error &) {
        }

        // Fallback: instruction is some combination of Python iterables.
        // Destructure and convert to C++ types...
        auto operands_op = py::reinterpret_borrow<py::sequence>(item);

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
            py::bytes iimage_unparsed_bytes = iimage.attr("unparse")();
            ss << std::string(iimage_unparsed_bytes);
        } else {
            auto operands = py::reinterpret_borrow<py::sequence>(operands_op[0]);
            for (const auto &operand : operands) {
                QPDFObjectHandle obj = objecthandle_encode(operand);
                ss << obj.unparseBinary() << " ";
            }
            ss << op.unparseBinary();
        }

        n++;
    }
    return py::bytes(ss.str());
}

void init_parsers(py::module_ &m)
{
    py::class_<ContentStreamInstruction>(m, "ContentStreamInstruction")
        .def(py::init<const ContentStreamInstruction &>())
        .def(py::init([](py::iterable operands, QPDFObjectHandle operator_) {
            ObjectList newlist;
            for (auto &item : operands) {
                newlist.push_back(objecthandle_encode(item));
            }
            return ContentStreamInstruction(newlist, operator_);
        }))
        .def_property_readonly(
            "operator",
            [](ContentStreamInstruction &csi) { return csi.operator_; },
            "The operator of used in this instruction.")
        .def_property_readonly(
            "operands",
            [](ContentStreamInstruction &csi) { return csi.operands; },
            "The operands (parameters) supplied to the operator.")
        .def(
            "__getitem__",
            [](ContentStreamInstruction &csi, int index) {
                if (index == 0 || index == -2)
                    return py::cast(csi.operands);
                else if (index == 1 || index == -1)
                    return py::cast(csi.operator_);
                throw py::index_error(
                    std::string("Invalid index ") + std::to_string(index));
            },
            "``[0]`` returns the operands, and ``[1]`` returns the operator.")
        .def("__len__", [](ContentStreamInstruction &csi) { return 2; })
        .def("__repr__", [](ContentStreamInstruction &csi) {
            std::ostringstream ss;
            ss.imbue(std::locale::classic());
            ss << "pikepdf.ContentStreamInstruction("
               << py::repr(py::cast(csi.operands)) << ", "
               << objecthandle_repr(csi.operator_) << ")";
            return ss.str();
        });

    py::class_<ContentStreamInlineImage>(m, "ContentStreamInlineImage")
        .def(py::init<const ContentStreamInlineImage &>())
        .def(py::init([](py::object iimage) {
            auto data         = iimage.attr("_data");
            auto image_object = iimage.attr("_image_object");

            return ContentStreamInlineImage(
                image_object.cast<ObjectList>(), data.cast<QPDFObjectHandle>());
        }))
        .def_property_readonly(
            "operator",
            [](ContentStreamInlineImage &csii) {
                return QPDFObjectHandle::newOperator("INLINE IMAGE");
            },
            "Always return the fictitious operator 'INLINE IMAGE'.")
        .def_property_readonly(
            "operands",
            [](ContentStreamInlineImage &csii) { return csii.get_operands(); },
            "Returns a list of operands, whose sole entry is the inline image.")
        .def("__getitem__",
            [](ContentStreamInlineImage &csii, int index) -> py::object {
                if (index == 0 || index == -2)
                    return csii.get_operands();
                else if (index == 1 || index == -1)
                    return py::cast(csii.get_operator());
                throw py::index_error(
                    std::string("Invalid index ") + std::to_string(index));
            })
        .def("__len__", [](ContentStreamInlineImage &csii) { return 2; })
        .def_property_readonly(
            "iimage",
            [](ContentStreamInlineImage &csii) { return csii.get_inline_image(); },
            "Returns the inline image itself.")
        .def("__repr__", [](ContentStreamInlineImage &csii) {
            std::ostringstream ss;
            ss.imbue(std::locale::classic());
            ss << "<pikepdf.ContentStreamInlineImage("
               << "[" << py::repr(csii.get_inline_image()) << "], "
               << "pikepdf.Operator('INLINE IMAGE')"
               << ")>";
            return ss.str();
        });
}