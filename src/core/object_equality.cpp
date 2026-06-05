// SPDX-FileCopyrightText: 2025 James R. Barlow
// SPDX-License-Identifier: MPL-2.0

#include "pikepdf.h"

#include <cstring>
#include <string>
#include <utility>
#include <vector>

#include <qpdf/QPDFObjectHandle.hh>

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

// The recursion path: the pairs of container objects we are currently in the
// middle of comparing. We identify objects by their underlying identity
// (isSameObjectAs) rather than by serializing them, because serializing a
// cyclic *direct* object recurses forever and overflows the stack (issue #731).
// Indirect objects could be identified cheaply by their object/generation
// number, but direct objects all share generation (0, 0), so identity is the
// only thing that works for both.
using ComparisonPath = std::vector<std::pair<QPDFObjectHandle, QPDFObjectHandle>>;

// Return true if we are already comparing this exact pair of objects further up
// the recursion stack, i.e. we have followed a cycle back to where we started.
static bool pair_on_path(
    ComparisonPath &path, QPDFObjectHandle &self, QPDFObjectHandle &other)
{
    for (auto &entry : path) {
        if (entry.first.isSameObjectAs(self) && entry.second.isSameObjectAs(other))
            return true;
    }
    return false;
}

// RAII helper to push a pair onto the comparison path for the duration of a
// recursive container comparison and pop it again on the way out.
class PathGuard {
public:
    PathGuard(ComparisonPath &path, QPDFObjectHandle self, QPDFObjectHandle other)
        : path(path)
    {
        path.emplace_back(std::move(self), std::move(other));
    }
    ~PathGuard() { path.pop_back(); }
    PathGuard(const PathGuard &) = delete;
    PathGuard &operator=(const PathGuard &) = delete;
    PathGuard(PathGuard &&) = delete;
    PathGuard &operator=(PathGuard &&) = delete;

private:
    ComparisonPath &path;
};

static bool objecthandle_equal_inner(
    QPDFObjectHandle self, QPDFObjectHandle other, ComparisonPath &path)
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
        bool result = py::cast<bool>(pyresult);
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
        // If we are already comparing this pair higher up the stack, we have
        // followed a cycle; treat it as equal so the recursion terminates.
        if (pair_on_path(path, self, other))
            return true;
        PathGuard guard(path, self, other);
        auto self_aitems = self.aitems();
        auto other_aitems = other.aitems();
        auto iter_self = self_aitems.begin();
        auto iter_other = other_aitems.begin();
        for (; iter_self != self_aitems.end(); ++iter_self, ++iter_other) {
            if (!objecthandle_equal_inner(*iter_self, *iter_other, path)) {
                return false;
            }
        }
        return true;
    }
    case qpdf_object_type_e::ot_dictionary: {
        if (self.getKeys() != other.getKeys())
            return false;
        if (pair_on_path(path, self, other))
            return true;
        PathGuard guard(path, self, other);
        for (auto &key : self.getKeys()) {
            auto value = self.getKey(key);
            auto other_value = other.getKey(key);
            if (other_value.isNull())
                return false;
            if (!objecthandle_equal_inner(value, other_value, path))
                return false;
        }
        return true;
    }
    case qpdf_object_type_e::ot_stream: {
        // Recurse into this function to check if our dictionaries are equal
        if (!objecthandle_equal_inner(self.getDict(), other.getDict(), path))
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
    ComparisonPath path;
    return objecthandle_equal_inner(self, other, path);
}