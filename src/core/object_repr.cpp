// SPDX-FileCopyrightText: 2022 James R. Barlow
// SPDX-License-Identifier: MPL-2.0

/*
 * Implement repr() for QPDFObjectHandle
 *
 * Since qpdf largely ignores const, it is not possible to use const here,
 * even though repr() is const throughout.
 *
 * References are used for functions that are just passing handles around.
 * objecthandle_repr_inner cannot cannot use references because it calls itself.
 */

#include "pikepdf.h"

#include <string>

#include <qpdf/Constants.h>
#include <qpdf/DLL.h>
#include <qpdf/QPDF.hh>
#include <qpdf/QPDFExc.hh>
#include <qpdf/QPDFObjGen.hh>
#include <qpdf/QPDFObjectHandle.hh>
#include <qpdf/QPDFWriter.hh>
#include <qpdf/QUtil.hh>
#include <qpdf/Types.h>

// Append s to out the way `stream << std::quoted(s)` would: wrap it in double
// quotes and backslash-escape any embedded quote or backslash. Like std::quoted,
// this leaves all other bytes alone, including non-printable ones.
static void append_quoted(std::string &out, std::string const &s)
{
    out += '"';
    for (char c : s) {
        if (c == '"' || c == '\\')
            out += '\\';
        out += c;
    }
    out += '"';
}

std::string objecthandle_scalar_value(QPDFObjectHandle h)
{
    std::string out;
    switch (h.getTypeCode()) {
    case qpdf_object_type_e::ot_null:
        return "None";
    case qpdf_object_type_e::ot_boolean:
        return h.getBoolValue() ? "True" : "False";
    case qpdf_object_type_e::ot_integer:
        return std::to_string(h.getIntValue());
    case qpdf_object_type_e::ot_real:
        if (get_explicit_conversion_mode()) {
            // In explicit mode, show as quoted string since pikepdf.Real wraps it
            return "'" + h.getRealValue() + "'";
        }
        // In implicit mode, show as Decimal for backward compatibility
        return "Decimal('" + h.getRealValue() + "')";
    case qpdf_object_type_e::ot_name:
        append_quoted(out, h.getName());
        return out;
    case qpdf_object_type_e::ot_string:
        append_quoted(out, h.getUTF8Value());
        return out;
    case qpdf_object_type_e::ot_operator:
        append_quoted(out, h.getOperatorValue());
        return out;
    // LCOV_EXCL_START
    default:
        throw std::logic_error("object_handle_scalar value called for non-scalar");
        // LCOV_EXCL_STOP
    }
}

std::string objecthandle_pythonic_typename(QPDFObjectHandle h)
{
    switch (h.getTypeCode()) {
    case qpdf_object_type_e::ot_name:
        return "pikepdf.Name";
    case qpdf_object_type_e::ot_string:
        return "pikepdf.String";
    case qpdf_object_type_e::ot_operator:
        return "pikepdf.Operator";
    // LCOV_EXCL_START
    case qpdf_object_type_e::ot_inlineimage:
        // Objects of this time are not directly returned.
        return "pikepdf.InlineImage";
    // LCOV_EXCL_STOP
    case qpdf_object_type_e::ot_array:
        return "pikepdf.Array";
    case qpdf_object_type_e::ot_dictionary:
        if (h.hasKey("/Type")) {
            return "pikepdf.Dictionary(Type=\"" + h.getKey("/Type").getName() + "\")";
        }
        return "pikepdf.Dictionary";
    case qpdf_object_type_e::ot_stream:
        return "pikepdf.Stream";
    case qpdf_object_type_e::ot_null:
        return ""; // None is always represented as None
    case qpdf_object_type_e::ot_boolean:
        return get_explicit_conversion_mode() ? "pikepdf.Boolean" : "";
    case qpdf_object_type_e::ot_integer:
        return get_explicit_conversion_mode() ? "pikepdf.Integer" : "";
    case qpdf_object_type_e::ot_real:
        return get_explicit_conversion_mode() ? "pikepdf.Real" : "";

    // LCOV_EXCL_START
    default:
        throw std::logic_error(
            std::string("Unexpected pikepdf object type name: ") + h.getTypeName());
        // LCOV_EXCL_STOP
    }
}

std::string objecthandle_repr_typename_and_value(QPDFObjectHandle h)
{
    auto pythonic_typename = objecthandle_pythonic_typename(h);
    if (pythonic_typename.empty()) {
        return objecthandle_scalar_value(h);
    }
    return pythonic_typename + "(" + objecthandle_scalar_value(h) + ")";
}

std::string preview_stream_data(QPDFObjectHandle h, uint recursion_depth)
{
    // If we are looking at the top level object, decode a stream of up to
    // MAX_BUFFER_TO_EXPAND and display up to MAX_PEEK_BYTES.

    const uint MAX_PEEK_RECURSION_DEPTH = 1;
    const size_t MAX_PEEK_BYTES = 20;
    const size_t MAX_BUFFER_TO_EXPAND = 10000;

    std::string s;

    unsigned long long stream_length;
    if (recursion_depth > MAX_PEEK_RECURSION_DEPTH ||
        !h.getDict().getKeyIfDict("/Length").getValueAsUInt(stream_length) ||
        stream_length > MAX_BUFFER_TO_EXPAND) {
        return "<...>";
    }

    std::shared_ptr<Buffer> buffer;
    try {
        buffer = h.getStreamData();
    } catch (QPDFExc &) {
        return "<...>";
    }
    auto data = buffer->getBuffer();

    // Use py::bytes to format output like Python does
    py::bytes pydata(reinterpret_cast<const char *>(data),
        std::min(MAX_PEEK_BYTES, buffer->getSize()));
    s = py::cast<std::string>(py::repr(pydata));
    if (buffer->getSize() > MAX_PEEK_BYTES) {
        s += "...";
    }
    return s;
}

static void objecthandle_repr_inner(std::string &out, // accumulates the result
    QPDFObjectHandle h,
    uint recursion_depth,
    uint indent_depth,
    uint &object_count,            // shared among recursive calls
    std::set<QPDFObjGen> &visited, // shared among recursive calls
    bool &pure_expr)               // shared among recursive calls
{
    const uint MAX_OBJECT_COUNT = 40;

    StackGuard sg(" objecthandle_repr_inner");

    if (!h.isScalar()) {
        if (visited.count(h.getObjGen()) > 0) {
            pure_expr = false;
            out += "<.get_object(" + h.getObjGen().unparse() + ")>";
            return;
        }

        if (!(h.getObjGen() == QPDFObjGen(0, 0)))
            visited.insert(h.getObjGen());
    }
    if (h.isPageObject() && recursion_depth >= 1 && h.isIndirect()) {
        out += "<Pdf.pages.from_objgen(" + h.getObjGen().unparse() + ")>";
        return;
    }
    object_count++;
    if (object_count > MAX_OBJECT_COUNT && recursion_depth > 1) {
        // If we've printed too many objects, start printing <...> instead
        // for objects that aren't the top level object.
        pure_expr = false;
        out += "<...>";
        return;
    }

    switch (h.getTypeCode()) {
    case qpdf_object_type_e::ot_null:
    case qpdf_object_type_e::ot_boolean:
    case qpdf_object_type_e::ot_integer:
    case qpdf_object_type_e::ot_real:
    case qpdf_object_type_e::ot_name:
    case qpdf_object_type_e::ot_string:
        out += objecthandle_scalar_value(h);
        break;
    case qpdf_object_type_e::ot_operator:
        out += objecthandle_repr_typename_and_value(h);
        break;
    case qpdf_object_type_e::ot_inlineimage:
        // LCOV_EXCL_START
        // Inline image objects are automatically promoted to higher level objects
        // in parse_content_stream, so objects of this type should not be returned
        // directly.
        out += objecthandle_pythonic_typename(h) + "(data=<...>)";
        break;
    // LCOV_EXCL_STOP
    case qpdf_object_type_e::ot_array: {
        out += "[ ";
        bool first_item = true;
        for (auto &item : h.aitems()) {
            if (!first_item)
                out += ", ";
            first_item = false;
            // We don't increase indent_depth when recursing into arrays,
            // because it doesn't look right. Always increase recursion_depth.
            objecthandle_repr_inner(out,
                item,
                recursion_depth + 1,
                indent_depth,
                object_count,
                visited,
                pure_expr);
        }
        out += " ]";
        break;
    }
    case qpdf_object_type_e::ot_dictionary: {
        out += "{\n"; // This will end the line
        bool first_item = true;
        for (auto &[key, obj] : h.ditems()) {
            if (!first_item)
                out += ",\n";
            first_item = false;
            out.append((indent_depth + 1) * 2, ' '); // Indent each line
            append_quoted(out, key);
            if (key == "/Parent" && obj.isPagesObject()) {
                // Don't visit /Parent keys since that just puts every page on the
                // repr() of a single page
                out += ": <reference to /Pages>";
            } else {
                out += ": ";
                objecthandle_repr_inner(out,
                    obj,
                    recursion_depth + 1,
                    indent_depth + 1,
                    object_count,
                    visited,
                    pure_expr);
            }
        }
        out += "\n";
        out.append(indent_depth * 2, ' '); // Restore previous indent level
        out += "}";
        break;
    }
    case qpdf_object_type_e::ot_stream:
        pure_expr = false;
        out += objecthandle_pythonic_typename(h) +
               "(owner=<...>, data=" + preview_stream_data(h, recursion_depth) + ", ";
        objecthandle_repr_inner(out,
            h.getDict(),
            recursion_depth + 1,
            indent_depth, // Don't indent here to align dict with stream
            object_count,
            visited,
            pure_expr);
        out += ")";
        break;
    // LCOV_EXCL_START
    default:
        out += "Unexpected qpdf object type value: " +
               std::to_string(static_cast<int>(h.getTypeCode()));
        break;
        // LCOV_EXCL_STOP
    }
}

std::string objecthandle_repr(QPDFObjectHandle h)
{
    // While we would normally expect a repr function to be a constant,
    // accessing the repr of an object can trigger dereferencing of indirect objects
    // and loading data from the source PDF. Thus, it is not constant.

    if (h.isDestroyed()) {
        return std::string("<Object was inside a closed or deleted pikepdf.Pdf>");
    }
    if (h.isScalar() || h.isOperator()) {
        // qpdf does not consider Operator a scalar but it is as far we
        // are concerned here
        return objecthandle_repr_typename_and_value(h);
    }

    std::set<QPDFObjGen> visited;
    bool pure_expr = true;
    uint object_count = 0;
    std::string inner;
    objecthandle_repr_inner(inner, h, 0, 0, object_count, visited, pure_expr);
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
