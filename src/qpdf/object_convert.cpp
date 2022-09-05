// SPDX-FileCopyrightText: 2022 James R. Barlow
// SPDX-License-Identifier: MPL-2.0

/*
 * Convert Python types <-> QPDFObjectHandle types
 */

#include <vector>
#include <map>
#include <cmath>

#include <qpdf/Constants.h>
#include <qpdf/Types.h>
#include <qpdf/DLL.h>
#include <qpdf/QPDFExc.hh>
#include <qpdf/QPDFObjGen.hh>
#include <qpdf/QPDFObjectHandle.hh>
#include <qpdf/QPDF.hh>
#include <qpdf/QPDFWriter.hh>

#include <pybind11/pybind11.h>
#include <pybind11/stl.h>

#include "pikepdf.h"

extern uint DECIMAL_PRECISION;

std::map<std::string, QPDFObjectHandle> dict_builder(const py::dict dict)
{
    StackGuard sg(" dict_builder");
    std::map<std::string, QPDFObjectHandle> result;

    for (const auto &item : dict) {
        std::string key = item.first.cast<std::string>();

        auto value  = objecthandle_encode(item.second);
        result[key] = value;
    }
    return result;
}

std::vector<QPDFObjectHandle> array_builder(const py::iterable iter)
{
    StackGuard sg(" array_builder");
    std::vector<QPDFObjectHandle> result;
    int narg = 0;

    for (const auto &item : iter) {
        narg++;

        auto value = objecthandle_encode(item);
        result.push_back(value);
    }
    return result;
}

class DecimalPrecision {
public:
    DecimalPrecision(uint calc_precision)
        : decimal_context(py::module_::import("decimal").attr("getcontext")()),
          saved_precision(decimal_context.attr("prec").cast<uint>())
    {
        decimal_context.attr("prec") = calc_precision;
    }
    ~DecimalPrecision() { decimal_context.attr("prec") = saved_precision; }
    DecimalPrecision(const DecimalPrecision &other)            = delete;
    DecimalPrecision(DecimalPrecision &&other)                 = delete;
    DecimalPrecision &operator=(const DecimalPrecision &other) = delete;
    DecimalPrecision &operator=(DecimalPrecision &&other)      = delete;

private:
    py::object decimal_context;
    uint saved_precision;
};

QPDFObjectHandle objecthandle_encode(const py::handle handle)
{
    if (handle.is_none())
        return QPDFObjectHandle::newNull();

    // Ensure that when we return QPDFObjectHandle/pikepdf.Object to the Py
    // environment, that we can recover it
    try {
        auto as_qobj = handle.cast<QPDFObjectHandle>();
        return as_qobj;
    } catch (const py::cast_error &) {
    }

    if (py::isinstance<QPDFObjectHelper>(handle)) {
        throw py::type_error(
            "Can't convert ObjectHelper (or subclass) to Object implicitly. "
            "Use .obj to get access the underlying object.");
    }

    // Special-case booleans since pybind11 coerces nonzero integers to boolean
    if (py::isinstance<py::bool_>(handle)) {
        bool as_bool = handle.cast<bool>();
        return QPDFObjectHandle::newBool(as_bool);
    }

    auto decimal_module = py::module_::import("decimal");
    auto Decimal        = decimal_module.attr("Decimal");
    if (py::isinstance(handle, Decimal)) {
        DecimalPrecision dp(DECIMAL_PRECISION);
        auto rounded =
            py::reinterpret_steal<py::object>(PyNumber_Positive(handle.ptr()));
        if (!rounded.attr("is_finite")().cast<bool>())
            throw py::value_error("Can't convert NaN or Infinity to PDF real number");
        return QPDFObjectHandle::newReal(py::str(rounded));
    } else if (py::isinstance<py::int_>(handle)) {
        auto as_int = handle.cast<long long>();
        return QPDFObjectHandle::newInteger(as_int);
    } else if (py::isinstance<py::float_>(handle)) {
        auto as_double = handle.cast<double>();
        if (!std::isfinite(as_double))
            throw py::value_error("Can't convert NaN or Infinity to PDF real number");
        return QPDFObjectHandle::newReal(as_double);
    }

    py::object obj = py::reinterpret_borrow<py::object>(handle);

    if (py::isinstance<py::bytes>(obj)) {
        py::bytes py_bytes = obj;
        return QPDFObjectHandle::newString(static_cast<std::string>(py_bytes));
    } else if (py::isinstance<py::str>(obj)) {
        py::str py_str = obj;
        return QPDFObjectHandle::newUnicodeString(static_cast<std::string>(py_str));
    }

    if (py::hasattr(obj, "__iter__")) {
        // Kludge to prevent converting certain objects into Dictionary or Array
        // when passed, e.g. to Object.__setitem__('/Key', ...). Specifically
        // added for NameTree.
        if (py::hasattr(obj, "_pikepdf_disallow_objecthandle_encode")) {
            throw py::type_error(
                "Can't convert this object to pikepdf.Object implicitly.");
        }

        bool is_mapping = false; // PyMapping_Check is unreliable in Py3
        if (py::hasattr(obj, "keys"))
            is_mapping = true;

        bool is_sequence = PySequence_Check(obj.ptr());
        if (is_mapping) {
            return QPDFObjectHandle::newDictionary(dict_builder(obj));
        } else if (is_sequence) {
            return QPDFObjectHandle::newArray(array_builder(obj));
        }
    }

    throw py::cast_error(
        std::string("don't know how to encode value ") + std::string(py::repr(obj)));
}

py::object decimal_from_pdfobject(QPDFObjectHandle h)
{
    auto decimal_constructor = py::module_::import("decimal").attr("Decimal");

    if (h.getTypeCode() == qpdf_object_type_e::ot_integer) {
        auto value = h.getIntValue();
        return decimal_constructor(py::cast(value));
    } else if (h.getTypeCode() == qpdf_object_type_e::ot_real) {
        auto value = h.getRealValue();
        return decimal_constructor(py::cast(value));
    } else if (h.getTypeCode() == qpdf_object_type_e::ot_boolean) {
        auto value = h.getBoolValue();
        return decimal_constructor(py::cast(value));
    }
    throw py::type_error("object has no Decimal() representation");
}
