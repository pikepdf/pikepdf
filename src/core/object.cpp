// SPDX-FileCopyrightText: 2022 James R. Barlow
// SPDX-License-Identifier: MPL-2.0

#include <cctype>
#include <cmath>
#include <cstring>

#include <qpdf/Buffer.hh>
#include <qpdf/Constants.h>
#include <qpdf/DLL.h>
#include <qpdf/Pl_String.hh>
#include <qpdf/QPDF.hh>
#include <qpdf/QPDFExc.hh>
#include <qpdf/QPDFObjGen.hh>
#include <qpdf/QPDFObjectHandle.hh>
#include <qpdf/QPDFWriter.hh>
#include <qpdf/QPDFXRefEntry.hh>
#include <qpdf/Types.h>

#include <pybind11/pybind11.h>
#include <pybind11/stl.h>

#include "pikepdf.h"
#include "utils.h"

#include "namepath.h"
#include "parsers.h"

// Encodes Python key to bytes, handling surrogates for invalid UTF-8.
std::string string_from_key(py::handle key)
{
    if (py::isinstance<py::bytes>(key)) {
        return key.cast<std::string>();
    }
    if (py::isinstance<py::str>(key)) {
        py::bytes encoded_key = key.attr("encode")("utf-8", "surrogateescape");
        return encoded_key.cast<std::string>();
    }
    throw py::type_error("Key must be str or bytes");
}

/*
  Helper: Decode C++ string to Python str using surrogateescape
  This prevents crashes when dictionary keys contain invalid UTF-8 (e.g. \x80)
*/
py::str safe_decode(std::string const &s)
{
    // Use the C-API to handle the specific "surrogateescape" requirement
    // PyUnicode_DecodeUTF8 returns a "New Reference"
    py::handle py_s = PyUnicode_DecodeUTF8(s.c_str(), s.size(), "surrogateescape");

    if (!py_s) {
        throw py::error_already_set();
    }

    return py::reinterpret_steal<py::str>(py_s);
}

/*
Type table

See objects.rst. In short and with technical details:

These qpdf types are directly mapped to a native Python equivalent. The C++
object is never returned to Python; a Python object is returned instead.
Adding one of these to a qpdf container type causes the appropriate conversion.
    Boolean <-> bool
    Integer <-> int
    Real <-> Decimal
    Real <- float
    Null <-> None

PDF semantics dictate that setting a dictionary key to Null deletes the key.

    d['/Key'] = None  # would delete /Key

For Python users this would be unexpected, so this action is prohibited.
You cannot set keys to None.

pikepdf.String is a "type" that can be converted with str() or bytes() as
needed.

*/

static void ensure_array(QPDFObjectHandle &h, const char *action)
{
    if (!h.isArray()) {
        throw py::type_error("pikepdf.Object is not an Array: cannot " +
                             std::string(action) + " object of type " +
                             h.getTypeName());
    }
}

py::size_t list_range_check(QPDFObjectHandle h, int index)
{
    ensure_array(h, "check list range");
    if (index < 0)
        index += h.getArrayNItems(); // Support negative indexing
    if (!(0 <= index && index < h.getArrayNItems()))
        throw py::index_error("index out of range");
    return static_cast<py::size_t>(index);
}

static void ensure_keyed(
    QPDFObjectHandle &h, const char *action, std::string const &key)
{
    if (!h.isDictionary() && !h.isStream()) {
        throw py::value_error("pikepdf.Object is not a Dictionary or Stream: cannot " +
                              std::string(action) + " key '" + key +
                              "' on object of type " + h.getTypeName());
    }
}

bool object_has_key(QPDFObjectHandle h, std::string const &key)
{
    ensure_keyed(h, "check existence of", key);
    QPDFObjectHandle dict = h.isStream() ? h.getDict() : h;
    return dict.hasKey(key);
}

bool array_has_item(QPDFObjectHandle haystack, QPDFObjectHandle needle)
{
    ensure_array(haystack, "check for an item");

    for (auto &item : haystack.aitems()) {
        if (objecthandle_equal(item, needle))
            return true;
    }
    return false;
}

QPDFObjectHandle object_get_key(QPDFObjectHandle h, std::string const &key)
{
    ensure_keyed(h, "get", key);
    QPDFObjectHandle dict = h.isStream() ? h.getDict() : h;
    if (!dict.hasKey(key))
        throw py::key_error(key);
    return dict.getKey(key);
}

void object_set_key(QPDFObjectHandle h, std::string const &key, QPDFObjectHandle &value)
{
    ensure_keyed(h, "set", key);
    if (value.isNull())
        throw py::value_error(
            "PDF Dictionary keys may not be set to None - use 'del' to remove");
    if (key == "/")
        throw py::key_error("PDF Dictionary keys may not be '/'");
    if (!str_startswith(key, "/"))
        throw py::key_error("PDF Dictionary keys must begin with '/'");
    if (h.isStream() && key == "/Length") {
        throw py::key_error("/Length may not be modified");
    }

    // For streams, the actual dictionary is attached to stream object
    QPDFObjectHandle dict = h.isStream() ? h.getDict() : h;

    // A stream dictionary has no owner, so use the stream object in this comparison
    dict.replaceKey(key, value);
}

void object_del_key(QPDFObjectHandle h, std::string const &key)
{
    ensure_keyed(h, "delete", key);
    if (h.isStream() && key == "/Length") {
        throw py::key_error("/Length may not be deleted");
    }

    // For streams, the actual dictionary is attached to stream object
    QPDFObjectHandle dict = h.isStream() ? h.getDict() : h;

    if (!dict.hasKey(key))
        throw py::key_error(key);

    dict.removeKey(key);
}

// Traverse a NamePath, returning the final object or throwing with context
QPDFObjectHandle traverse_namepath(
    QPDFObjectHandle h, NamePath const &path, bool for_set = false)
{
    auto const &components = path.components();
    size_t end = for_set ? components.size() - 1 : components.size();

    QPDFObjectHandle current = h;
    for (size_t i = 0; i < end; ++i) {
        if (std::holds_alternative<std::string>(components[i])) {
            auto const &key = std::get<std::string>(components[i]);
            if (!current.isDictionary() && !current.isStream()) {
                throw py::type_error("Expected Dictionary or Stream at " +
                                     path.format_path(i) + ", got " +
                                     current.getTypeName());
            }
            QPDFObjectHandle dict = current.isStream() ? current.getDict() : current;
            if (!dict.hasKey(key)) {
                throw py::key_error(
                    "Key " + key + " not found; traversed " + path.format_path(i));
            }
            current = dict.getKey(key);
        } else {
            int index = std::get<int>(components[i]);
            if (!current.isArray()) {
                throw py::type_error("Expected Array at " + path.format_path(i) +
                                     ", got " + current.getTypeName());
            }
            int size = current.getArrayNItems();
            if (index < 0)
                index += size;
            if (index < 0 || index >= size) {
                throw py::index_error("Index " + std::to_string(index) +
                                      " out of range at " + path.format_path(i));
            }
            current = current.getArrayItem(static_cast<size_t>(index));
        }
    }
    return current;
}

std::pair<int, int> object_get_objgen(QPDFObjectHandle h)
{
    auto objgen = h.getObjGen();
    return std::pair<int, int>(objgen.getObj(), objgen.getGen());
}

QPDFObjectHandle copy_object(QPDFObjectHandle &h)
{
    if (h.isStream())
        return h.copyStream();
    return h.shallowCopy();
}

std::shared_ptr<Buffer> get_stream_data(
    QPDFObjectHandle &h, qpdf_stream_decode_level_e decode_level)
{
    try {
        return h.getStreamData(decode_level);
    } catch (const QPDFExc &e) {
        // Make a new exception that has the objgen info, since qpdf's
        // will not
        std::string msg = e.getMessageDetail();
        str_replace(msg, "getStreamData", "read_bytes");
        throw QPDFExc(e.getErrorCode(),
            e.getFilename(),
            std::string("object ") + h.getObjGen().unparse(),
            e.getFilePosition(),
            msg);
    }
}

void init_object(py::module_ &m)
{
    py::enum_<qpdf_object_type_e>(m, "ObjectType")
        .value("uninitialized", qpdf_object_type_e::ot_uninitialized)
        .value("reserved", qpdf_object_type_e::ot_reserved)
        .value("null", qpdf_object_type_e::ot_null)
        .value("boolean", qpdf_object_type_e::ot_boolean)
        .value("integer", qpdf_object_type_e::ot_integer)
        .value("real", qpdf_object_type_e::ot_real)
        .value("string", qpdf_object_type_e::ot_string)
        .value("name_", qpdf_object_type_e::ot_name)
        .value("array", qpdf_object_type_e::ot_array)
        .value("dictionary", qpdf_object_type_e::ot_dictionary)
        .value("stream", qpdf_object_type_e::ot_stream)
        .value("operator", qpdf_object_type_e::ot_operator)
        .value("inlineimage", qpdf_object_type_e::ot_inlineimage);

    py::class_<Buffer, py::smart_holder>(m, "Buffer", py::buffer_protocol())
        .def_buffer([](Buffer &b) -> py::buffer_info {
            return py::buffer_info(b.getBuffer(),
                sizeof(unsigned char),
                py::format_descriptor<unsigned char>::format(),
                1,
                {b.getSize()},
                {sizeof(unsigned char)});
        });

    py::bind_vector<ObjectList>(m, "_ObjectList") // Autoformat fix
        .def("__repr__", [](ObjectList &ol) {
            std::ostringstream ss;
            ss.imbue(std::locale::classic());
            bool first = true;
            ss << "pikepdf._core._ObjectList([";
            for (auto &h : ol) {
                if (first) {
                    first = false;
                } else {
                    ss << ", ";
                }
                ss << objecthandle_repr(h);
            }
            ss << "])";
            return ss.str();
        });

    py::bind_map<ObjectMap>(m, "_ObjectMapping");

// MSVC raises a false positive warning here
#if _MSC_VER
#    pragma warning(suppress : 4267)
#endif
    py::class_<QPDFObjectHandle, py::smart_holder>(m, "Object")
        .def_property_readonly("_type_code", &QPDFObjectHandle::getTypeCode)
        .def_property_readonly("_type_name", &QPDFObjectHandle::getTypeName)
        .def(
            "is_owned_by",
            [](QPDFObjectHandle &h, QPDF &possible_owner) {
                return (h.getOwningQPDF() == &possible_owner);
            },
            py::arg("possible_owner"))
        .def("same_owner_as",
            [](QPDFObjectHandle &self, QPDFObjectHandle &other) {
                return self.getOwningQPDF() == other.getOwningQPDF();
            })
        .def("with_same_owner_as",
            [](QPDFObjectHandle &self, QPDFObjectHandle &other) {
                QPDF *self_owner = self.getOwningQPDF();
                QPDF *other_owner = other.getOwningQPDF();

                if (self_owner == other_owner)
                    return self;
                if (!other_owner)
                    throw py::value_error(
                        "with_same_owner_as() called for object that has no owner");
                if (!self.isIndirect())
                    return other_owner->makeIndirectObject(self);

                auto self_in_other = other_owner->copyForeignObject(self);
                return self_in_other;
            })
        .def_property_readonly("is_indirect", &QPDFObjectHandle::isIndirect)
        .def("__repr__", &objecthandle_repr)
        .def("__hash__",
            [](QPDFObjectHandle &self) -> py::int_ {
                if (self.isIndirect())
                    throw py::type_error("Can't hash indirect object");

                // Objects which compare equal must have the same hash value
                switch (self.getTypeCode()) {
                case qpdf_object_type_e::ot_string:
                    return py::hash(py::bytes(self.getUTF8Value()));
                case qpdf_object_type_e::ot_name:
                    return py::hash(py::bytes(self.getName()));
                case qpdf_object_type_e::ot_operator:
                    return py::hash(py::bytes(self.getOperatorValue()));
                case qpdf_object_type_e::ot_array:
                case qpdf_object_type_e::ot_dictionary:
                case qpdf_object_type_e::ot_stream:
                case qpdf_object_type_e::ot_inlineimage:
                    throw py::type_error("Can't hash mutable object");
                default:
                    break;
                }
                throw std::logic_error("don't know how to hash this"); // LCOV_EXCL_LINE
            })
        .def(
            "__eq__",
            [](QPDFObjectHandle &self, QPDFObjectHandle &other) {
                return objecthandle_equal(self, other);
            },
            py::is_operator())
        .def(
            "__eq__",
            [](QPDFObjectHandle &self, py::str other) {
                std::string utf8_other = other.cast<std::string>();
                switch (self.getTypeCode()) {
                case qpdf_object_type_e::ot_string:
                    return self.getUTF8Value() == utf8_other;
                case qpdf_object_type_e::ot_name:
                    return self.getName() == utf8_other;
                default:
                    return false;
                }
            },
            py::is_operator())
        .def(
            "__eq__",
            [](QPDFObjectHandle &self, py::bytes other) {
                std::string bytes_other = other.cast<std::string>();
                switch (self.getTypeCode()) {
                case qpdf_object_type_e::ot_string:
                    return self.getStringValue() == bytes_other;
                case qpdf_object_type_e::ot_name:
                    return self.getName() == bytes_other;
                default:
                    return false;
                }
            },
            py::is_operator())
        .def(
            "__eq__",
            [](QPDFObjectHandle &self, py::object other) -> py::object {
                QPDFObjectHandle q_other;
                try {
                    q_other = objecthandle_encode(other);
                } catch (const py::cast_error &) {
                    // Cannot remove this construct without reaching into pybind11
                    // internals - reason being that we don't automatically convert
                    // py::object to handle, so pybind11 doesn't know that we tried.
                    return py::reinterpret_borrow<py::object>(
                        py::handle(Py_NotImplemented));
                }
                bool result = objecthandle_equal(self, q_other);
                return py::bool_(result);
            },
            py::is_operator())
        .def("__copy__", &copy_object)
        .def("__len__",
            [](QPDFObjectHandle &h) -> py::size_t {
                if (h.isDictionary()) {
                    // getKeys constructs a new object, so this is better
                    return static_cast<py::size_t>(h.getDictAsMap().size());
                } else if (h.isArray()) {
                    int nitems = h.getArrayNItems();
                    // LCOV_EXCL_START
                    if (nitems < 0) {
                        throw std::logic_error("Array items < 0");
                    }
                    // LCOV_EXCL_STOP
                    return static_cast<py::size_t>(nitems);
                }
                if (h.isStream())
                    throw py::type_error(
                        "length not defined for object - "
                        "use len(obj.keys()) for number of dictionary keys, "
                        "or len(bytes(obj)) for length of stream data");
                throw py::type_error("length not defined for object");
            })
        .def("__bool__",
            [](QPDFObjectHandle &h) -> bool {
                // Handle boolean objects (in explicit conversion mode)
                if (h.isBool()) {
                    return h.getBoolValue();
                }
                if (h.isDictionary()) {
                    return h.getDictAsMap().size() > 0;
                } else if (h.isArray()) {
                    int nitems = h.getArrayNItems();
                    // LCOV_EXCL_START
                    if (nitems < 0) {
                        throw std::logic_error("Array items < 0");
                    }
                    // LCOV_EXCL_STOP
                    return nitems > 0;
                } else if (h.isStream()) {
                    auto stream_dict = h.getDict();
                    auto len = stream_dict.getKey("/Length");
                    if (len.isNull() || !len.isInteger() || len.getIntValue() <= 0) {
                        return false;
                    }
                    return true;
                } else if (h.isString()) {
                    return h.getStringValue().size() > 0;
                } else if (h.isName()) {
                    return h.getName().size() > 0;
                } else if (h.isOperator()) {
                    return h.getOperatorValue().size() > 0;
                } else if (h.isNull()) {
                    return false;
                }
                throw py::notimpl_error("code is unreachable");
            })
        .def("__int__",
            [](QPDFObjectHandle &h) -> long long {
                if (!h.isInteger())
                    throw py::type_error("Object is not an integer");
                return h.getIntValue();
            })
        .def("__index__",
            [](QPDFObjectHandle &h) -> long long {
                if (!h.isInteger())
                    throw py::type_error("Object is not an integer");
                return h.getIntValue();
            })
        .def("__float__",
            [](QPDFObjectHandle &h) -> double {
                if (h.isInteger())
                    return static_cast<double>(h.getIntValue());
                if (h.isReal())
                    return std::stod(h.getRealValue());
                throw py::type_error("Object is not numeric");
            })
        .def("_get_real_value",
            [](QPDFObjectHandle &h) -> std::string {
                if (!h.isReal())
                    throw py::type_error("Object is not a real number");
                return h.getRealValue();
            })
        .def(
            "__add__",
            [](QPDFObjectHandle &h, py::iterable iterable) -> py::object {
                // We still need this check because 'h' could be a pikepdf.Integer
                if (!h.isArray()) {
                    return py::handle(Py_NotImplemented).cast<py::object>();
                }

                auto result = h.shallowCopy();
                for (auto const &item : iterable) {
                    result.appendItem(
                        objecthandle_encode(py::reinterpret_borrow<py::object>(item)));
                }
                return py::cast(result);
            },
            py::arg("iterable"),
            py::is_operator(),
            "Return a new Array containing elements from both operands.")
        // Arithmetic operations for Integer objects (return native Python types)
        // Integer + int -> int
        .def(
            "__add__",
            [](QPDFObjectHandle &h, long long other) -> long long {
                if (!h.isInteger())
                    throw py::type_error("Object is not an integer");
                return h.getIntValue() + other;
            },
            py::is_operator())
        .def(
            "__radd__",
            [](QPDFObjectHandle &h, long long other) -> long long {
                if (!h.isInteger())
                    throw py::type_error("Object is not an integer");
                return other + h.getIntValue();
            },
            py::is_operator())
        // Numeric + float -> float (for Integer or Real)
        .def(
            "__add__",
            [](QPDFObjectHandle &h, double other) -> py::object {
                if (h.isInteger())
                    return py::cast(static_cast<double>(h.getIntValue()) + other);
                if (h.isReal())
                    return py::cast(std::stod(h.getRealValue()) + other);
                throw py::type_error("Object is not numeric");
            },
            py::is_operator())
        .def(
            "__radd__",
            [](QPDFObjectHandle &h, double other) -> py::object {
                if (h.isInteger())
                    return py::cast(other + static_cast<double>(h.getIntValue()));
                if (h.isReal())
                    return py::cast(other + std::stod(h.getRealValue()));
                throw py::type_error("Object is not numeric");
            },
            py::is_operator())
        // Fallback for other types (e.g., Decimal) - return NotImplemented
        .def("__add__",
            [](QPDFObjectHandle &h, py::object other) -> py::object {
                if (!h.isArray())
                    return py::cast<py::object>(Py_NotImplemented);

                // We accept py::object to prevent premature pybind11 coercion errors
                if (!py::isinstance<py::iterable>(other))
                    return py::cast<py::object>(Py_NotImplemented);

                auto result = QPDFObjectHandle::newArray();
                int n = h.getArrayNItems();
                for (int i = 0; i < n; ++i) {
                    result.appendItem(h.getArrayItem(i));
                }

                // Constructing the iterable only after we know we are in an array
                // context
                py::iterable it = py::reinterpret_borrow<py::iterable>(other);
                for (auto const &item : it) {
                    result.appendItem(
                        objecthandle_encode(py::reinterpret_borrow<py::object>(item)));
                }
                return py::cast(result);
            })
        .def(
            "__radd__",
            [](QPDFObjectHandle &h, py::object other) -> py::object {
                if (!h.isInteger() && !h.isReal())
                    throw py::type_error("Object is not numeric");
                return py::handle(Py_NotImplemented).cast<py::object>();
            },
            py::is_operator())
        .def(
            "__sub__",
            [](QPDFObjectHandle &h, long long other) -> long long {
                if (!h.isInteger())
                    throw py::type_error("Object is not an integer");
                return h.getIntValue() - other;
            },
            py::is_operator())
        .def(
            "__rsub__",
            [](QPDFObjectHandle &h, long long other) -> long long {
                if (!h.isInteger())
                    throw py::type_error("Object is not an integer");
                return other - h.getIntValue();
            },
            py::is_operator())
        .def(
            "__sub__",
            [](QPDFObjectHandle &h, double other) -> py::object {
                if (h.isInteger())
                    return py::cast(static_cast<double>(h.getIntValue()) - other);
                if (h.isReal())
                    return py::cast(std::stod(h.getRealValue()) - other);
                throw py::type_error("Object is not numeric");
            },
            py::is_operator())
        .def(
            "__rsub__",
            [](QPDFObjectHandle &h, double other) -> py::object {
                if (h.isInteger())
                    return py::cast(other - static_cast<double>(h.getIntValue()));
                if (h.isReal())
                    return py::cast(other - std::stod(h.getRealValue()));
                throw py::type_error("Object is not numeric");
            },
            py::is_operator())
        .def(
            "__sub__",
            [](QPDFObjectHandle &h, py::object other) -> py::object {
                if (!h.isInteger() && !h.isReal())
                    throw py::type_error("Object is not numeric");
                return py::handle(Py_NotImplemented).cast<py::object>();
            },
            py::is_operator())
        .def(
            "__rsub__",
            [](QPDFObjectHandle &h, py::object other) -> py::object {
                if (!h.isInteger() && !h.isReal())
                    throw py::type_error("Object is not numeric");
                return py::handle(Py_NotImplemented).cast<py::object>();
            },
            py::is_operator())
        .def(
            "__mul__",
            [](QPDFObjectHandle &h, long long other) -> long long {
                if (!h.isInteger())
                    throw py::type_error("Object is not an integer");
                return h.getIntValue() * other;
            },
            py::is_operator())
        .def(
            "__rmul__",
            [](QPDFObjectHandle &h, long long other) -> long long {
                if (!h.isInteger())
                    throw py::type_error("Object is not an integer");
                return other * h.getIntValue();
            },
            py::is_operator())
        .def(
            "__mul__",
            [](QPDFObjectHandle &h, double other) -> py::object {
                if (h.isInteger())
                    return py::cast(static_cast<double>(h.getIntValue()) * other);
                if (h.isReal())
                    return py::cast(std::stod(h.getRealValue()) * other);
                throw py::type_error("Object is not numeric");
            },
            py::is_operator())
        .def(
            "__rmul__",
            [](QPDFObjectHandle &h, double other) -> py::object {
                if (h.isInteger())
                    return py::cast(other * static_cast<double>(h.getIntValue()));
                if (h.isReal())
                    return py::cast(other * std::stod(h.getRealValue()));
                throw py::type_error("Object is not numeric");
            },
            py::is_operator())
        .def(
            "__mul__",
            [](QPDFObjectHandle &h, py::object other) -> py::object {
                if (!h.isInteger() && !h.isReal())
                    throw py::type_error("Object is not numeric");
                return py::handle(Py_NotImplemented).cast<py::object>();
            },
            py::is_operator())
        .def(
            "__rmul__",
            [](QPDFObjectHandle &h, py::object other) -> py::object {
                if (!h.isInteger() && !h.isReal())
                    throw py::type_error("Object is not numeric");
                return py::handle(Py_NotImplemented).cast<py::object>();
            },
            py::is_operator())
        // True division: always returns float
        .def(
            "__truediv__",
            [](QPDFObjectHandle &h, double other) -> py::object {
                if (other == 0.0)
                    throw py::value_error("division by zero");
                if (h.isInteger())
                    return py::cast(static_cast<double>(h.getIntValue()) / other);
                if (h.isReal())
                    return py::cast(std::stod(h.getRealValue()) / other);
                throw py::type_error("Object is not numeric");
            },
            py::is_operator())
        .def(
            "__rtruediv__",
            [](QPDFObjectHandle &h, double other) -> py::object {
                double val;
                if (h.isInteger())
                    val = static_cast<double>(h.getIntValue());
                else if (h.isReal())
                    val = std::stod(h.getRealValue());
                else
                    throw py::type_error("Object is not numeric");
                if (val == 0.0)
                    throw py::value_error("division by zero");
                return py::cast(other / val);
            },
            py::is_operator())
        .def(
            "__truediv__",
            [](QPDFObjectHandle &h, long long other) -> py::object {
                if (other == 0)
                    throw py::value_error("division by zero");
                if (h.isInteger())
                    return py::cast(static_cast<double>(h.getIntValue()) /
                                    static_cast<double>(other));
                if (h.isReal())
                    return py::cast(
                        std::stod(h.getRealValue()) / static_cast<double>(other));
                throw py::type_error("Object is not numeric");
            },
            py::is_operator())
        .def(
            "__rtruediv__",
            [](QPDFObjectHandle &h, long long other) -> py::object {
                double val;
                if (h.isInteger())
                    val = static_cast<double>(h.getIntValue());
                else if (h.isReal())
                    val = std::stod(h.getRealValue());
                else
                    throw py::type_error("Object is not numeric");
                if (val == 0.0)
                    throw py::value_error("division by zero");
                return py::cast(static_cast<double>(other) / val);
            },
            py::is_operator())
        .def(
            "__truediv__",
            [](QPDFObjectHandle &h, py::object other) -> py::object {
                if (!h.isInteger() && !h.isReal())
                    throw py::type_error("Object is not numeric");
                return py::handle(Py_NotImplemented).cast<py::object>();
            },
            py::is_operator())
        .def(
            "__rtruediv__",
            [](QPDFObjectHandle &h, py::object other) -> py::object {
                if (!h.isInteger() && !h.isReal())
                    throw py::type_error("Object is not numeric");
                return py::handle(Py_NotImplemented).cast<py::object>();
            },
            py::is_operator())
        // Floor division: Integer // int -> int
        .def(
            "__floordiv__",
            [](QPDFObjectHandle &h, long long other) -> long long {
                if (!h.isInteger())
                    throw py::type_error("Object is not an integer");
                if (other == 0)
                    throw py::value_error("division by zero");
                return h.getIntValue() / other;
            },
            py::is_operator())
        .def(
            "__rfloordiv__",
            [](QPDFObjectHandle &h, long long other) -> long long {
                if (!h.isInteger())
                    throw py::type_error("Object is not an integer");
                long long val = h.getIntValue();
                if (val == 0)
                    throw py::value_error("division by zero");
                return other / val;
            },
            py::is_operator())
        // Floor division with float -> float
        .def(
            "__floordiv__",
            [](QPDFObjectHandle &h, double other) -> py::object {
                if (other == 0.0)
                    throw py::value_error("division by zero");
                if (h.isInteger())
                    return py::cast(
                        std::floor(static_cast<double>(h.getIntValue()) / other));
                if (h.isReal())
                    return py::cast(std::floor(std::stod(h.getRealValue()) / other));
                throw py::type_error("Object is not numeric");
            },
            py::is_operator())
        .def(
            "__rfloordiv__",
            [](QPDFObjectHandle &h, double other) -> py::object {
                double val;
                if (h.isInteger())
                    val = static_cast<double>(h.getIntValue());
                else if (h.isReal())
                    val = std::stod(h.getRealValue());
                else
                    throw py::type_error("Object is not numeric");
                if (val == 0.0)
                    throw py::value_error("division by zero");
                return py::cast(std::floor(other / val));
            },
            py::is_operator())
        .def(
            "__floordiv__",
            [](QPDFObjectHandle &h, py::object other) -> py::object {
                if (!h.isInteger() && !h.isReal())
                    throw py::type_error("Object is not numeric");
                return py::handle(Py_NotImplemented).cast<py::object>();
            },
            py::is_operator())
        .def(
            "__rfloordiv__",
            [](QPDFObjectHandle &h, py::object other) -> py::object {
                if (!h.isInteger() && !h.isReal())
                    throw py::type_error("Object is not numeric");
                return py::handle(Py_NotImplemented).cast<py::object>();
            },
            py::is_operator())
        .def(
            "__mod__",
            [](QPDFObjectHandle &h, long long other) -> long long {
                if (!h.isInteger())
                    throw py::type_error("Object is not an integer");
                if (other == 0)
                    throw py::value_error("modulo by zero");
                return h.getIntValue() % other;
            },
            py::is_operator())
        .def(
            "__rmod__",
            [](QPDFObjectHandle &h, long long other) -> long long {
                if (!h.isInteger())
                    throw py::type_error("Object is not an integer");
                long long val = h.getIntValue();
                if (val == 0)
                    throw py::value_error("modulo by zero");
                return other % val;
            },
            py::is_operator())
        .def(
            "__mod__",
            [](QPDFObjectHandle &h, double other) -> py::object {
                if (other == 0.0)
                    throw py::value_error("modulo by zero");
                if (h.isInteger())
                    return py::cast(
                        std::fmod(static_cast<double>(h.getIntValue()), other));
                if (h.isReal())
                    return py::cast(std::fmod(std::stod(h.getRealValue()), other));
                throw py::type_error("Object is not numeric");
            },
            py::is_operator())
        .def(
            "__rmod__",
            [](QPDFObjectHandle &h, double other) -> py::object {
                double val;
                if (h.isInteger())
                    val = static_cast<double>(h.getIntValue());
                else if (h.isReal())
                    val = std::stod(h.getRealValue());
                else
                    throw py::type_error("Object is not numeric");
                if (val == 0.0)
                    throw py::value_error("modulo by zero");
                return py::cast(std::fmod(other, val));
            },
            py::is_operator())
        .def(
            "__mod__",
            [](QPDFObjectHandle &h, py::object other) -> py::object {
                if (!h.isInteger() && !h.isReal())
                    throw py::type_error("Object is not numeric");
                return py::handle(Py_NotImplemented).cast<py::object>();
            },
            py::is_operator())
        .def(
            "__rmod__",
            [](QPDFObjectHandle &h, py::object other) -> py::object {
                if (!h.isInteger() && !h.isReal())
                    throw py::type_error("Object is not numeric");
                return py::handle(Py_NotImplemented).cast<py::object>();
            },
            py::is_operator())
        .def("__neg__",
            [](QPDFObjectHandle &h) -> py::object {
                if (h.isInteger())
                    return py::cast(-h.getIntValue());
                if (h.isReal())
                    return py::cast(-std::stod(h.getRealValue()));
                throw py::type_error("Object is not numeric");
            })
        .def("__pos__",
            [](QPDFObjectHandle &h) -> py::object {
                if (h.isInteger())
                    return py::cast(+h.getIntValue());
                if (h.isReal())
                    return py::cast(+std::stod(h.getRealValue()));
                throw py::type_error("Object is not numeric");
            })
        .def("__abs__",
            [](QPDFObjectHandle &h) -> py::object {
                if (h.isInteger())
                    return py::cast(std::abs(h.getIntValue()));
                if (h.isReal())
                    return py::cast(std::abs(std::stod(h.getRealValue())));
                throw py::type_error("Object is not numeric");
            })
        .def("__getitem__",
            [](QPDFObjectHandle &h, int index) {
                auto u_index = list_range_check(h, index);
                return h.getArrayItem(u_index);
            })
        .def(
            "__getitem__",
            [](QPDFObjectHandle &h, py::slice slice) -> QPDFObjectHandle {
                ensure_array(h, "slice");

                size_t start, stop, step, slicelength;
                if (!slice.compute(
                        h.getArrayNItems(), &start, &stop, &step, &slicelength))
                    throw py::error_already_set();

                std::vector<QPDFObjectHandle> items;
                for (size_t i = 0; i < slicelength; ++i) {
                    items.push_back(h.getArrayItem(static_cast<int>(start)));
                    start += step;
                }
                return QPDFObjectHandle::newArray(items);
            },
            "Return a slice of the array as a new pikepdf.Array")
        .def("__getitem__",
            [](QPDFObjectHandle &h, QPDFObjectHandle &name) {
                return object_get_key(h, name.getName());
            })
        .def("__getitem__",
            [](QPDFObjectHandle &h, NamePath const &path) {
                if (path.empty()) {
                    return h; // Empty path returns self
                }
                return traverse_namepath(h, path);
            })
        .def("__getitem__",
            [](QPDFObjectHandle &h, py::object key) -> QPDFObjectHandle {
                std::string k = string_from_key(key);
                return object_get_key(h, k);
            })
        .def("__setitem__",
            [](QPDFObjectHandle &h, QPDFObjectHandle &name, QPDFObjectHandle &value) {
                object_set_key(h, name.getName(), value);
            })
        .def("__setitem__",
            [](QPDFObjectHandle &h, QPDFObjectHandle &name, py::object pyvalue) {
                auto value = objecthandle_encode(pyvalue);
                object_set_key(h, name.getName(), value);
            })
        .def(
            "copy",
            [](QPDFObjectHandle &h) {
                if (!h.isDictionary() && !h.isStream() && !h.isArray()) {
                    throw py::type_error(
                        std::string(
                            "pikepdf.Object is not an Array, Dictionary or Stream: ") +
                        "cannot copy an object of type " + h.getTypeName());
                }
                return copy_object(h);
            },
            "Create a shallow copy of the object.")
        .def(
            "update",
            [](QPDFObjectHandle &h, py::dict other) {
                // object_set_key handles the check if 'h' is a dictionary
                for (auto item : other) {
                    std::string key = py::str(item.first);
                    auto value = objecthandle_encode(item.second);
                    object_set_key(h, key, value);
                }
            },
            "Update the dictionary with key/value pairs from another dictionary.")
        .def(
            "update",
            [](QPDFObjectHandle &h, QPDFObjectHandle &other) {
                if (other.isStream()) {
                    throw py::type_error("update(): cannot update from a Stream; use "
                                         ".update(other.stream_dict()) instead");
                }
                if (!other.isDictionary()) {
                    throw py::type_error("update() argument must be a dictionary");
                }
                // Efficient C++-to-C++ merge without Python overhead
                for (auto const &key : other.getKeys()) {
                    QPDFObjectHandle val = other.getKey(key);
                    object_set_key(h, key, val);
                }
            },
            "Update the dictionary with key/value pairs from another pikepdf "
            "Dictionary.")
        .def("__setitem__",
            [](QPDFObjectHandle &h, NamePath const &path, QPDFObjectHandle &value) {
                if (path.empty()) {
                    throw py::value_error("Cannot assign to empty NamePath");
                }
                auto const &components = path.components();

                // Traverse to parent
                QPDFObjectHandle parent =
                    path.size() == 1 ? h : traverse_namepath(h, path, true);

                // Get final component
                auto const &last = components.back();
                if (std::holds_alternative<std::string>(last)) {
                    auto const &key = std::get<std::string>(last);
                    object_set_key(parent, key, value);
                } else {
                    int index = std::get<int>(last);
                    if (!parent.isArray()) {
                        throw py::type_error("Cannot use integer index on non-Array");
                    }
                    int size = parent.getArrayNItems();
                    if (index < 0)
                        index += size;
                    if (index < 0 || index >= size) {
                        throw py::index_error("Index out of range");
                    }
                    parent.setArrayItem(static_cast<size_t>(index), value);
                }
            })
        .def("__setitem__",
            [](QPDFObjectHandle &h, NamePath const &path, py::object pyvalue) {
                if (path.empty()) {
                    throw py::value_error("Cannot assign to empty NamePath");
                }
                auto value = objecthandle_encode(pyvalue);
                auto const &components = path.components();

                // Traverse to parent
                QPDFObjectHandle parent =
                    path.size() == 1 ? h : traverse_namepath(h, path, true);

                // Get final component
                auto const &last = components.back();
                if (std::holds_alternative<std::string>(last)) {
                    auto const &key = std::get<std::string>(last);
                    object_set_key(parent, key, value);
                } else {
                    int index = std::get<int>(last);
                    if (!parent.isArray()) {
                        throw py::type_error("Cannot use integer index on non-Array");
                    }
                    int size = parent.getArrayNItems();
                    if (index < 0)
                        index += size;
                    if (index < 0 || index >= size) {
                        throw py::index_error("Index out of range");
                    }
                    parent.setArrayItem(static_cast<size_t>(index), value);
                }
            })
        .def("__delitem__",
            [](QPDFObjectHandle &h, int index) {
                auto u_index = list_range_check(h, index);
                h.eraseItem(u_index);
            })
        .def("__delitem__",
            [](QPDFObjectHandle &h, QPDFObjectHandle &name) {
                object_del_key(h, name.getName());
            })
        .def("__delitem__",
            [](QPDFObjectHandle &h, py::slice slice) {
                ensure_array(h, "delete slice");
                size_t start, stop, step, slicelength;
                if (!slice.compute(
                        h.getArrayNItems(), &start, &stop, &step, &slicelength))
                    throw py::error_already_set();

                // Collect all target indices first
                std::vector<size_t> indices;
                for (size_t i = 0; i < slicelength; ++i) {
                    indices.push_back(start);
                    start += step;
                }

                // Sort indices in descending order and delete
                std::sort(indices.begin(), indices.end(), std::greater<size_t>());
                for (auto const &idx : indices) {
                    h.eraseItem(static_cast<int>(idx));
                }
            })
        .def("__delitem__",
            [](QPDFObjectHandle &h, py::object key) {
                std::string k = string_from_key(key);
                object_del_key(h, k);
            })
        .def("__getattr__",
            [](QPDFObjectHandle &h, std::string const &name) {
                QPDFObjectHandle value;
                std::string key = "/" + name;
                try {
                    value = object_get_key(h, key);
                } catch (const py::key_error &e) {
                    if (std::isupper(name[0]))
                        throw py::attribute_error(e.what());
                    else
                        throw py::attribute_error(name);
                } catch (const py::value_error &) {
                    if (name == std::string("__name__"))
                        throw py::attribute_error(name);
                    throw;
                }
                return value;
            })
        .def_property("stream_dict",
            &QPDFObjectHandle::getDict,
            &QPDFObjectHandle::replaceDict,
            py::return_value_policy::reference_internal)
        .def("__setattr__",
            [](QPDFObjectHandle &h, std::string const &name, py::object pyvalue) {
                if (h.isDictionary() || (h.isStream() && name != "stream_dict")) {
                    // Map attribute assignment to setting dictionary key
                    std::string key = "/" + name;
                    auto value = objecthandle_encode(pyvalue);
                    object_set_key(h, key, value);
                    return;
                }

                // If we don't have a special rule, do object.__setattr__()
                py::object baseobj = py::module_::import("builtins").attr("object");
                baseobj.attr("__setattr__")(py::cast(h), py::str(name), pyvalue);
            })
        .def("__delattr__",
            [](QPDFObjectHandle &h, std::string const &name) {
                std::string key = "/" + name;
                object_del_key(h, key);
            })
        .def("__dir__",
            [](QPDFObjectHandle &h) {
                py::list result;
                py::object obj = py::cast(h);
                py::object class_keys =
                    obj.attr("__class__").attr("__dict__").attr("keys")();
                for (auto attr : class_keys) {
                    result.append(attr);
                }
                if (h.isDictionary() || h.isStream()) {
                    for (auto key_attr : h.getKeys()) {
                        std::string s = key_attr.substr(1);
                        result.append(py::str(s));
                    }
                }
                return result;
            })
        .def(
            "get",
            [](QPDFObjectHandle &h, std::string const &key, py::object default_) {
                QPDFObjectHandle value;
                try {
                    value = object_get_key(h, key);
                } catch (const py::key_error &) {
                    return default_;
                }
                return py::cast(value);
            },
            py::arg("key"),
            py::arg("default") = py::none())
        .def(
            "get",
            [](QPDFObjectHandle &h, QPDFObjectHandle &name, py::object default_) {
                QPDFObjectHandle value;
                try {
                    value = object_get_key(h, name.getName());
                } catch (const py::key_error &) {
                    return default_;
                }
                return py::cast(value);
            },
            py::arg("key"),
            py::arg("default") = py::none())
        .def(
            "get",
            [](QPDFObjectHandle &h, NamePath const &path, py::object default_) {
                if (path.empty()) {
                    return py::cast(h);
                }
                try {
                    return py::cast(traverse_namepath(h, path));
                } catch (const py::key_error &) {
                    return default_;
                } catch (const py::index_error &) {
                    return default_;
                } catch (const py::type_error &) {
                    return default_;
                }
            },
            py::arg("path"),
            py::arg("default") = py::none())
        .def("keys",
            [](QPDFObjectHandle &h) {
                std::set<std::string> keys =
                    h.isStream() ? h.getDict().getKeys() : h.getKeys();
                py::set result;
                for (auto const &k : keys) {
                    result.add(safe_decode(k));
                }
                return result;
            })
        .def(
            "clear",
            [](QPDFObjectHandle &h) {
                ensure_array(h, "clear");
                int n = h.getArrayNItems();
                // Erase from back-to-front
                for (int i = n - 1; i >= 0; --i) {
                    h.eraseItem(i);
                }
            },
            "Remove all items from the array.")

        .def(
            "pop",
            [](QPDFObjectHandle &h, int index) {
                ensure_array(h, "pop");
                auto u_index = list_range_check(h, index);
                auto item = h.getArrayItem(static_cast<int>(u_index));
                h.eraseItem(static_cast<int>(u_index));
                return item;
            },
            py::arg("index") = -1,
            "Remove and return the item at the specified index.")

        .def(
            "insert",
            [](QPDFObjectHandle &h, int index, py::object pyitem) {
                ensure_array(h, "insert");
                int nitems = h.getArrayNItems();
                // Pythonic normalization: clamp to bounds rather than throwing range
                // error
                if (index < 0)
                    index += nitems;
                if (index < 0)
                    index = 0;
                if (index > nitems)
                    index = nitems;
                h.insertItem(index, objecthandle_encode(pyitem));
            },
            py::arg("index"),
            py::arg("value"),
            "Insert an object at the specified index.")

        .def(
            "remove",
            [](QPDFObjectHandle &h, py::object pyitem) {
                ensure_array(h, "remove");
                auto needle = objecthandle_encode(pyitem);
                int n = h.getArrayNItems();
                for (int i = 0; i < n; ++i) {
                    if (objecthandle_equal(h.getArrayItem(i), needle)) {
                        h.eraseItem(i);
                        return;
                    }
                }
                throw py::value_error("item not in array");
            },
            py::arg("value"),
            "Remove first occurrence of value.")

        .def(
            "index",
            [](QPDFObjectHandle &h, py::object pyitem) {
                ensure_array(h, "index");
                auto needle = objecthandle_encode(pyitem);
                int n = h.getArrayNItems();
                for (int i = 0; i < n; ++i) {
                    if (objecthandle_equal(h.getArrayItem(i), needle))
                        return i;
                }
                throw py::value_error("item not in array");
            },
            py::arg("value"),
            "Return first index of value.")

        .def(
            "count",
            [](QPDFObjectHandle &h, py::object pyitem) {
                ensure_array(h, "count");
                auto needle = objecthandle_encode(pyitem);
                int count = 0;
                for (auto const &item : h.aitems()) {
                    if (objecthandle_equal(item, needle))
                        count++;
                }
                return count;
            },
            py::arg("value"),
            "Return number of occurrences of value.")
        .def(
            "reverse",
            [](QPDFObjectHandle &h) {
                ensure_array(h, "reverse");
                int n = h.getArrayNItems();
                for (int i = 0; i < n / 2; ++i) {
                    auto left = h.getArrayItem(i);
                    auto right = h.getArrayItem(n - 1 - i);
                    h.setArrayItem(i, right);
                    h.setArrayItem(n - 1 - i, left);
                }
            },
            "Reverse the elements of the array in place.")
        .def(
            "copy",
            [](QPDFObjectHandle &h) { return h.shallowCopy(); },
            "Return a shallow copy of this PDF object.")
        .def(
            "extend",
            [](QPDFObjectHandle &h, py::iterable iterable) {
                ensure_array(h, "extend");
                for (auto const &item : iterable) {
                    h.appendItem(
                        objecthandle_encode(py::reinterpret_borrow<py::object>(item)));
                }
            },
            py::arg("iterable"),
            "Extend the array by appending elements from an iterable.")
        .def(
            "__iadd__",
            [](QPDFObjectHandle &h, py::iterable iterable) {
                ensure_array(h, "use += to extend");
                for (auto const &item : iterable) {
                    h.appendItem(
                        objecthandle_encode(py::reinterpret_borrow<py::object>(item)));
                }
                return h; // __iadd__ must return self
            },
            py::arg("iterable"),
            py::is_operator(),
            "Extend the array in-place using the += operator.")
        .def("__contains__",
            [](QPDFObjectHandle &h, QPDFObjectHandle &key) {
                if (h.isArray()) {
                    return array_has_item(h, key);
                }
                if (!key.isName())
                    throw py::type_error("Dictionaries can only contain Names");
                return object_has_key(h, key.getName());
            })
        .def("__contains__",
            [](QPDFObjectHandle &h, py::object key) {
                if (h.isArray()) {
                    if (py::isinstance<py::str>(key) ||
                        py::isinstance<py::bytes>(key)) {
                        throw py::type_error(
                            "Testing `str in pikepdf.Array` is not supported due to "
                            "ambiguity. Use `pikepdf.String('...') in pikepdf.Array`.");
                    }
                    return array_has_item(h, objecthandle_encode(key));
                }
                try {
                    return object_has_key(h, string_from_key(key));
                } catch (py::type_error &) {
                    return false;
                }
            })
        .def("as_list", &QPDFObjectHandle::getArrayAsVector)
        .def("as_dict", &QPDFObjectHandle::getDictAsMap)
        .def(
            "__iter__",
            [](QPDFObjectHandle h) -> py::iterable {
                if (h.isArray()) {
                    auto vec = h.getArrayAsVector();
                    auto pyvec = py::cast(vec);
                    return pyvec.attr("__iter__")();
                } else if (h.isDictionary() || h.isStream()) {
                    if (h.isStream())
                        h = h.getDict();

                    // Manually build safe list to iterate over
                    auto keys = h.getKeys();
                    py::list result;
                    for (auto const &k : keys) {
                        result.append(safe_decode(k));
                    }
                    return result.attr("__iter__")();
                } else {
                    throw py::type_error("__iter__ not available on this type");
                }
            },
            py::return_value_policy::reference_internal)
        .def(
            "items",
            [](QPDFObjectHandle h) -> py::iterable {
                if (h.isStream())
                    h = h.getDict();
                if (!h.isDictionary())
                    throw py::type_error("items() not available on this type");

                // Manually build dict to ensure keys are safely decoded
                auto dict_map = h.getDictAsMap();
                py::dict pydict;
                for (auto const &item : dict_map) {
                    // item.first is std::string (key), item.second is QPDFObjectHandle
                    // (value)
                    pydict[safe_decode(item.first)] = py::cast(item.second);
                }
                return pydict.attr("items")();
            },
            py::return_value_policy::reference_internal)
        .def("__str__",
            [](QPDFObjectHandle &h) -> py::str {
                if (h.isName())
                    return h.getName();
                else if (h.isOperator())
                    return h.getOperatorValue();
                else if (h.isString())
                    return h.getUTF8Value();
                // Python's default __str__ calls __repr__
                return objecthandle_repr(h);
            })
        .def("__bytes__",
            [](QPDFObjectHandle &h) {
                if (h.isName())
                    return py::bytes(h.getName());
                if (h.isStream()) {
                    auto buf = h.getStreamData();
                    // py::bytes will make a copy of the buffer, so releasing is fine
                    return py::bytes((const char *)buf->getBuffer(), buf->getSize());
                }
                if (h.isOperator()) {
                    return py::bytes(h.getOperatorValue());
                }
                return py::bytes(h.getStringValue());
            })
        .def("__setitem__",
            [](QPDFObjectHandle &h, int index, QPDFObjectHandle &value) {
                auto u_index = list_range_check(h, index);
                h.setArrayItem(u_index, value);
            })
        .def("__setitem__",
            [](QPDFObjectHandle &h, int index, py::object pyvalue) {
                auto u_index = list_range_check(h, index);
                auto value = objecthandle_encode(pyvalue);
                h.setArrayItem(u_index, value);
            })
        .def("__setitem__",
            [](QPDFObjectHandle &h, py::object key, py::object val) {
                if (py::isinstance<py::slice>(key)) {
                    ensure_array(h, "set slice");
                    if (!py::isinstance<py::iterable>(val)) {
                        throw py::type_error("can only assign an iterable");
                    }
                    Py_ssize_t start, stop, step, slicelength;
                    if (!py::reinterpret_borrow<py::slice>(key).compute(
                            h.getArrayNItems(), &start, &stop, &step, &slicelength))
                        throw py::error_already_set();

                    std::vector<QPDFObjectHandle> new_vals;
                    py::iterable it = py::reinterpret_borrow<py::iterable>(val);
                    try {
                        new_vals.reserve(py::len(val));
                    } catch (...) {
                        // Some iterables (generators) don't support len(), which is
                        // fine
                    }
                    for (auto const &item : py::cast<py::iterable>(val)) {
                        new_vals.push_back(objecthandle_encode(
                            py::reinterpret_borrow<py::object>(item)));
                    }

                    if (step != 1) {
                        if (static_cast<Py_ssize_t>(new_vals.size()) != slicelength) {
                            // Match the expected test regex exactly:
                            throw py::value_error(
                                "attempt to assign sequence of size " +
                                std::to_string(new_vals.size()) +
                                " to extended slice of size " +
                                std::to_string(slicelength));
                        }
                        for (Py_ssize_t i = 0; i < slicelength; ++i) {
                            h.setArrayItem(
                                static_cast<int>(start + i * step), new_vals[i]);
                        }
                    } else {
                        for (Py_ssize_t i = 0; i < slicelength; ++i)
                            h.eraseItem(static_cast<int>(start));
                        int insert_at = static_cast<int>(start);
                        for (auto const &new_obj : new_vals) {
                            h.insertItem(insert_at++, new_obj);
                        }
                    }
                } else if (py::isinstance<py::int_>(key)) {
                    ensure_array(h, "set index");
                    int index = key.cast<int>();
                    int n = h.getArrayNItems();
                    if (index < 0)
                        index += n;
                    if (index < 0 || index >= n)
                        throw py::index_error("array index out of range");

                    h.setArrayItem(index, objecthandle_encode(val));
                } else {
                    std::string k =
                        string_from_key(key); // Validates '/' prefix, throws KeyError
                    auto encoded_val =
                        objecthandle_encode(val); // Handles None, throws ValueError
                    object_set_key(
                        h, k, encoded_val); // Validates Dictionary/Stream type
                }
            })
        .def("wrap_in_array", [](QPDFObjectHandle &h) { return h.wrapInArray(); })
        .def("append",
            [](QPDFObjectHandle &h, py::object pyitem) {
                auto item = objecthandle_encode(pyitem);
                return h.appendItem(item);
            })
        .def("extend",
            [](QPDFObjectHandle &h, py::iterable iter) {
                for (auto item : iter) {
                    h.appendItem(objecthandle_encode(item));
                }
            })
        .def_property_readonly("is_rectangle",
            &QPDFObjectHandle::isRectangle // LCOV_EXCL_LINE
            )
        .def(
            "get_stream_buffer",
            [](QPDFObjectHandle &h, qpdf_stream_decode_level_e decode_level) {
                return get_stream_data(h, decode_level);
            },
            py::arg("decode_level") = qpdf_dl_generalized)
        .def("get_raw_stream_buffer",
            [](QPDFObjectHandle &h) { return h.getRawStreamData(); })
        .def(
            "read_bytes",
            [](QPDFObjectHandle &h, qpdf_stream_decode_level_e decode_level) {
                auto buf = get_stream_data(h, decode_level);
                return py::bytes((const char *)buf->getBuffer(), buf->getSize());
            },
            py::arg("decode_level") = qpdf_dl_generalized)
        .def("read_raw_bytes",
            [](QPDFObjectHandle &h) {
                auto buf = h.getRawStreamData();
                // py::bytes will make a copy of the buffer, so releasing is fine
                return py::bytes((const char *)buf->getBuffer(), buf->getSize());
            })
        .def(
            "_write",
            [](QPDFObjectHandle &h,
                py::bytes data,
                py::object filter,
                py::object decode_parms) {
                std::string sdata = data;
                QPDFObjectHandle h_filter = objecthandle_encode(filter);
                QPDFObjectHandle h_decode_parms = objecthandle_encode(decode_parms);
                h.replaceStreamData(sdata, h_filter, h_decode_parms);
            },
            py::arg("data"),
            py::arg("filter"),
            py::arg("decode_parms"))
        .def("_inline_image_raw_bytes",
            [](QPDFObjectHandle &h) { return py::bytes(h.getInlineImageValue()); })
        .def_property_readonly("_objgen", &object_get_objgen)
        .def_property_readonly("objgen", &object_get_objgen)
        .def_static(
            "parse",
            [](py::bytes stream, py::str description) {
                return QPDFObjectHandle::parse(
                    std::string(stream), std::string(description));
            },
            py::arg("stream"),
            py::arg("description") = "")
        .def("_parse_page_contents",
            &QPDFObjectHandle::parsePageContents,
            "Helper for parsing page contents; use ``pikepdf.parse_content_stream``.")
        .def("_parse_page_contents_grouped",
            [](QPDFObjectHandle &h, std::string const &whitelist) {
                OperandGrouper og(whitelist);
                h.parsePageContents(&og);
                return og.getInstructions();
            })
        .def_static("_parse_stream",
            &QPDFObjectHandle::parseContentStream, // LCOV_EXCL_LINE
            "Helper for parsing PDF content stream; use "
            "``pikepdf.parse_content_stream``.")
        .def_static("_parse_stream_grouped",
            [](QPDFObjectHandle &h, std::string const &whitelist) {
                OperandGrouper og(whitelist);
                QPDFObjectHandle::parseContentStream(h, &og);
                if (!og.getWarning().empty()) {
                    python_warning(og.getWarning().c_str());
                }
                return og.getInstructions();
            })
        .def(
            "_get_unique_resource_name",
            [](QPDFObjectHandle &h, std::string const &prefix, int min_suffix) {
                auto name = h.getUniqueResourceName(prefix, min_suffix);
                return std::pair(name, min_suffix);
            },
            py::arg("prefix") = "",
            py::arg("min_suffix") = 0)
        .def("_get_resource_names",
            [](QPDFObjectHandle &h) { return h.getResourceNames(); })
        .def(
            "unparse",
            [](QPDFObjectHandle &h, bool resolved) -> py::bytes {
                if (resolved)
                    return h.unparseResolved();
                return h.unparse();
            },
            py::arg("resolved") = false)
        .def(
            "to_json",
            [](QPDFObjectHandle &h,
                bool dereference = false,
                int schema_version = 2) -> py::bytes {
                std::string result;
                Pl_String p("json", nullptr, result);
                h.writeJSON(schema_version, &p, dereference);
                return result;
            },
            py::arg("dereference") = false,
            py::arg("schema_version") = 2); // end of QPDFObjectHandle bindings

    m.def("_new_boolean", &QPDFObjectHandle::newBool);
    m.def("_new_integer", &QPDFObjectHandle::newInteger);
    m.def("_new_real",
        [](const std::string &value) { return QPDFObjectHandle::newReal(value); });
    m.def(
        "_new_real",
        [](double value, uint places) {
            return QPDFObjectHandle::newReal(value, places);
        },
        py::arg("value"),
        py::arg("places") = 0);
    m.def("_new_name", [](const std::string &s) {
        if (s.length() < 2)
            throw py::value_error("Name must be at least one character long");
        if (s.at(0) != '/')
            throw py::value_error("Name objects must begin with '/'");
        return QPDFObjectHandle::newName(s);
    });
    m.def("_new_string",
        [](const std::string &s) { return QPDFObjectHandle::newString(s); });
    m.def("_new_string_utf8", [](const std::string &utf8) {
        return QPDFObjectHandle::newUnicodeString(utf8);
    });
    m.def("_new_array", [](py::iterable iterable) {
        return QPDFObjectHandle::newArray(array_builder(iterable));
    });
    m.def("_new_dictionary", [](py::dict dict) {
        return QPDFObjectHandle::newDictionary(dict_builder(dict));
    });
    m.def("_new_stream", [](QPDF &owner, py::bytes data) {
        // This makes a copy of the data
        return QPDFObjectHandle::newStream(&owner, data);
    });
    m.def(
        "_new_operator",
        [](const std::string &op) { return QPDFObjectHandle::newOperator(op); },
        py::arg("op"));
    m.def("_Null", &QPDFObjectHandle::newNull, "Construct a PDF Null object");

    py::class_<QPDFObjectHandle::ParserCallbacks, py::smart_holder, PyParserCallbacks>(
        m, "StreamParser")
        .def(py::init<>(), "You must call ``super.__init__()`` in subclasses.")
        // LCOV_EXCL_START
        // coverage misses the virtual function call ::handleObject here.
        .def("handle_object",
            [](QPDFObjectHandle::ParserCallbacks &parsercallbacks,
                QPDFObjectHandle &h,
                size_t offset,
                size_t length) { parsercallbacks.handleObject(h, offset, length); })
        // LCOV_EXCL_STOP
        .def("handle_eof", &QPDFObjectHandle::ParserCallbacks::handleEOF);

    // Since QPDFEmbeddedFileDocumentHelper::getEmbeddedFiles returns
    // std::map<std::string, std::shared_ptr<QPDFFileSpecObjectHelper>>
    // we must use smart_holder.
    py::class_<QPDFObjectHelper, py::smart_holder>(m, "ObjectHelper")
        .def(
            "__eq__",
            [](QPDFObjectHelper &self, QPDFObjectHelper &other) {
                // Object helpers are equal if their object handles are equal
                return objecthandle_equal(
                    self.getObjectHandle(), other.getObjectHandle());
            },
            py::is_operator())
        .def_property_readonly("obj", [](QPDFObjectHelper &poh) -> QPDFObjectHandle {
            return poh.getObjectHandle();
        });

    m.def("_encode", [](py::handle handle) { return objecthandle_encode(handle); });
    m.def("unparse", [](py::object obj) -> py::bytes {
        return objecthandle_encode(obj).unparseBinary();
    });
} // init_object
