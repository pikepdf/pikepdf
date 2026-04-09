// SPDX-FileCopyrightText: 2022 James R. Barlow
// SPDX-License-Identifier: MPL-2.0

/*
 * Convert Python types <-> QPDFObjectHandle types
 */

#include <cmath>
#include <map>
#include <vector>

#include <qpdf/Constants.h>
#include <qpdf/DLL.h>
#include <qpdf/QPDF.hh>
#include <qpdf/QPDFExc.hh>
#include <qpdf/QPDFObjGen.hh>
#include <qpdf/QPDFObjectHandle.hh>
#include <qpdf/QPDFWriter.hh>
#include <qpdf/Types.h>

#include "pikepdf.h"

std::map<std::string, QPDFObjectHandle> dict_builder(const py::dict dict)
{
    StackGuard sg(" dict_builder");
    std::map<std::string, QPDFObjectHandle> result;

    for (const auto &item : dict) {
        result.emplace(to_string(item.first), objecthandle_encode(item.second));
    }
    return result;
}

std::vector<QPDFObjectHandle> array_builder(const py::iterable iter)
{
    StackGuard sg(" array_builder");
    std::vector<QPDFObjectHandle> result;

    // If it's a list/tuple, pre-allocate memory
    if (py::isinstance<py::list>(iter) || py::isinstance<py::tuple>(iter)) {
        result.reserve(py::len(iter));
    }

    for (const auto &item : iter) {
        result.emplace_back(objecthandle_encode(item));
    }
    return result;
}

class DecimalPrecision {
public:
    DecimalPrecision(uint calc_precision)
    {
        decimal_context = py::module_::import_("decimal").attr("getcontext")();
        saved_precision = py::cast<uint>(decimal_context.attr("prec"));
        decimal_context.attr("prec") = calc_precision;
    }
    ~DecimalPrecision() { decimal_context.attr("prec") = saved_precision; }
    DecimalPrecision(const DecimalPrecision &other) = delete;
    DecimalPrecision(DecimalPrecision &&other) = delete;
    DecimalPrecision &operator=(const DecimalPrecision &other) = delete;
    DecimalPrecision &operator=(DecimalPrecision &&other) = delete;

private:
    py::object decimal_context;
    uint saved_precision;
};

QPDFObjectHandle objecthandle_encode(const py::handle handle)
{
    if (handle.is_none())
        return QPDFObjectHandle::newNull();

    if (py::isinstance<QPDFObjectHandle>(handle)) {
        return py::cast<QPDFObjectHandle>(handle);
    }

    auto *type_ptr = Py_TYPE(handle.ptr());

    if (type_ptr == &PyUnicode_Type) {
        Py_ssize_t size;
        const char *ptr = PyUnicode_AsUTF8AndSize(handle.ptr(), &size);

        if (!ptr) {
            throw py::python_error();
        }
        return QPDFObjectHandle::newUnicodeString(std::string(ptr, size));
    }
    if (type_ptr == &PyLong_Type) {
        return QPDFObjectHandle::newInteger(py::cast<long long>(handle));
    }
    if (type_ptr == &PyBool_Type) {
        return QPDFObjectHandle::newBool(py::cast<bool>(handle));
    }
    if (type_ptr == &PyFloat_Type) {
        double val = py::cast<double>(handle);
        if (!std::isfinite(val))
            throw py::value_error("Can't convert NaN or Infinity to PDF real number");
        return QPDFObjectHandle::newReal(val);
    }
    if (type_ptr == &PyBytes_Type) {
        Py_ssize_t size;
        char *ptr;
        if (PyBytes_AsStringAndSize(handle.ptr(), &ptr, &size) != 0) {
            throw py::python_error();
        }
        return QPDFObjectHandle::newString(std::string(ptr, size));
    }

    if (py::isinstance<QPDFObjectHelper>(handle)) {
        throw py::type_error("Can't convert ObjectHelper implicitly. Use .obj");
    }
    if (py::isinstance<QPDFObjectHandle::Rectangle>(handle)) {
        return QPDFObjectHandle::newFromRectangle(
            py::cast<QPDFObjectHandle::Rectangle>(handle));
    }

    auto Decimal = py::module_::import_("decimal").attr("Decimal");
    if (py::isinstance(handle, Decimal)) {
        DecimalPrecision dp(get_decimal_precision());
        auto rounded = py::steal<py::object>(PyNumber_Positive(handle.ptr()));
        if (!py::cast<bool>(rounded.attr("is_finite")()))
            throw py::value_error("Can't convert NaN or Infinity to PDF real number");

        auto as_decimal_string = py::cast<std::string>(py::str(rounded));
        if (as_decimal_string.find_first_of("Ee") != std::string::npos) {
            return QPDFObjectHandle::newReal(
                py::cast<double>(rounded.attr("__float__")()));
        }
        return QPDFObjectHandle::newReal(as_decimal_string);
    }

    // Containers (recursive calls)
    if (py::hasattr(handle, "__iter__")) {
        if (py::hasattr(handle, "keys")) {
            return QPDFObjectHandle::newDictionary(
                dict_builder(py::cast<py::dict>(handle)));
        }
        if (PySequence_Check(handle.ptr())) {
            return QPDFObjectHandle::newArray(
                array_builder(py::cast<py::iterable>(handle)));
        }
    }

    throw std::runtime_error(std::string("don't know how to encode value ") +
                             py::cast<std::string>(py::repr(handle)));
}

py::object decimal_from_pdfobject(QPDFObjectHandle h)
{
    auto Decimal = py::module_::import_("decimal").attr("Decimal");

    if (h.getTypeCode() == qpdf_object_type_e::ot_integer) {
        auto value = h.getIntValue();
        return Decimal(py::cast(value));
    } else if (h.getTypeCode() == qpdf_object_type_e::ot_real) {
        auto value = h.getRealValue();
        return Decimal(py::cast(value));
    } else if (h.getTypeCode() == qpdf_object_type_e::ot_boolean) {
        auto value = h.getBoolValue();
        return Decimal(py::cast(value));
    }
    throw py::type_error("object has no Decimal() representation");
}
