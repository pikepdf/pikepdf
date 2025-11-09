// SPDX-FileCopyrightText: 2025 James R. Barlow
// SPDX-License-Identifier: MPL-2.0

#include <string>

#include <qpdf/QPDFObjectHandle.hh>

#include "pikepdf.h"

inline bool typecode_is_bool(qpdf_object_type_e typecode)
{
    return typecode == qpdf_object_type_e::ot_boolean;
}

inline bool typecode_is_int(qpdf_object_type_e typecode)
{
    return typecode == qpdf_object_type_e::ot_integer;
}

inline bool typecode_is_numeric(qpdf_object_type_e typecode)
{
    return typecode == qpdf_object_type_e::ot_integer ||
           typecode == qpdf_object_type_e::ot_real ||
           typecode == qpdf_object_type_e::ot_boolean;
}

static std::pair<std::string, std::string> make_unparsed_pair(
    QPDFObjectHandle &self, QPDFObjectHandle &other)
{
    return std::make_pair(self.unparseBinary(), other.unparseBinary());
}

static bool objecthandle_equal_inner(QPDFObjectHandle self,
    QPDFObjectHandle other,
    std::set<std::pair<std::string, std::string>> &visited)
{
    StackGuard sg(" objecthandle_equal");

    // Uninitialized objects are never equal
    if (!self.isInitialized() || !other.isInitialized())
        return false; // LCOV_EXCL_LINE

    // If two objects point to the same underlying object, they are equal (in fact,
    // they are identical; they reference the same underlying QPDFObject, even if the
    // handles are different). This lets us compare deeply nested and cyclic
    // structures without recursing into them.
    if (self.isSameObjectAs(other)) {
        return true;
    }

    auto self_typecode = self.getTypeCode();
    auto other_typecode = other.getTypeCode();

    if (typecode_is_bool(self_typecode) && typecode_is_bool(other_typecode)) {
        return self.getBoolValue() == other.getBoolValue();
    } else if (typecode_is_int(self_typecode) && typecode_is_int(other_typecode)) {
        return self.getIntValue() == other.getIntValue();
    } else if (typecode_is_numeric(self_typecode) &&
               typecode_is_numeric(other_typecode)) {
        // If 'self' and 'other' are different numeric types, convert both to
        // Decimal objects and compare them as such.
        auto a = decimal_from_pdfobject(self);
        auto b = decimal_from_pdfobject(other);
        py::object pyresult = a.attr("__eq__")(b);
        bool result = pyresult.cast<bool>();
        return result;
    }

    // Apart from numeric types, dissimilar types are never equal
    if (self_typecode != other_typecode)
        return false;

    switch (self_typecode) {
    case qpdf_object_type_e::ot_null:
        return true; // Both must be null
    case qpdf_object_type_e::ot_name:
        return self.getName() == other.getName();
    case qpdf_object_type_e::ot_operator:
        return self.getOperatorValue() == other.getOperatorValue();
    case qpdf_object_type_e::ot_string: {
        // We don't know what encoding the string is in
        // This ensures UTF-16 coded ASCII strings will compare equal to
        // UTF-8/ASCII coded.
        return self.getStringValue() == other.getStringValue() ||
               self.getUTF8Value() == other.getUTF8Value();
    }
    case qpdf_object_type_e::ot_array: {
        if (self.getArrayNItems() != other.getArrayNItems())
            return false;
        auto self_aitems = self.aitems();
        auto other_aitems = other.aitems();
        auto iter_self = self_aitems.begin();
        auto iter_other = other_aitems.begin();
        auto unparsed_pair = make_unparsed_pair(self, other);
        // If previously visited, we have a cycle
        if (visited.count(unparsed_pair) > 0)
            return true;
        // We are going to recurse, so record the current pair as visited
        visited.insert(unparsed_pair);
        for (; iter_self != self_aitems.end(); ++iter_self, ++iter_other) {
            if (!objecthandle_equal_inner(*iter_self, *iter_other, visited)) {
                return false;
            }
        }
        return true;
    }
    case qpdf_object_type_e::ot_dictionary: {
        if (self.getKeys() != other.getKeys())
            return false;
        auto unparsed_pair = make_unparsed_pair(self, other);
        if (visited.count(unparsed_pair) > 0)
            return true;
        // Potential recursive comparison
        visited.insert(unparsed_pair);
        for (auto &key : self.getKeys()) {
            auto value = self.getKey(key);
            auto other_value = other.getKey(key);
            if (other_value.isNull())
                return false;
            if (!objecthandle_equal_inner(value, other_value, visited))
                return false;
        }
        return true;
    }
    case qpdf_object_type_e::ot_stream: {
        // Recurse into this function to check if our dictionaries are equal
        if (!objecthandle_equal_inner(self.getDict(), other.getDict(), visited))
            return false;

        // If dictionaries are equal, check our stream
        // We don't go as far as decompressing the data to see if it's equal
        auto self_buffer = self.getRawStreamData();
        auto other_buffer = other.getRawStreamData();

        // Early out: if underlying qpdf Buffers happen to be the same, the data is
        // the same
        if (self_buffer == other_buffer)
            return true;
        // Early out: if sizes are different, data cannot be the same
        if (self_buffer->getSize() != other_buffer->getSize())
            return false;

        // Slow path: memcmp the binary data
        return 0 == std::memcmp(self_buffer->getBuffer(),
                        other_buffer->getBuffer(),
                        self_buffer->getSize());
    }
    // LCOV_EXCL_START
    case qpdf_object_type_e::ot_boolean:
    case qpdf_object_type_e::ot_integer:
    case qpdf_object_type_e::ot_real:
        throw std::logic_error("should have eliminated numeric types by now");
    default:
        throw std::logic_error("invalid object type");
    }
    // LCOV_EXCL_STOP
}

bool objecthandle_equal(QPDFObjectHandle self, QPDFObjectHandle other)
{
    auto visited = std::set<std::pair<std::string, std::string>>();
    return objecthandle_equal_inner(self, other, visited);
}