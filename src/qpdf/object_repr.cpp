/*
 * This Source Code Form is subject to the terms of the Mozilla Public
 * License, v. 2.0. If a copy of the MPL was not distributed with this
 * file, You can obtain one at http://mozilla.org/MPL/2.0/.
 *
 * Copyright (C) 2017, James R. Barlow (https://github.com/jbarlow83/)
 */

/* 
 * Implement repr() for QPDFObjectHandle
 * 
 * Since qpdf largely ignores const, it is not possible to use const here,
 * even though repr() is const throughout.
 * 
 * References are used for functions that are just passing handles around.
 * objecthandle_repr_inner cannot cannot use references because it calls itself.
 */

#include <sstream>
#include <iostream>
#include <iomanip>

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

#include "pikepdf.h"


std::string objecthandle_scalar_value(QPDFObjectHandle& h, bool escaped)
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

std::string objecthandle_pythonic_typename(QPDFObjectHandle& h, std::string prefix)
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
        if (h.hasKey("/Type")) {
            s += std::string("Dictionary(type_=\"") + h.getKey("/Type").getName() + "\")"; 
        } else {
            s += "Dictionary";
        }
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


std::string objecthandle_repr_typename_and_value(QPDFObjectHandle& h)
{
    return objecthandle_pythonic_typename(h) + \
                "(" + objecthandle_scalar_value(h) + ")";
}


static
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

std::string objecthandle_repr(QPDFObjectHandle& h)
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