/*
 * This Source Code Form is subject to the terms of the Mozilla Public
 * License, v. 2.0. If a copy of the MPL was not distributed with this
 * file, You can obtain one at http://mozilla.org/MPL/2.0/.
 *
 * Copyright (C) 2017, James R. Barlow (https://github.com/jbarlow83/)
 */

/*
 * Convert Python types <-> QPDFObjectHandle types
 */

#include <vector>
#include <map>

#include <qpdf/Constants.h>
#include <qpdf/Types.h>
#include <qpdf/DLL.h>
#include <qpdf/QPDFExc.hh>
#include <qpdf/QPDFObjGen.hh>
#include <qpdf/PointerHolder.hh>
#include <qpdf/Buffer.hh>
#include <qpdf/QPDFObjectHandle.hh>
#include <qpdf/QPDF.hh>
#include <qpdf/QPDFWriter.hh>

#include <pybind11/pybind11.h>
#include <pybind11/stl.h>

#include "pikepdf.h"


std::map<std::string, QPDFObjectHandle>
dict_builder(py::dict dict)
{
    std::map<std::string, QPDFObjectHandle> result;

    for (auto item: dict) {
        std::string key = item.first.cast<std::string>();

        auto value = objecthandle_encode(item.second);
        result[key] = value;
    }
    return result;
}

std::vector<QPDFObjectHandle>
array_builder(py::iterable iter)
{
    std::vector<QPDFObjectHandle> result;
    int narg = 0;

    for (auto item: iter) {
        narg++;

        auto value = objecthandle_encode(item);
        result.push_back(value);
    }
    return result;
}


QPDFObjectHandle objecthandle_encode(py::handle handle)
{
    if (handle.is_none())
        return QPDFObjectHandle::newNull();

    // Ensure that when we return QPDFObjectHandle/pikepdf.Object to the Py
    // environment, that we can recover it
    try {
        auto as_qobj = handle.cast<QPDFObjectHandle>();
        return as_qobj;
    } catch (py::cast_error) {}

    // Special-case booleans since pybind11 coerces nonzero integers to boolean
    if (py::isinstance<py::bool_>(handle)) {
        bool as_bool = handle.cast<bool>();
        return QPDFObjectHandle::newBool(as_bool);
    }

    try {
        auto as_int = handle.cast<long long>();
        return QPDFObjectHandle::newInteger(as_int);
    } catch (py::cast_error) {}

    try {
        auto as_double = handle.cast<double>();
        return QPDFObjectHandle::newReal(as_double);
    } catch (py::cast_error) {}

    try {
        auto as_str = handle.cast<std::string>();
        return QPDFObjectHandle::newString(as_str);
    } catch (py::cast_error) {}

    py::object obj = py::reinterpret_borrow<py::object>(handle);

    if (py::isinstance<py::bytes>(obj)) {
        auto py_bytes = py::bytes(obj);
        auto as_str = (std::string)py_bytes;
        return QPDFObjectHandle::newString(as_str);
    }

    if (py::hasattr(obj, "__iter__")) {
        //py::print(py::repr(obj));
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

    if (obj.is(py::object())) {
        return QPDFObjectHandle::newNull();
    }

    throw py::cast_error(std::string("don't know how to encode value") + std::string(py::repr(obj)));
}


py::object decimal_from_pdfobject(QPDFObjectHandle& h)
{
    auto decimal_constructor = py::module::import("decimal").attr("Decimal");

    if (h.getTypeCode() == QPDFObject::object_type_e::ot_integer) {
        auto value = h.getIntValue();
        return decimal_constructor(py::cast(value));
    } else if (h.getTypeCode() == QPDFObject::object_type_e::ot_real) {
        auto value = h.getRealValue();
        return decimal_constructor(py::cast(value));
    }
    throw py::type_error("object has no Decimal() representation");
}


py::object objecthandle_decode(QPDFObjectHandle& h)
{
    py::object obj = py::none();

    switch (h.getTypeCode()) {
    case QPDFObject::object_type_e::ot_null:
        return py::none();
    case QPDFObject::object_type_e::ot_integer:
        obj = py::cast(h.getIntValue());
        break;
    case QPDFObject::object_type_e::ot_boolean:
        obj = py::cast(h.getBoolValue());
        break;
    case QPDFObject::object_type_e::ot_real:
        obj = decimal_from_pdfobject(h);
        break;
    case QPDFObject::object_type_e::ot_name:
        break;
    case QPDFObject::object_type_e::ot_string:
        obj = py::bytes(h.getStringValue());
        break;
    case QPDFObject::object_type_e::ot_operator:
        break;
    case QPDFObject::object_type_e::ot_inlineimage:
        break;
    case QPDFObject::object_type_e::ot_array:
        {
            py::list lst;
            for (auto item: h.getArrayAsVector()) {
                lst.append(objecthandle_decode(item));
            }
            obj = lst;
        }
        break;
    case QPDFObject::object_type_e::ot_dictionary:
        break;
    case QPDFObject::object_type_e::ot_stream:
        break;
    default:
        break;
    }

    if (obj.is_none())
        throw py::type_error("not decodable"); 

    return obj;
}