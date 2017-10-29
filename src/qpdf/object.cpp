/*
 * This Source Code Form is subject to the terms of the Mozilla Public
 * License, v. 2.0. If a copy of the MPL was not distributed with this
 * file, You can obtain one at http://mozilla.org/MPL/2.0/.
 *
 * Copyright (C) 2017, James R. Barlow (https://github.com/jbarlow83/)
 */

#include <sstream>
#include <iostream>
#include <iomanip>
#include <math.h>

#include <qpdf/Constants.h>
#include <qpdf/Types.h>
#include <qpdf/DLL.h>
#include <qpdf/QPDFExc.hh>
#include <qpdf/QPDFObjGen.hh>
#include <qpdf/QPDFXRefEntry.hh>
#include <qpdf/PointerHolder.hh>
#include <qpdf/Buffer.hh>
#include <qpdf/QPDFObjectHandle.hh>
#include <qpdf/QPDF.hh>
#include <qpdf/QPDFWriter.hh>

#include <pybind11/pybind11.h>
#include <pybind11/stl.h>

#include "pikepdf.h"

/*
New type table

Encode Python type to C++ type
Decode C++ type to Python

Definite native:
Null - None
Boolean - bool
Integer - int
Real - Decimal

Uncertain:
String - str or bytes ?

Convertible:
Name - Name('/thing') 
Operator - Operator('Do')
Array - list / iterable
Dictionary - dict
Stream - Stream()


*/


std::string objecthandle_scalar_value(QPDFObjectHandle h, bool escaped=true)
{
    std::stringstream ss;
    switch (h.getTypeCode()) {
    case QPDFObject::object_type_e::ot_null:
        ss << "None";
        break;
    case QPDFObject::object_type_e::ot_boolean:
        ss << (h.getBoolValue() ? "True" : "False");
        break;
    case QPDFObject::object_type_e::ot_integer:
        ss << std::to_string(h.getIntValue());
        break;
    case QPDFObject::object_type_e::ot_real:
        ss << "Decimal('" + h.getRealValue() + "')";
        break;
    case QPDFObject::object_type_e::ot_name:
        ss << std::quoted(h.getName());
        break;
    case QPDFObject::object_type_e::ot_string:
        ss << std::quoted(h.getUTF8Value());
        break;
    case QPDFObject::object_type_e::ot_operator:
        ss << std::quoted(h.getOperatorValue());
        break;
    default:
        return "<not a scalar>";
    }
    return ss.str();
}

std::string objecthandle_pythonic_typename(QPDFObjectHandle h, std::string prefix = "pikepdf.Object.")
{
    std::string s;

    s += prefix;
    switch (h.getTypeCode()) {
    case QPDFObject::object_type_e::ot_null:
        s += "Null";
        break;
    case QPDFObject::object_type_e::ot_boolean:
        s += "Boolean";
        break;
    case QPDFObject::object_type_e::ot_integer:
        s += "Integer";
        break;
    case QPDFObject::object_type_e::ot_real:
        s += "Real";
        break;
    case QPDFObject::object_type_e::ot_name:
        s += "Name";
        break;
    case QPDFObject::object_type_e::ot_string:
        s += "String";
        break;
    case QPDFObject::object_type_e::ot_operator:
        s += "Operator";
        break;
    case QPDFObject::object_type_e::ot_inlineimage:
        s += "InlineImage";
        break;
    case QPDFObject::object_type_e::ot_array:
        s += "Array";
        break;
    case QPDFObject::object_type_e::ot_dictionary:
        s += "Dictionary";
        break;
    case QPDFObject::object_type_e::ot_stream:
        s += "Stream";
        break;
    default:
        s += "<Error>";
        break;
    }

    return s;
}


std::string objecthandle_repr_typename_and_value(QPDFObjectHandle h)
{
    return objecthandle_pythonic_typename(h) + \
                "(" + objecthandle_scalar_value(h) + ")";
}


std::string objecthandle_repr_inner(QPDFObjectHandle h, uint depth, std::set<QPDFObjGen>* visited, bool* pure_expr)
{
    if (depth > 1000) {
        throw std::runtime_error("Reached object recursion depth of 1000");
    }

    if (!h.isScalar()) {
        if (visited->count(h.getObjGen()) > 0) {
            *pure_expr = false;
            return "<circular reference>";
        }

        if (!(h.getObjGen() == QPDFObjGen(0, 0)))
            visited->insert(h.getObjGen());
    }

    std::ostringstream oss;

    switch (h.getTypeCode()) {
    case QPDFObject::object_type_e::ot_null:
    case QPDFObject::object_type_e::ot_boolean:
    case QPDFObject::object_type_e::ot_integer:
    case QPDFObject::object_type_e::ot_real:
    case QPDFObject::object_type_e::ot_name:
    case QPDFObject::object_type_e::ot_string:
        oss << objecthandle_scalar_value(h);
        break;
    case QPDFObject::object_type_e::ot_operator:
        oss << objecthandle_repr_typename_and_value(h);
        break;
    case QPDFObject::object_type_e::ot_inlineimage:
        oss << objecthandle_pythonic_typename(h);
        oss << "(";
        oss << "data=<...>";
        oss << ")";
        break;
    case QPDFObject::object_type_e::ot_array:
        oss << "[";
        {
            bool first = true;
            oss << " ";
            for (auto item: h.getArrayAsVector()) {
                if (!first) oss << ", ";
                first = false;
                oss << objecthandle_repr_inner(item, depth, visited, pure_expr);
            }
            oss << " ";
        }
        oss << "]";
        break;
    case QPDFObject::object_type_e::ot_dictionary:
        oss << "{"; // This will end the line
        {
            bool first = true;
            oss << "\n";
            for (auto item: h.getDictAsMap()) {
                if (!first) oss << ",\n";
                first = false;
                oss << std::string((depth + 1) * 2, ' '); // Indent each line
                if (item.first == "/Parent" && item.second.isPagesObject()) {
                    // Don't visit /Parent keys since that just puts every page on the repr() of a single page
                    oss << std::quoted(item.first) << ": <reference to /Pages>";
                } else {
                    oss << std::quoted(item.first) << ": " << objecthandle_repr_inner(item.second, depth + 1, visited, pure_expr);
                }
            }
            oss << "\n";
        }
        oss << std::string(depth * 2, ' '); // Restore previous indent level
        oss << "}";
        break;
    case QPDFObject::object_type_e::ot_stream:
        *pure_expr = false;
        oss << objecthandle_pythonic_typename(h);
        oss << "(";
        oss << "stream_dict=";
        oss << objecthandle_repr_inner(h.getDict(), depth + 1, visited, pure_expr);
        oss << ", ";
        oss << "data=<...>";
        oss << ")";
        break;
    default:
        oss << "???";
        break;
    }

    return oss.str();
}

std::string objecthandle_repr(QPDFObjectHandle h)
{
    if (h.isScalar()) {
        return objecthandle_repr_typename_and_value(h);
    }

    std::set<QPDFObjGen> visited;
    bool pure_expr = true;
    std::string inner = objecthandle_repr_inner(h, 0, &visited, &pure_expr);
    std::string output;

    if (h.isScalar() || h.isDictionary() || h.isArray()) {
        output = objecthandle_pythonic_typename(h) + "(" + inner + ")";
    } else {
        output = inner;
        pure_expr = false;
    }

    if (pure_expr) {
        // The output contains no external or parent objects so this object
        // can be output as a Python expression and rebuild with repr(output)
        return output;
    }
    // Output cannot be fully described in a Python expression
    return std::string("<") + output + ">";
}


std::vector<QPDFObjectHandle>
array_builder(py::iterable iter);

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
    // Ensure that when we return QPDFObjectHandle/pikepdf.Object to the Py
    // environment, that we can recover it
    try {
        auto as_qobj = handle.cast<QPDFObjectHandle>();
        return as_qobj;
    } catch (py::cast_error) {}

    try {
        auto as_int = handle.cast<long long>();
        return QPDFObjectHandle::newInteger(as_int);
    } catch (py::cast_error) {}

    try {
        auto as_double = handle.cast<double>();
        return QPDFObjectHandle::newReal(as_double);
    } catch (py::cast_error) {}

    // Special-case booleans since pybind11 coerces nonzero integers to boolean
    if (py::isinstance<py::bool_>(handle)) {
        bool as_bool = handle.cast<bool>();
        return QPDFObjectHandle::newBool(as_bool);
    }

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
        py::print(py::repr(obj));

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



class PyParserCallbacks : public QPDFObjectHandle::ParserCallbacks {
public:
    using QPDFObjectHandle::ParserCallbacks::ParserCallbacks;

    void handleObject(QPDFObjectHandle h) override {
        PYBIND11_OVERLOAD_PURE_NAME(
            void,
            QPDFObjectHandle::ParserCallbacks,
            "handle_object", /* Python name */
            handleObject, /* C++ name */
            h
        );
    }

    void handleEOF() override {
        PYBIND11_OVERLOAD_PURE_NAME(
            void,
            QPDFObjectHandle::ParserCallbacks,
            "handle_eof", /* Python name */
            handleEOF, /* C++ name; trailing comma needed for macro */
        );
    }
};


size_t list_range_check(QPDFObjectHandle& h, int index)
{
    if (!h.isArray())
        throw py::value_error("object is not an array");
    if (index < 0)
        index += h.getArrayNItems(); // Support negative indexing
    if (!(0 <= index && index < h.getArrayNItems()))
        throw py::index_error("index out of range");
    return (size_t)index;   
}


void init_object(py::module& m)
{
    py::enum_<QPDFObject::object_type_e>(m, "ObjectType")
        .value("ot_uninitialized", QPDFObject::object_type_e::ot_uninitialized)
        .value("ot_reserved", QPDFObject::object_type_e::ot_reserved)
        .value("ot_null", QPDFObject::object_type_e::ot_null)
        .value("ot_boolean", QPDFObject::object_type_e::ot_boolean)
        .value("ot_integer", QPDFObject::object_type_e::ot_integer)
        .value("ot_real", QPDFObject::object_type_e::ot_real)
        .value("ot_string", QPDFObject::object_type_e::ot_string)
        .value("ot_name", QPDFObject::object_type_e::ot_name)
        .value("ot_array", QPDFObject::object_type_e::ot_array)
        .value("ot_dictionary", QPDFObject::object_type_e::ot_dictionary)
        .value("ot_stream", QPDFObject::object_type_e::ot_stream)
        .value("ot_operator", QPDFObject::object_type_e::ot_operator)
        .value("ot_inlineimage", QPDFObject::object_type_e::ot_inlineimage);

/* Object API

qpdf.Object.Typename()  <-- class-ish name, static method in reality
tries to coerce input to Pdf object of typename, or fails

qpdf.Object.new() <--- tries to create a Pdf object from its input with when
possible without ambiguity

Boolean <- bool
Integer <- int
Real <- decimal.Decimal, float
String <- str, bytes
    this will need help from Pdf doc encoding

Array <- list, tuple
Dictionary <- dict, Mapping

Stream <- present as qpdf.Object.Stream({dictionary}, stream=<...>)

when does Dictionary.__setitem__ coerce its value to a Pdf object? on input
or serialization
    probably on input, fail first

that means __setitem__ needs to recursively coerce

should be able to assign python objects and have them mapped to appropriate
objects - or




// qpdf.Object.Boolean(True) <-- class-ish name, static method in reality
// instead of
// qpdf.Object.new(True)  <--- when possible without ambiguity
// strings:
// qpdf.Object.Name("")
// qpdf.Object.new("/Name"?)

// Then repr becomes...
// or should each object be type-decorated?
qpdf.Object.Dictionary({
    "/Type": "/Page",
    "/MediaBox": [],
    "/Contents": <qpdf.Object.Stream>,
})


*/

    py::class_<Buffer, PointerHolder<Buffer>>(m, "Buffer", py::buffer_protocol())
        .def_buffer([](Buffer &b) -> py::buffer_info {
            return py::buffer_info(
                b.getBuffer(),
                sizeof(unsigned char),
                py::format_descriptor<unsigned char>::format(),
                1,
                { b.getSize() },
                { sizeof(unsigned char) }
            );
        });

    py::class_<QPDFObjectHandle> objecthandle(m, "Object");

    objecthandle
        .def_static("Boolean",
            [](bool b) {
                return QPDFObjectHandle::newBool(b);
            },
            "Construct a PDF Boolean object"
        )
        .def_static("Integer",
            [](int n) {
                return QPDFObjectHandle::newInteger(n);
            },
            "Construct a PDF Integer object"
        )
        .def_static("Real",
            [](py::object obj) {
                py::object Decimal = py::module::import("decimal").attr("Decimal");
                if (py::isinstance<py::float_>(obj) || py::isinstance<py::int_>(obj)) {
                    auto val = obj.cast<double>();
                    if (isinf(val) || isnan(val))
                        throw py::value_error("NaN and infinity cannot be represented as PDF objects");
                    return QPDFObjectHandle::newReal(val, 0);
                }
                py::print(obj);
                py::print(py::repr(obj));                
                if (!py::isinstance(obj, Decimal))
                    throw py::type_error("Can't convert arbitrary Python object to PDF Real");
                py::bool_ is_finite = obj.attr("is_finite")();
                if (!is_finite)
                    throw py::value_error("NaN and infinity cannot be represented as PDF objects");
                return QPDFObjectHandle::newReal(py::str(obj));
            },
            "Construct a PDF Real value, that is, a decimal number"
        )
        .def_static("Name",
            [](const std::string& s) {
                if (s.at(0) != '/')
                    throw py::value_error("Name objects must begin with '/'");
                if (s.length() < 2)
                    throw py::value_error("Name must be at least one character long");
                return QPDFObjectHandle::newName(s);
            },
            "Create a Name from a string. Must begin with '/'. All other characters except null are valid."
        )
        .def_static("String",
            [](const std::string& s) {
                return QPDFObjectHandle::newString(s);
            },
            "Construct a PDF String object."
        )
        .def_static("Array",
            [](py::iterable iterable) {
                return QPDFObjectHandle::newArray(array_builder(iterable));
            },
            "Construct a PDF Array object from an iterable of PDF objects or types that can be coerced to PDF objects."
        )
        .def_static("Dictionary",
            [](py::dict dict) {
                return QPDFObjectHandle::newDictionary(dict_builder(dict));
            },
            "Construct a PDF Dictionary from a mapping of PDF objects or Python types that can be coerced to PDF objects."
        )
        .def_static("Stream",
            [](QPDF* owner, py::bytes data) {
                std::string s = data;
                return QPDFObjectHandle::newStream(owner, data); // This makes a copy of the data
            },
            "Construct a PDF Stream object from binary data",
            py::keep_alive<0, 1>() // returned object references the owner
        )
        .def_static("Stream",
            [](QPDF* owner, py::iterable content_stream) {
                std::stringstream data;

                for (auto handle_command : content_stream) {
                    py::tuple command = py::reinterpret_borrow<py::tuple>(handle_command);

                    if (command.size() != 2)
                        throw py::value_error("Each item in stream data must be a tuple(operands, operator)");

                    py::object operands = command[0];
                    py::object operator_ = command[1];
                    for (auto operand : operands) {
                        QPDFObjectHandle h = objecthandle_encode(operand);
                        data << h.unparse();
                        data << " ";
                    }
                    data << objecthandle_encode(operator_).unparse();
                    data << "\n";
                }
                return QPDFObjectHandle::newStream(owner, data.str());
            },
            "Construct a PDF Stream object from a list of operand-operator tuples [((operands,), operator)]",
            py::keep_alive<0, 1>() // returned object references the owner   
        )
        .def_static("Operator",
            [](const std::string& op) {
                return QPDFObjectHandle::newOperator(op);
            },
            "Construct a PDF Operator object for use in content streams"
        )
        .def_static("Null", &QPDFObjectHandle::newNull,
            "Construct a PDF Null object"
        )
        .def_static("new",
            [](bool b) {
                return QPDFObjectHandle::newBool(b);
            }
        )
        .def_static("new",
            [](int n) {
                return QPDFObjectHandle::newInteger(n);
            }
        )
        .def_static("new",
            [](double f) {
                return QPDFObjectHandle::newReal(f, 0); // default to six decimals
            }
        )
        .def_static("new",
            [](std::string s) {
                return QPDFObjectHandle::newString(s); // TO DO: warn about /Name
            }
        )
        .def_static("new",
            [](py::none none) {
                return QPDFObjectHandle::newNull();
            }
        )
        .def_property_readonly("type_code", &QPDFObjectHandle::getTypeCode)
        .def_property_readonly("type_name", &QPDFObjectHandle::getTypeName)
        .def_property_readonly("owner", &QPDFObjectHandle::getOwningQPDF,
            "Return the QPDF object that owns an indirect object.  Returns None for a direct object."
        )
        .def("__repr__", &objecthandle_repr)
        .def("__hash__",
            [](QPDFObjectHandle &self) {
                Py_ssize_t val = 42; // Seed
                std::string hashstr = "";

                // Mix in our type code
                val = val * 101 + (Py_ssize_t)self.getTypeCode();

                switch (self.getTypeCode()) {
                    case QPDFObject::object_type_e::ot_null:
                        break;
                    case QPDFObject::object_type_e::ot_boolean:
                        val = val * 101 + (int)self.getBoolValue();
                        break;
                    case QPDFObject::object_type_e::ot_integer:
                        val = val * 101 + self.getIntValue();
                        break;
                    case QPDFObject::object_type_e::ot_real:
                        hashstr = self.getRealValue();  // Is a string
                        break;
                    case QPDFObject::object_type_e::ot_string:
                        hashstr = self.getStringValue();
                        break;
                    case QPDFObject::object_type_e::ot_name:
                        hashstr = self.getName();
                         break;
                    case QPDFObject::object_type_e::ot_operator:
                        hashstr = self.getOperatorValue();
                        break;
                    case QPDFObject::object_type_e::ot_array:
                    case QPDFObject::object_type_e::ot_dictionary:
                    case QPDFObject::object_type_e::ot_stream:
                    case QPDFObject::object_type_e::ot_inlineimage:
                        throw py::value_error("Can't hash mutable object");
                        break;
                    default:
                        break;
                }

                for (unsigned long n = 0; n < hashstr.length(); n++)
                    val = val * 101 + hashstr[n];

                return val;
            }
        )
        .def("__eq__",
            [](QPDFObjectHandle &self, QPDFObjectHandle &other) {
                /* Uninitialized objects are never equal */
                if (!self.isInitialized() || !other.isInitialized())
                    return false;

                /* If 'self' is a numeric type, coerce both to Decimal objects
                   and compare them as such */
                if (self.getTypeCode() == QPDFObject::object_type_e::ot_integer ||
                    self.getTypeCode() == QPDFObject::object_type_e::ot_real) {
                    try {
                        auto a = decimal_from_pdfobject(self);
                        auto b = decimal_from_pdfobject(other);
                        py::object pyresult = a.attr("__eq__")(b);
                        bool result = pyresult.cast<bool>();
                        return result;
                    } catch (py::type_error) {
                        return false;
                    }
                }

                /* Apart from numeric types, disimilar types are never equal */
                if (self.getTypeCode() != other.getTypeCode())
                    return false;

                switch (self.getTypeCode()) {
                    case QPDFObject::object_type_e::ot_null:
                        return true; // Both must be null
                    case QPDFObject::object_type_e::ot_boolean:
                        return self.getBoolValue() == other.getBoolValue();
                    case QPDFObject::object_type_e::ot_name:
                        return self.getName() == other.getName();
                    case QPDFObject::object_type_e::ot_operator:
                        return self.getOperatorValue() == other.getOperatorValue();
                    case QPDFObject::object_type_e::ot_string:
                        return self.getStringValue() == other.getStringValue();
                    default:
                        // Objects with the same obj-gen are equal if they have nonzero
                        // objid and belong to the same PDF
                        if (self.getObjectID() != 0 && self.getOwningQPDF() == other.getOwningQPDF())
                            return self.getObjGen() == other.getObjGen();
                        break;
                }
                return false;
            }
        )
        .def("__eq__",
            [](QPDFObjectHandle &self, long long other) {
                /* Objects of different numeric types are expected to compare equal */
                if (!self.isInitialized())
                    return false;
                if (self.getTypeCode() == QPDFObject::object_type_e::ot_integer)
                    return self.getIntValue() == other;
                return false;
            }
        )
        .def("__lt__",
            [](QPDFObjectHandle &self, QPDFObjectHandle &other) {
                if (!self.isInitialized() || !other.isInitialized())
                    throw py::type_error("comparison involving an uninitialized object");
                if (self.getTypeCode() == QPDFObject::object_type_e::ot_integer ||
                    self.getTypeCode() == QPDFObject::object_type_e::ot_real) {
                    try {
                        auto a = decimal_from_pdfobject(self);
                        auto b = decimal_from_pdfobject(other);
                        py::object pyresult = a.attr("__lt__")(b);
                        bool result = pyresult.cast<bool>();
                        return result;
                    } catch (py::type_error) {
                        throw py::type_error("comparison undefined");
                    }
                }
                throw py::type_error("comparison undefined");
            }
        )
        .def("__lt__",
            [](QPDFObjectHandle &self, long long other) {
                if (!self.isInitialized())
                    throw py::type_error("comparison involving an uninitialized object");
                if (self.getTypeCode() == QPDFObject::object_type_e::ot_integer ||
                    self.getTypeCode() == QPDFObject::object_type_e::ot_real) {
                    try {
                        auto a = decimal_from_pdfobject(self);
                        auto b = py::int_(other);
                        py::object pyresult = a.attr("__lt__")(b);
                        bool result = pyresult.cast<bool>();
                        return result;
                    } catch (py::type_error) {
                        throw py::type_error("comparison undefined");
                    }
                }
                throw py::type_error("comparison undefined");
            }
        )
        .def("__len__",
            [](QPDFObjectHandle &h) {
                if (h.isDictionary())
                    return (Py_ssize_t)h.getDictAsMap().size(); // getKeys constructs a new object, so this is better
                else if (h.isArray())
                    return (Py_ssize_t)h.getArrayNItems();
                throw py::value_error("length not defined for object");
            }
        )
        .def("__getitem__",
            [](QPDFObjectHandle &h, std::string const& key) {
                if (!h.isDictionary())
                    throw py::value_error("object is not a dictionary");
                if (!h.hasKey(key))
                    throw py::key_error(key);
                return h.getKey(key);
            }
        )
        .def("__setitem__",
            [](QPDFObjectHandle &h, std::string const& key, QPDFObjectHandle &value) {
                if (!h.isDictionary() && !h.isStream())
                    throw py::value_error("object is not a dictionary or a stream");

                // For streams, the actual dictionary is attached to stream object
                QPDFObjectHandle dict = h.isStream() ? h.getDict() : h;

                // A stream dictionary has no owner, so use the stream object in this comparison
                if (value.getOwningQPDF() && value.getOwningQPDF() != h.getOwningQPDF())
                    throw py::value_error("cannot assign indirect object from a foreign PDF - use copyForeignObject");

                // if (value.isScalar() || value.isStream()) {
                //     dict.replaceKey(key, value);
                //     return;
                // }

                // try {
                //     auto copy = value.shallowCopy();
                //     copy.makeDirect();
                // } catch (std::exception &e) {
                //     throw py::value_error(e.what());
                // }
                dict.replaceKey(key, value);
            },
            "assign dictionary key to new object",
            py::keep_alive<1, 3>()
        )
        .def("__setitem__",
            [](QPDFObjectHandle &h, std::string const& key, py::object &pyvalue) {
                if (!h.isDictionary() && !h.isStream())
                    throw py::value_error("object is not a dictionary or a stream");

                // For streams, the actual dictionary is attached to stream object
                QPDFObjectHandle dict = h.isStream() ? h.getDict() : h;

                auto value = objecthandle_encode(pyvalue);
                // A stream dictionary has no owner, so use the stream object in this comparison
                dict.replaceKey(key, value);
            }
        )
        .def("__delitem__",
            [](QPDFObjectHandle &h, std::string const& key) {
                if (!h.isDictionary())
                    throw py::value_error("object is not a dictionary");

                if (!h.hasKey(key))
                    throw py::key_error(key);

                h.removeKey(key);
            },
            "delete a dictionary key"
        )
        .def("__getattr__",
            [](QPDFObjectHandle &h, std::string const& name) {
                if (!h.isDictionary() && !h.isStream())
                    throw py::attr_error("object is not a dictionary or a stream");
                QPDFObjectHandle dict = h.isStream() ? h.getDict() : h;
                std::string key = "/" + name;
                if (!dict.hasKey(key))
                    throw py::attr_error(key);
                return dict.getKey(key);
            },
            "attribute lookup name"
        )
        .def("__setattr__",
            [](QPDFObjectHandle &h, std::string const& name, py::object &pyvalue) {
                if (!h.isDictionary() && !h.isStream())
                    throw py::attr_error("object is not a dictionary or a stream");
                QPDFObjectHandle dict = h.isStream() ? h.getDict() : h;
                std::string key = "/" + name;
                auto value = objecthandle_encode(pyvalue);
                dict.replaceKey(key, value);
            },
            "attribute access"
        )
        .def("get",
            [](QPDFObjectHandle &h, std::string const& key, py::object default_) {
                if (!h.isDictionary())
                    throw py::value_error("object is not a dictionary");
                if (!h.hasKey(key))
                    return default_;
                return py::cast(h.getKey(key));
            },
            "for dictionary objects, behave as dict.get(key, default=None)",
            py::arg("key"),
            py::arg("default_") = py::none()
        )
        .def("keys", &QPDFObjectHandle::getKeys)
        .def("__contains__",
            [](QPDFObjectHandle &h, std::string const& key) {
                if (h.isDictionary()) {
                    return h.hasKey(key);
                }
                throw py::value_error("__contains__ not defined for object type");
            }
        )
        .def("as_list", &QPDFObjectHandle::getArrayAsVector)
        .def("as_dict", &QPDFObjectHandle::getDictAsMap)
        .def("as_int", &QPDFObjectHandle::getIntValue)
        .def("__int__", &QPDFObjectHandle::getIntValue)
        .def("as_bool", &QPDFObjectHandle::getBoolValue)
        .def("decode", objecthandle_decode, "convert to nearest Python object")
        .def("__str__", &QPDFObjectHandle::getUTF8Value)
        .def("__bytes__", &QPDFObjectHandle::getStringValue)
        .def("__getitem__",
            [](QPDFObjectHandle &h, int index) {
                size_t u_index = list_range_check(h, index);
                return h.getArrayItem(u_index);
            }
        )
        .def("__setitem__",
            [](QPDFObjectHandle &h, int index, QPDFObjectHandle &value) {
                size_t u_index = list_range_check(h, index);
                h.setArrayItem(u_index, value);
            }
        )
        .def("__setitem__",
            [](QPDFObjectHandle &h, int index, py::object &pyvalue) {
                size_t u_index = list_range_check(h, index);
                auto value = objecthandle_encode(pyvalue);
                h.setArrayItem(u_index, value);
            }
        )
        .def("__delitem__",
            [](QPDFObjectHandle &h, int index) {
                size_t u_index = list_range_check(h, index);
                h.eraseItem(u_index);                
            }
        )
        .def_property("stream_dict", 
            &QPDFObjectHandle::getDict, &QPDFObjectHandle::replaceDict,
            py::return_value_policy::copy // ObjectHandle is wrapper around a shared pointer, so should be copied
        )
        .def("get_stream_buffer",
            [](QPDFObjectHandle &h) {
                PointerHolder<Buffer> phbuf = h.getStreamData();
                return phbuf;
            },
            "Return a buffer protocol buffer describing the decoded stream"
        )
        .def("get_raw_stream_buffer",
            [](QPDFObjectHandle &h) {
                PointerHolder<Buffer> phbuf = h.getRawStreamData();
                return phbuf;
            },
            "Return a buffer protocol buffer describing the raw, encoded stream"
        )
        .def("read_stream",
            [](QPDFObjectHandle &h) {
                PointerHolder<Buffer> buf = h.getStreamData();
                // py::bytes will make a copy of the buffer, so releasing is fine
                return py::bytes((const char*)buf->getBuffer(), buf->getSize());
            },
            py::return_value_policy::take_ownership,
            "Decode and read the content stream associated with this object"
        )
        .def("read_raw_stream",
            [](QPDFObjectHandle &h) {
                PointerHolder<Buffer> buf = h.getRawStreamData();
                // py::bytes will make a copy of the buffer, so releasing is fine
                return py::bytes((const char*)buf->getBuffer(), buf->getSize());
            },
            py::return_value_policy::take_ownership,
            "Read the content stream associated with this object without decoding"
        )
        .def_property_readonly("_objgen",
            [](QPDFObjectHandle &h) {
                auto objgen = h.getObjGen();
                return std::pair<int, int>(objgen.getObj(), objgen.getGen());
            }
        )
        .def_static("parse", 
            [](std::string const& stream, std::string const& description) {
                return QPDFObjectHandle::parse(stream, description);
            },
            "Parse text PostScript into PDF objects.",
            py::arg("stream"),
            py::arg("description") = ""
        )
        .def_static("parse",
            [](py::bytes &stream, std::string const& description) {
                std::string s = stream;
                return QPDFObjectHandle::parse(stream, description);
            },
            "Parse binary PostScript into PDF objects.",
            py::arg("stream"),
            py::arg("description") = ""
        )
        .def_static("parse_stream", 
            &QPDFObjectHandle::parseContentStream,
            "Helper for parsing PDF content stream. Use ``pikepdf.parse_content_stream`` instead.")
        .def("unparse", &QPDFObjectHandle::unparse,
            "Convert PDF objects into PostScript, without resolving indirect objects.")
        .def("unparse_resolved", &QPDFObjectHandle::unparseResolved,
            "Convert PDF objects into PostScript, and resolve referenced objects when possible.");

    py::class_<QPDFObjectHandle::ParserCallbacks, PyParserCallbacks> parsercallbacks(m, "StreamParser");
    parsercallbacks
        .def(py::init<>())
        .def("handle_object", &QPDFObjectHandle::ParserCallbacks::handleObject)
        .def("handle_eof", &QPDFObjectHandle::ParserCallbacks::handleEOF);

    m.def("_encode", &objecthandle_encode);
    m.def("_decode", &objecthandle_decode);

} // init_object
