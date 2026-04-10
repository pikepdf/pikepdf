// SPDX-FileCopyrightText: 2022 James R. Barlow
// SPDX-License-Identifier: MPL-2.0

#include <locale>
#include <sstream>

#include "parsers.h"
#include "pikepdf.h"

void PyParserCallbacks::handleObject(QPDFObjectHandle obj, size_t offset, size_t length)
{
    NB_OVERRIDE_NAME("handle_object", handleObject, obj, offset, length);
}

void PyParserCallbacks::handleEOF()
{
    NB_OVERRIDE_PURE_NAME("handle_eof", handleEOF);
}

void check_operand(QPDFObjectHandle obj)
{
    switch (obj.getTypeCode()) {
    case qpdf_object_type_e::ot_null:
    case qpdf_object_type_e::ot_boolean:
    case qpdf_object_type_e::ot_integer:
    case qpdf_object_type_e::ot_real:
    case qpdf_object_type_e::ot_name:
    case qpdf_object_type_e::ot_string:
    case qpdf_object_type_e::ot_inlineimage:
        break;
    case qpdf_object_type_e::ot_array: {
        if (obj.isIndirect()) {
            throw py::type_error(
                "Indirect arrays are not allowed in content stream instructions");
        }
        for (auto &inner : obj.aitems()) {
            check_operand(inner);
        }
        break;
    }
    case qpdf_object_type_e::ot_dictionary: {
        if (obj.isIndirect()) {
            throw py::type_error(
                "Indirect dictionaries are not allowed in content stream instructions");
        }
        for (auto &kv : obj.ditems()) {
            check_operand(kv.second);
        }
        break;
    }
    default: {
        throw py::type_error("Only scalar types, arrays, and dictionaries are allowed "
                             "in content streams.");
    }
    }
}

void check_objects_in_operands(std::vector<QPDFObjectHandle> &operands)
{
    for (QPDFObjectHandle &obj : operands) {
        check_operand(obj);
    }
}

ContentStreamInstruction::ContentStreamInstruction(
    ObjectList operands, QPDFObjectHandle operator_)
    : operands(operands), operator_(operator_)
{
    if (!this->operator_.isOperator())
        throw py::type_error("operator parameter must be a pikepdf.Operator");
    check_objects_in_operands(this->operands);
}

std::ostream &operator<<(std::ostream &os, ContentStreamInstruction &csi)
{
    for (QPDFObjectHandle &obj : csi.operands) {
        os << obj.unparse() << " ";
    }
    os << csi.operator_.unparse();
    return os;
}

py::object ContentStreamInlineImage::get_inline_image() const
{
    auto PdfInlineImage = py::module_::import_("pikepdf").attr("PdfInlineImage");
    auto kwargs = py::dict();
    kwargs["image_data"] = this->image_data;
    kwargs["image_object"] = this->image_metadata;
    auto iimage = PdfInlineImage(**kwargs);
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
    py::bytes ii_bytes =
        py::borrow<py::bytes>(csii.get_inline_image().attr("unparse")());

    os << to_string(ii_bytes);
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
                this->inline_metadata = ObjectList();
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

py::list OperandGrouper::getInstructions() const
{
    return this->instructions;
}
std::string OperandGrouper::getWarning() const
{
    return this->warning;
}

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

        if (py::isinstance<ContentStreamInstruction>(item)) {
            auto &csi = py::cast<ContentStreamInstruction &>(item);
            ss << csi;
            continue;
        }

        if (py::isinstance<ContentStreamInlineImage>(item)) {
            auto &csii = py::cast<ContentStreamInlineImage &>(item);
            ss << csii;
            continue;
        }

        // Fallback: instruction is some combination of Python iterables.
        // Destructure and convert to C++ types. Use py::object so we accept
        // both lists and tuples (and any sequence with __getitem__).
        py::object operands_op = py::borrow<py::object>(item);
        Py_ssize_t op_size = PyObject_Length(operands_op.ptr());
        if (op_size < 0) {
            throw py::python_error();
        }

        if ((size_t)op_size != 2) {
            errmsg << "Wrong number of operands at content stream instruction " << n
                   << "; expected 2";
            throw py::value_error(errmsg.str().c_str());
        }

        auto operator_ = operands_op[1];

        QPDFObjectHandle op;
        if (py::isinstance<py::str>(operator_)) {
            auto s = py::cast<std::string>(operator_);
            op = QPDFObjectHandle::newOperator(s.c_str());
        } else if (py::isinstance<py::bytes>(operator_)) {
            auto s = to_string(operator_);
            op = QPDFObjectHandle::newOperator(s.c_str());
        } else {
            op = py::cast<QPDFObjectHandle>(operator_);
            if (!op.isOperator()) {
                errmsg << "At content stream instruction " << n
                       << ", the operator is not of type pikepdf.Operator, bytes "
                          "or str";
                throw py::type_error(errmsg.str().c_str());
            }
        }

        if (op.getOperatorValue() == std::string("INLINE IMAGE")) {
            py::object operands_obj = py::borrow<py::object>(operands_op[0]);
            py::object iimage =
                py::borrow<py::object>(operands_obj.attr("__getitem__")(0));
            py::handle PdfInlineImage =
                py::module_::import_("pikepdf").attr("PdfInlineImage");
            if (!py::isinstance(iimage, PdfInlineImage)) {
                errmsg << "Expected PdfInlineImage as operand for instruction " << n;
                throw py::value_error(errmsg.str().c_str());
            }
            py::bytes iimage_unparsed_bytes =
                py::borrow<py::bytes>(iimage.attr("unparse")());
            ss << to_string(iimage_unparsed_bytes);
        } else {
            py::object operands_obj = py::borrow<py::object>(operands_op[0]);
            for (auto operand : operands_obj) {
                QPDFObjectHandle obj = objecthandle_encode(operand);
                ss << obj.unparse() << " ";
            }
            ss << op.unparse();
        }

        n++;
    }
    auto result_str = ss.str();
    return py::bytes(result_str.data(), result_str.size());
}

void init_parsers(py::module_ &m)
{
    py::class_<ContentStreamInstruction>(
        m, "ContentStreamInstruction", py::type_slots(pikepdf_gc_slots))
        .def(py::init<const ContentStreamInstruction &>())
        .def("__init__",
            [](ContentStreamInstruction *self,
                py::iterable operands,
                QPDFObjectHandle operator_) {
                ObjectList newlist;
                for (const auto &item : operands) {
                    newlist.emplace_back(objecthandle_encode(item));
                }
                new (self) ContentStreamInstruction(newlist, operator_);
            })
        .def_prop_ro(
            "operator",
            [](ContentStreamInstruction &csi) { return csi.operator_; },
            "The operator of used in this instruction.")
        .def_prop_ro(
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
                    (std::string("Invalid index ") + std::to_string(index)).c_str());
            },
            "``[0]`` returns the operands, and ``[1]`` returns the operator.")
        .def("__len__", [](ContentStreamInstruction &csi) { return 2; })
        .def("__repr__", [](ContentStreamInstruction &csi) {
            std::ostringstream ss;
            ss.imbue(std::locale::classic());
            ss << "pikepdf.ContentStreamInstruction("
               << py::cast<std::string>(py::repr(py::cast(csi.operands))) << ", "
               << objecthandle_repr(csi.operator_) << ")";
            return ss.str();
        });

    py::class_<ContentStreamInlineImage>(
        m, "ContentStreamInlineImage", py::type_slots(pikepdf_gc_slots))
        .def(py::init<const ContentStreamInlineImage &>())
        .def("__init__",
            [](ContentStreamInlineImage *self, py::object iimage) {
                auto data = iimage.attr("_data");
                auto image_object = iimage.attr("_image_object");

                new (self) ContentStreamInlineImage(py::cast<ObjectList>(image_object),
                    py::cast<QPDFObjectHandle>(data));
            })
        .def_prop_ro(
            "operator",
            [](ContentStreamInlineImage &csii) {
                return QPDFObjectHandle::newOperator("INLINE IMAGE");
            },
            "Always return the fictitious operator 'INLINE IMAGE'.")
        .def_prop_ro(
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
                    (std::string("Invalid index ") + std::to_string(index)).c_str());
            })
        .def("__len__", [](ContentStreamInlineImage &csii) { return 2; })
        .def_prop_ro(
            "iimage",
            [](ContentStreamInlineImage &csii) { return csii.get_inline_image(); },
            "Returns the inline image itself.")
        .def("__repr__", [](ContentStreamInlineImage &csii) {
            std::ostringstream ss;
            ss.imbue(std::locale::classic());
            ss << "<pikepdf.ContentStreamInlineImage("
               << "[" << py::cast<std::string>(py::repr(csii.get_inline_image()))
               << "], "
               << "pikepdf.Operator('INLINE IMAGE')"
               << ")>";
            return ss.str();
        });
}