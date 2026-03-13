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

#include <pybind11/pybind11.h>
#include <pybind11/stl.h>

#include "pikepdf.h"

static py::handle get_decimal_cls()
{
    // Intentionally leaked to avoid destruction order issues at interpreter shutdown
    static auto *cls = new py::object(py::module_::import("decimal").attr("Decimal"));
    return *cls;
}

static py::handle get_decimal_getcontext()
{
    // Intentionally leaked to avoid destruction order issues at interpreter shutdown
    static auto *func =
        new py::object(py::module_::import("decimal").attr("getcontext"));
    return *func;
}

std::map<std::string, QPDFObjectHandle> dict_builder(const py::dict dict)
{
    StackGuard sg(" dict_builder");
    std::map<std::string, QPDFObjectHandle> result;

    for (const auto &item : dict) {
        result.emplace(
            item.first.cast<std::string>(), objecthandle_encode(item.second));
    }
    return result;
}

std::vector<QPDFObjectHandle> array_builder(const py::iterable iter)
{
    StackGuard sg(" array_builder");
    std::vector<QPDFObjectHandle> result;

    // If it's a list/tuple, pre-allocate memory
    if (py::isinstance<py::sequence>(iter)) {
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
        decimal_context = get_decimal_getcontext()();
        saved_precision = decimal_context.attr("prec").cast<uint>();
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
        return handle.cast<QPDFObjectHandle>();
    }

    auto *type_ptr = Py_TYPE(handle.ptr());

    if (type_ptr == &PyUnicode_Type) {
        Py_ssize_t size;
        const char *ptr = PyUnicode_AsUTF8AndSize(handle.ptr(), &size);

        if (!ptr) {
            throw py::error_already_set();
        }
        return QPDFObjectHandle::newUnicodeString(std::string(ptr, size));
    }
    if (type_ptr == &PyLong_Type) {
        return QPDFObjectHandle::newInteger(handle.cast<long long>());
    }
    if (type_ptr == &PyBool_Type) {
        return QPDFObjectHandle::newBool(handle.cast<bool>());
    }
    if (type_ptr == &PyFloat_Type) {
        double val = handle.cast<double>();
        if (!std::isfinite(val))
            throw py::value_error("Can't convert NaN or Infinity to PDF real number");
        return QPDFObjectHandle::newReal(val);
    }
    if (type_ptr == &PyBytes_Type) {
        return QPDFObjectHandle::newString(handle.cast<std::string>());
    }

    if (py::isinstance<QPDFObjectHelper>(handle)) {
        throw py::type_error("Can't convert ObjectHelper implicitly. Use .obj");
    }
    if (py::isinstance<QPDFObjectHandle::Rectangle>(handle)) {
        return QPDFObjectHandle::newFromRectangle(
            handle.cast<QPDFObjectHandle::Rectangle>());
    }

    auto Decimal = get_decimal_cls();
    if (py::isinstance(handle, Decimal)) {
        DecimalPrecision dp(get_decimal_precision());
        auto rounded =
            py::reinterpret_steal<py::object>(PyNumber_Positive(handle.ptr()));
        if (!rounded.attr("is_finite")().cast<bool>())
            throw py::value_error("Can't convert NaN or Infinity to PDF real number");

        auto as_decimal_string = std::string(py::str(rounded));
        if (as_decimal_string.find_first_of("Ee") != std::string::npos) {
            return QPDFObjectHandle::newReal(
                rounded.attr("__float__")().cast<double>());
        }
        return QPDFObjectHandle::newReal(as_decimal_string);
    }

    // Containers (recursive calls)
    if (py::hasattr(handle, "__iter__")) {
        if (py::hasattr(handle, "keys")) {
            return QPDFObjectHandle::newDictionary(
                dict_builder(handle.cast<py::dict>()));
        }
        if (PySequence_Check(handle.ptr())) {
            return QPDFObjectHandle::newArray(
                array_builder(handle.cast<py::iterable>()));
        }
    }

    throw py::cast_error(
        std::string("don't know how to encode value ") + std::string(py::repr(handle)));
}

py::object decimal_from_pdfobject(QPDFObjectHandle h)
{
    auto Decimal = get_decimal_cls();

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
