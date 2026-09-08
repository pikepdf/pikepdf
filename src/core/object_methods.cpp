// SPDX-FileCopyrightText: 2022 James R. Barlow
// SPDX-License-Identifier: MPL-2.0

// Second half of the QPDFObjectHandle ("Object") binding, split out of
// object.cpp so each translation unit's nanobind template instantiation uses
// less peak compiler memory (see the x86_64 CI build notes in pyproject.toml).

#include "pikepdf.h"
#include "qpdf_lock.h"
#include "utils.h"

#include "namepath.h"
#include "parsers.h"

#include <algorithm>
#include <cctype>
#include <cerrno>
#include <charconv>
#include <cmath>
#include <cstdlib>
#include <cstring>
#include <optional>
#include <string>
#include <system_error>
#include <vector>

#include "numeric-inl.h"
#include "object.h"
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

// Convert QPDF Dictionary/Stream to temporary Python dict, or throw
static py::dict pydict_from_object(QPDFObjectHandle h, const char *method_name)
{
    QpdfLockGuard lock(h.getOwningQPDF());
    if (h.isStream())
        h = h.getDict();

    if (!h.isDictionary()) {
        std::string msg = std::string(method_name) + "() not available on this type";
        throw py::type_error(msg.c_str());
    }

    auto dict_map = h.getDictAsMap();
    py::dict pydict;
    for (auto const &item : dict_map) {
        pydict[safe_decode(item.first)] = py::cast(item.second);
    }
    return pydict;
}

// as_int()/as_bool()/as_decimal() insist on an exact PDF type, so that a value
// the caller believes is one type is never silently read as another, unless
// the caller opts in with coerce=True.
[[noreturn]] static void raise_overflow()
{
    PyErr_SetString(
        PyExc_OverflowError, "value is out of range for a 64-bit PDF integer");
    throw py::python_error();
}

// Parse the whole string as an integer. Returns nullopt if the text is not an
// integer at all; raises OverflowError if it is an integer that does not fit.
static std::optional<long long> parse_ll(std::string const &s)
{
    char const *begin = s.data();
    char const *end = s.data() + s.size();
    if (begin != end && *begin == '+')
        ++begin; // std::from_chars does not accept a leading '+'
    if (begin == end)
        return std::nullopt;
    long long value = 0;
    auto result = std::from_chars(begin, end, value);
    if (result.ec == std::errc::result_out_of_range)
        raise_overflow();
    if (result.ec != std::errc() || result.ptr != end)
        return std::nullopt;
    return value;
}

// Truncate toward zero, raising OverflowError rather than invoking undefined
// behaviour when the value does not fit in long long.
static long long double_to_ll_trunc(double value)
{
    double t = std::trunc(value);
    // -2^63 is exactly representable; 2^63 is the first double above the range.
    if (!(t >= -9223372036854775808.0) || !(t < 9223372036854775808.0))
        raise_overflow();
    return static_cast<long long>(t);
}

static std::optional<long long> try_as_int(QPDFObjectHandle &h, bool coerce)
{
    if (h.isInteger())
        return h.getIntValue();
    if (!coerce)
        return std::nullopt;
    if (h.isReal()) {
        auto value = real_as_double(h);
        if (!value)
            return std::nullopt;
        return double_to_ll_trunc(*value);
    }
    if (h.isString()) {
        auto text = trimmed(h.getUTF8Value());
        // Integer text is converted exactly; anything else goes through double.
        if (auto exact = parse_ll(text))
            return *exact;
        auto value = parse_double(text);
        if (!value)
            return std::nullopt;
        return double_to_ll_trunc(*value);
    }
    return std::nullopt;
}

static std::optional<bool> try_as_bool(QPDFObjectHandle &h, bool coerce)
{
    if (h.isBool())
        return h.getBoolValue();
    if (!coerce)
        return std::nullopt;
    if (h.isInteger())
        return h.getIntValue() != 0;
    if (h.isReal()) {
        auto value = real_as_double(h);
        if (!value)
            return std::nullopt;
        return *value != 0.0;
    }
    return std::nullopt;
}

static std::optional<double> try_as_double(QPDFObjectHandle &h, bool coerce)
{
    if (h.isInteger())
        return static_cast<double>(h.getIntValue());
    if (h.isReal())
        return real_as_double(h);
    if (!coerce)
        return std::nullopt;
    if (h.isString())
        return parse_double(trimmed(h.getUTF8Value()));
    return std::nullopt;
}

static std::optional<py::object> try_as_decimal(QPDFObjectHandle &h, bool coerce)
{
    if (h.isReal()) {
        // Validate the token text the same way try_as_double() does, so that a
        // Real holding "nan"/"inf" cannot become Decimal('NaN')/Decimal('Infinity').
        if (!real_as_double(h))
            return std::nullopt;
        return decimal_from_pdfobject(h);
    }
    if (!coerce)
        return std::nullopt;
    if (h.isInteger())
        return decimal_from_pdfobject(h);
    if (h.isString()) {
        auto text = trimmed(h.getUTF8Value());
        // Validate as a double so that Decimal('Infinity') and Decimal('NaN')
        // cannot be constructed, but build from the text to keep every digit.
        if (!parse_double(text))
            return std::nullopt;
        auto Decimal = py::module_::import_("decimal").attr("Decimal");
        return py::object(Decimal(py::cast(text)));
    }
    return std::nullopt;
}

[[noreturn]] static void raise_expected(QPDFObjectHandle &h, char const *expected)
{
    throw py::type_error(
        (std::string("Expected ") + expected + ", got " + h.getTypeName()).c_str());
}

// Resolve a NamePath to the container that holds its last component, along
// with that component. The caller decides what to do with the component
// (set, delete, ...); *action* names the operation in the empty-path error.
static std::pair<QPDFObjectHandle, PathComponent> namepath_parent_and_last(
    QPDFObjectHandle &h, NamePath const &path, char const *action)
{
    if (path.empty()) {
        throw py::value_error(
            (std::string("Cannot ") + action + " empty NamePath").c_str());
    }
    return {traverse_namepath(h, path, true), path.components().back()};
}

void init_object_methods(py::class_<QPDFObjectHandle> &object)
{
    object
        .def("__getitem__",
            [](QPDFObjectHandle &h, int index) {
                QpdfLockGuard lock(h.getOwningQPDF());
                auto u_index = list_range_check(h, index);
                return h.getArrayItem(u_index);
            })
        .def("__getitem__",
            [](QPDFObjectHandle &h, QPDFObjectHandle &name) {
                QpdfLockGuard lock(h.getOwningQPDF());
                return object_get_key(h, name.getName());
            })
        .def("__getitem__",
            [](QPDFObjectHandle &h, NamePath const &path) {
                QpdfLockGuard lock(h.getOwningQPDF());
                if (path.empty()) {
                    return h; // Empty path returns self
                }
                return traverse_namepath(h, path);
            })
        .def("__getitem__",
            [](QPDFObjectHandle &h, py::slice slice) {
                QpdfLockGuard lock(h.getOwningQPDF());
                ensure_array(h, "slice");
                auto [start, stop, step, slicelength] =
                    slice.compute(h.getArrayNItems());
                std::vector<QPDFObjectHandle> items;
                items.reserve(slicelength);
                Py_ssize_t idx = start;
                for (size_t i = 0; i < slicelength; ++i) {
                    items.push_back(h.getArrayItem(static_cast<int>(idx)));
                    idx += step;
                }
                return QPDFObjectHandle::newArray(items);
            })
        .def("__getitem__",
            [](QPDFObjectHandle &h, py::object key) -> QPDFObjectHandle {
                QpdfLockGuard lock(h.getOwningQPDF());
                std::string k = string_from_key(key);
                return object_get_key(h, k);
            })
        .def("__setitem__",
            [](QPDFObjectHandle &h, QPDFObjectHandle &name, QPDFObjectHandle &value) {
                object_set_key(h, name.getName(), value);
            })
        .def(
            "__setitem__",
            [](QPDFObjectHandle &h, QPDFObjectHandle &name, py::object pyvalue) {
                auto value = objecthandle_encode(pyvalue);
                object_set_key(h, name.getName(), value);
            },
            py::arg("name"),
            py::arg("value").none())
        .def(
            "copy",
            [](QPDFObjectHandle &h) {
                if (!h.isDictionary() && !h.isStream() && !h.isArray()) {
                    throw py::type_error(
                        (std::string(
                             "pikepdf.Object is not an Array, Dictionary or Stream: ") +
                            "cannot copy an object of type " + h.getTypeName())
                            .c_str());
                }
                return copy_object(h);
            },
            "Create a shallow copy of the object.")
        .def(
            "update",
            [](QPDFObjectHandle &h, py::dict other) {
                // object_set_key handles the check if 'h' is a dictionary
                for (auto item : other) {
                    std::string key = py::cast<std::string>(py::str(item.first));
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
                for (auto &[key, val] : other.ditems())
                    object_set_key(h, key, val);
            },
            "Update the dictionary with key/value pairs from another pikepdf "
            "Dictionary.")
        .def("__setitem__",
            [](QPDFObjectHandle &h, NamePath const &path, QPDFObjectHandle &value) {
                auto [parent, last] = namepath_parent_and_last(h, path, "assign to");
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
                    auto old_value = parent.getArrayItem(index);
                    auto adopted = adopt_into(live_owner(parent), value);
                    parent.setArrayItem(static_cast<size_t>(index), adopted);
                    if (!old_value.isSameObjectAs(adopted))
                        disconnect_detached(parent, old_value);
                }
            })
        .def("__setitem__",
            [](QPDFObjectHandle &h, NamePath const &path, py::object pyvalue) {
                auto value = objecthandle_encode(pyvalue);
                auto [parent, last] = namepath_parent_and_last(h, path, "assign to");
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
                    auto old_value = parent.getArrayItem(index);
                    auto adopted = adopt_into(live_owner(parent), value);
                    parent.setArrayItem(static_cast<size_t>(index), adopted);
                    if (!old_value.isSameObjectAs(adopted))
                        disconnect_detached(parent, old_value);
                }
            })
        .def("__delitem__",
            [](QPDFObjectHandle &h, NamePath const &path) {
                QpdfLockGuard lock(h.getOwningQPDF());
                auto [parent, last] = namepath_parent_and_last(h, path, "delete");
                if (std::holds_alternative<std::string>(last)) {
                    object_del_key(parent, std::get<std::string>(last));
                } else {
                    auto u_index = list_range_check(parent, std::get<int>(last));
                    auto old_value = parent.getArrayItem(static_cast<int>(u_index));
                    parent.eraseItem(u_index);
                    disconnect_detached(parent, old_value);
                }
            })
        .def("__delitem__",
            [](QPDFObjectHandle &h, int index) {
                QpdfLockGuard lock(h.getOwningQPDF());
                auto u_index = list_range_check(h, index);
                auto old_value = h.getArrayItem(static_cast<int>(u_index));
                h.eraseItem(u_index);
                disconnect_detached(h, old_value);
            })
        .def("__delitem__",
            [](QPDFObjectHandle &h, QPDFObjectHandle &name) {
                object_del_key(h, name.getName());
            })
        .def("__delitem__",
            [](QPDFObjectHandle &h, py::slice slice) {
                QpdfLockGuard lock(h.getOwningQPDF());
                ensure_array(h, "delete slice");
                auto [start, stop, step, slicelength] =
                    slice.compute(h.getArrayNItems());
                std::vector<int> indices;
                indices.reserve(slicelength);
                Py_ssize_t idx = start;
                for (size_t i = 0; i < slicelength; ++i) {
                    indices.push_back(static_cast<int>(idx));
                    idx += step;
                }
                // Delete from highest index to lowest so earlier indices
                // remain valid as items are erased.
                std::sort(indices.begin(), indices.end(), std::greater<int>());
                std::vector<QPDFObjectHandle> removed;
                removed.reserve(indices.size());
                for (int i : indices) {
                    removed.push_back(h.getArrayItem(i));
                    h.eraseItem(i);
                }
                for (auto &old_value : removed)
                    disconnect_detached(h, old_value);
            })
        .def("__delitem__",
            [](QPDFObjectHandle &h, py::object key) {
                std::string k = string_from_key(key);
                object_del_key(h, k);
            })
        .def("__getattr__",
            [](QPDFObjectHandle &h, std::string const &name) {
                QpdfLockGuard lock(h.getOwningQPDF());
                QPDFObjectHandle value;
                std::string key = "/" + name;
                try {
                    value = object_get_key(h, key);
                } catch (const py::builtin_exception &e) {
                    if (e.type() == py::exception_type::key_error) {
                        if (std::isupper(name[0]))
                            throw py::attribute_error(e.what());
                        else
                            throw py::attribute_error(name.c_str());
                    } else if (e.type() == py::exception_type::value_error) {
                        if (name == std::string("__name__"))
                            throw py::attribute_error(name.c_str());
                        throw; // LCOV_EXCL_LINE
                    } else {
                        throw; // LCOV_EXCL_LINE
                    }
                }
                return value;
            })
        .def_prop_rw(
            "stream_dict",
            &QPDFObjectHandle::getDict,
            [](QPDFObjectHandle &h, QPDFObjectHandle &dict) {
                QpdfLockGuard lock(h.getOwningQPDF());
                // Adopt the dictionary's children but not the dictionary
                // itself: qpdf labels a stream dictionary through
                // QPDF_Stream::setDictDescription, which only acts on a
                // dictionary that has no description of its own.
                adopt_children_into(live_owner(h), dict);
                h.replaceDict(dict);
            },
            py::rv_policy::reference_internal)
        .def(
            "__setattr__",
            [](QPDFObjectHandle &h, std::string const &name, py::object pyvalue) {
                QpdfLockGuard lock(h.getOwningQPDF());
                if (h.isDictionary() || (h.isStream() && name != "stream_dict")) {
                    // Map attribute assignment to setting dictionary key
                    std::string key = "/" + name;
                    auto value = objecthandle_encode(pyvalue);
                    object_set_key(h, key, value);
                    return;
                }

                // If we don't have a special rule, do object.__setattr__()
                py::object baseobj = py::module_::import_("builtins").attr("object");
                baseobj.attr("__setattr__")(
                    py::cast(h), py::str(name.c_str()), pyvalue);
            },
            py::arg("name"),
            py::arg("value").none())
        .def("__delattr__",
            [](QPDFObjectHandle &h, std::string const &name) {
                QpdfLockGuard lock(h.getOwningQPDF());
                std::string key = "/" + name;
                object_del_key(h, key);
            })
        .def("__dir__",
            [](QPDFObjectHandle &h) {
                QpdfLockGuard lock(h.getOwningQPDF());
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
                        result.append(py::str(s.c_str()));
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
                } catch (const py::builtin_exception &) {
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
                } catch (const py::builtin_exception &) {
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
                } catch (const py::builtin_exception &) {
                    return default_;
                }
            },
            py::arg("path"),
            py::arg("default") = py::none())
        .def(
            "get_raw",
            [](QPDFObjectHandle &h, std::string const &key, py::object default_) {
                QPDFObjectHandle value;
                try {
                    value = object_get_key(h, key);
                } catch (const py::builtin_exception &) {
                    return default_;
                }
                return cast_raw(value);
            },
            py::arg("key"),
            py::arg("default") = py::none(),
            R"~~~(Retrieve a value without implicit conversion of scalars.

            Like :meth:`get`, except the result is always a
            :class:`pikepdf.Object`, regardless of the conversion mode in
            effect.

            A null stored inside an *array* comes back as a ``Null``-typed
            Object rather than ``None``. In a *dictionary*, qpdf treats a key
            whose value is null as absent, so ``get_raw`` returns the default
            for it, exactly as :meth:`get` does; ``None`` (or *default*) is
            likewise returned when the key or path does not exist at all.

            *key* may be a string, a :class:`pikepdf.Name`, or a
            :class:`pikepdf.NamePath`.

            .. versionadded:: 10.14
            )~~~")
        .def(
            "get_raw",
            [](QPDFObjectHandle &h, QPDFObjectHandle &name, py::object default_) {
                QPDFObjectHandle value;
                try {
                    value = object_get_key(h, name.getName());
                } catch (const py::builtin_exception &) {
                    return default_;
                }
                return cast_raw(value);
            },
            py::arg("key"),
            py::arg("default") = py::none())
        .def(
            "get_raw",
            [](QPDFObjectHandle &h, NamePath const &path, py::object default_) {
                if (path.empty()) {
                    return cast_raw(h);
                }
                try {
                    return cast_raw(traverse_namepath(h, path));
                } catch (const py::builtin_exception &) {
                    return default_;
                }
            },
            py::arg("path"),
            py::arg("default") = py::none())
        .def("keys",
            [](QPDFObjectHandle &h) {
                QpdfLockGuard lock(h.getOwningQPDF());
                std::set<std::string> keys =
                    h.isStream() ? h.getDict().getKeys() : h.getKeys();
                py::set result;
                for (auto const &k : keys) {
                    result.add(safe_decode(k));
                }
                return result;
            })
        .def("__contains__",
            [](QPDFObjectHandle &h, NamePath const &path) {
                QpdfLockGuard lock(h.getOwningQPDF());
                if (path.empty())
                    return true; // The object always contains itself
                try {
                    traverse_namepath(h, path);
                    return true;
                } catch (py::builtin_exception &e) {
                    auto type = e.type();
                    if (type == py::exception_type::key_error ||
                        type == py::exception_type::index_error ||
                        type == py::exception_type::type_error)
                        return false;
                    throw; // LCOV_EXCL_LINE
                }
            })
        .def("__contains__",
            [](QPDFObjectHandle &h, QPDFObjectHandle &key) {
                QpdfLockGuard lock(h.getOwningQPDF());
                if (h.isArray()) {
                    return array_has_item(h, key);
                }
                if (!key.isName())
                    throw py::type_error("Dictionaries can only contain Names");
                return object_has_key(h, key.getName());
            })
        .def(
            "__contains__",
            [](QPDFObjectHandle &h, py::object key) {
                QpdfLockGuard lock(h.getOwningQPDF());
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
                } catch (py::builtin_exception &e) {
                    if (e.type() == py::exception_type::type_error)
                        return false;
                    throw;
                }
            },
            py::arg("key").none())
        .def(
            "as_list",
            [](QPDFObjectHandle &h) {
                QpdfLockGuard lock(h.getOwningQPDF());
                if (!h.isArray())
                    raise_expected(h, "array");
                return py::cast(h.getArrayAsVector());
            },
            R"(Return the array's items, or return default if not an array.

Args:
    default: Value to return if this object is not an array. If not
        provided and the object is not an array, raises TypeError.

Raises:
    TypeError: If object is not an array and no default was provided.

.. versionchanged:: 10.14
    Previously this raised an unhelpful error on non-arrays. It now raises
    :exc:`TypeError`, and accepts a *default*.
)")
        .def(
            "as_list",
            [](QPDFObjectHandle &h, py::handle default_) -> py::object {
                QpdfLockGuard lock(h.getOwningQPDF());
                if (!h.isArray())
                    return py::borrow<py::object>(default_);
                return py::cast(h.getArrayAsVector());
            },
            py::arg("default").none())
        .def(
            "as_dict",
            [](QPDFObjectHandle &h) {
                QpdfLockGuard lock(h.getOwningQPDF());
                if (!h.isDictionary())
                    raise_expected(h, "dictionary");
                return py::cast(h.getDictAsMap());
            },
            R"(Return the dictionary's items, or return default if not a dictionary.

For a :class:`pikepdf.Stream`, use :attr:`pikepdf.Object.stream_dict` to
obtain its dictionary; a Stream is not a dictionary here.

Args:
    default: Value to return if this object is not a dictionary. If not
        provided and the object is not a dictionary, raises TypeError.

Raises:
    TypeError: If object is not a dictionary and no default was provided.

.. versionchanged:: 10.14
    Previously this raised an unhelpful error on non-dictionaries, and
    accepted a Stream. It now raises :exc:`TypeError`, and accepts a
    *default*.
)")
        .def(
            "as_dict",
            [](QPDFObjectHandle &h, py::handle default_) -> py::object {
                QpdfLockGuard lock(h.getOwningQPDF());
                if (!h.isDictionary())
                    return py::borrow<py::object>(default_);
                return py::cast(h.getDictAsMap());
            },
            py::arg("default").none())
        .def(
            "as_int",
            [](QPDFObjectHandle &h, bool coerce) -> long long {
                auto value = try_as_int(h, coerce);
                if (!value)
                    raise_expected(h, "integer");
                return *value;
            },
            py::kw_only(),
            py::arg("coerce") = false,
            R"(Convert to int, or return default if not an integer.

In explicit conversion mode, this provides a safe way to convert
pikepdf.Integer to Python int with proper type hints.

Args:
    default: Value to return if this object is not an integer.
        If not provided and the object is not an integer,
        raises TypeError.
    coerce: If True, also accept a Real (truncated toward zero) and a
        String whose text is a number.

Returns:
    The integer value, or the default if provided and object is
    not an integer.

Raises:
    TypeError: If object is not an integer and no default was provided.
    OverflowError: If the value is out of range for a 64-bit integer and
        no default was provided. If a default was provided, it is
        returned instead.

.. versionadded:: 10.1

.. versionchanged:: 10.14
    Added the keyword-only *coerce* argument.

.. versionchanged:: 10.14
    A value out of range for a 64-bit integer now returns *default*, if
    one was given, instead of raising OverflowError.
)")
        .def(
            "as_int",
            [](QPDFObjectHandle &h, py::handle default_, bool coerce) -> py::object {
                std::optional<long long> value;
                try {
                    value = try_as_int(h, coerce);
                } catch (py::python_error &e) {
                    // A value out of range for a 64-bit PDF integer is a value
                    // the caller cannot use, so a supplied default answers the
                    // question just as well as it does for a type mismatch.
                    // The no-default overload still raises OverflowError.
                    if (!e.matches(PyExc_OverflowError))
                        throw;
                    e.restore();
                    PyErr_Clear();
                    return py::borrow<py::object>(default_);
                }
                if (!value)
                    return py::borrow<py::object>(default_);
                return py::cast(*value);
            },
            py::arg("default").none(),
            py::kw_only(),
            py::arg("coerce") = false)
        .def(
            "as_bool",
            [](QPDFObjectHandle &h, bool coerce) -> bool {
                auto value = try_as_bool(h, coerce);
                if (!value)
                    raise_expected(h, "boolean");
                return *value;
            },
            py::kw_only(),
            py::arg("coerce") = false,
            R"(Convert to bool, or return default if not a boolean.

In explicit conversion mode, this provides a safe way to convert
pikepdf.Boolean to Python bool with proper type hints.

Args:
    default: Value to return if this object is not a boolean.
        If not provided and the object is not a boolean,
        raises TypeError.
    coerce: If True, also accept an Integer or Real, which are True when
        nonzero.

Returns:
    The boolean value, or the default if provided and object is
    not a boolean.

Raises:
    TypeError: If object is not a boolean and no default was provided.

.. versionadded:: 10.1

.. versionchanged:: 10.14
    Added the keyword-only *coerce* argument.
)")
        .def(
            "as_bool",
            [](QPDFObjectHandle &h, py::handle default_, bool coerce) -> py::object {
                auto value = try_as_bool(h, coerce);
                if (!value)
                    return py::borrow<py::object>(default_);
                return py::cast(*value);
            },
            py::arg("default").none(),
            py::kw_only(),
            py::arg("coerce") = false)
        .def(
            "as_float",
            [](QPDFObjectHandle &h, bool coerce) -> double {
                auto value = try_as_double(h, coerce);
                if (!value)
                    raise_expected(h, "numeric");
                return *value;
            },
            py::kw_only(),
            py::arg("coerce") = false,
            R"(Convert to float, or return default if not numeric.

Works for both Integer and Real objects.

Args:
    default: Value to return if this object is not numeric.
        If not provided and the object is not numeric,
        raises TypeError.
    coerce: If True, also accept a String whose text is a number,
        including exponential notation such as ``1e-5``.

Returns:
    The float value, or the default if provided and object is
    not numeric.

Raises:
    TypeError: If object is not numeric and no default was provided.

.. versionadded:: 10.1

.. versionchanged:: 10.14
    Added the keyword-only *coerce* argument.
)")
        .def(
            "as_float",
            [](QPDFObjectHandle &h, py::handle default_, bool coerce) -> py::object {
                auto value = try_as_double(h, coerce);
                if (!value)
                    return py::borrow<py::object>(default_);
                return py::cast(*value);
            },
            py::arg("default").none(),
            py::kw_only(),
            py::arg("coerce") = false)
        .def(
            "as_decimal",
            [](QPDFObjectHandle &h, bool coerce) -> py::object {
                auto value = try_as_decimal(h, coerce);
                if (!value)
                    raise_expected(h, "real");
                return *value;
            },
            py::kw_only(),
            py::arg("coerce") = false,
            R"(Convert to Decimal, or return default if not a Real.

Preferred over as_float() for PDF reals to preserve precision.
Only works for Real objects, not Integer.

Args:
    default: Value to return if this object is not a Real.
        If not provided and the object is not a Real,
        raises TypeError.
    coerce: If True, also accept an Integer and a String whose text is a
        number. The Decimal is built from the string as written, so all
        of its digits are preserved.

Returns:
    The Decimal value, or the default if provided and object is
    not a Real.

Raises:
    TypeError: If object is not a Real and no default was provided.

.. versionadded:: 10.1

.. versionchanged:: 10.14
    Added the keyword-only *coerce* argument.
)")
        .def(
            "as_decimal",
            [](QPDFObjectHandle &h, py::handle default_, bool coerce) -> py::object {
                auto value = try_as_decimal(h, coerce);
                if (!value)
                    return py::borrow<py::object>(default_);
                return *value;
            },
            py::arg("default").none(),
            py::kw_only(),
            py::arg("coerce") = false)
        .def("_ipython_key_completions_",
            [](QPDFObjectHandle &h) -> py::object {
                if (!h.isDictionary() && !h.isStream())
                    return py::none();
                return py::cast(h).attr("keys")();
            })
        .def(
            "__iter__",
            [](QPDFObjectHandle h) -> py::object {
                QpdfLockGuard lock(h.getOwningQPDF());
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
            py::rv_policy::reference_internal)
        .def(
            "items",
            [](QPDFObjectHandle h) {
                return pydict_from_object(h, "items").attr("items")();
            },
            py::rv_policy::reference_internal)
        .def(
            "values",
            [](QPDFObjectHandle h) {
                return pydict_from_object(h, "values").attr("values")();
            },
            py::rv_policy::reference_internal)
        .def("__str__",
            [](QPDFObjectHandle &h) -> py::str {
                QpdfLockGuard lock(h.getOwningQPDF());
                std::string s;
                if (h.isName())
                    s = h.getName();
                else if (h.isOperator())
                    s = h.getOperatorValue();
                else if (h.isString())
                    s = h.getUTF8Value();
                else if (h.isInteger())
                    s = std::to_string(h.getIntValue());
                else if (h.isBool())
                    // Match str() of the Python bool this becomes in implicit mode
                    s = h.getBoolValue() ? "True" : "False";
                else if (h.isReal())
                    // The stored decimal string, trailing zeros and all, which is
                    // what str() of the equivalent Decimal produces
                    s = h.getRealValue();
                else
                    // Python's default __str__ calls __repr__
                    s = objecthandle_repr(h);
                return py::steal<py::str>(
                    PyUnicode_FromStringAndSize(s.data(), s.size()));
            })
        .def("__bytes__",
            [](QPDFObjectHandle &h) {
                QpdfLockGuard lock(h.getOwningQPDF());
                if (h.isName()) {
                    auto v = h.getName();
                    return py::bytes(v.data(), v.size());
                }
                if (h.isStream()) {
                    auto buf = h.getStreamData();
                    // py::bytes will make a copy of the buffer, so releasing is fine
                    return py::bytes((const char *)buf->getBuffer(), buf->getSize());
                }
                if (h.isOperator()) {
                    auto v = h.getOperatorValue();
                    return py::bytes(v.data(), v.size());
                }
                auto v = h.getStringValue();
                return py::bytes(v.data(), v.size());
            })
        .def("__setitem__",
            [](QPDFObjectHandle &h, int index, QPDFObjectHandle &value) {
                auto u_index = list_range_check(h, index);
                auto old_value = h.getArrayItem(static_cast<int>(u_index));
                auto adopted = adopt_into(live_owner(h), value);
                h.setArrayItem(u_index, adopted);
                if (!old_value.isSameObjectAs(adopted))
                    disconnect_detached(h, old_value);
            })
        .def(
            "__setitem__",
            [](QPDFObjectHandle &h, int index, py::object pyvalue) {
                auto u_index = list_range_check(h, index);
                auto value = objecthandle_encode(pyvalue);
                auto old_value = h.getArrayItem(static_cast<int>(u_index));
                auto adopted = adopt_into(live_owner(h), value);
                h.setArrayItem(u_index, adopted);
                if (!old_value.isSameObjectAs(adopted))
                    disconnect_detached(h, old_value);
            },
            py::arg("index"),
            py::arg("value").none())
        .def(
            "__setitem__",
            [](QPDFObjectHandle &h, py::slice slice, py::object val) {
                QpdfLockGuard lock(h.getOwningQPDF());
                ensure_array(h, "set slice");

                // Validate iterability and obtain an iterator. Typing the
                // value as py::object (not py::iterable) lets us emit the
                // list-compatible message for non-iterables like int.
                PyObject *iter_raw = PyObject_GetIter(val.ptr());
                if (!iter_raw) {
                    PyErr_Clear();
                    throw py::type_error("can only assign an iterable");
                }
                py::object iterator = py::steal(iter_raw);

                auto [start, stop, step, slicelength] =
                    slice.compute(h.getArrayNItems());

                std::vector<QPDFObjectHandle> new_vals;
                PyObject *item;
                while ((item = PyIter_Next(iterator.ptr())) != nullptr) {
                    py::object o = py::steal(item);
                    new_vals.push_back(objecthandle_encode(o));
                }
                if (PyErr_Occurred())
                    throw py::python_error();

                std::vector<QPDFObjectHandle> replaced;
                if (step != 1) {
                    if (new_vals.size() != slicelength)
                        throw py::value_error(("attempt to assign sequence of size " +
                                               std::to_string(new_vals.size()) +
                                               " to extended slice of size " +
                                               std::to_string(slicelength))
                                .c_str());
                    Py_ssize_t idx = start;
                    for (size_t i = 0; i < new_vals.size(); ++i) {
                        replaced.push_back(h.getArrayItem(static_cast<int>(idx)));
                        h.setArrayItem(static_cast<int>(idx),
                            adopt_into(live_owner(h), new_vals[i]));
                        idx += step;
                    }
                } else {
                    for (size_t i = 0; i < slicelength; ++i) {
                        replaced.push_back(h.getArrayItem(static_cast<int>(start)));
                        h.eraseItem(static_cast<int>(start));
                    }
                    int insert_at = static_cast<int>(start);
                    for (auto const &obj : new_vals)
                        h.insertItem(insert_at++, adopt_into(live_owner(h), obj));
                }
                // Values pushed out of the array lose their claim on the
                // document, unless the same object was assigned back in.
                for (auto &old_value : replaced) {
                    bool reinserted = false;
                    for (auto const &obj : new_vals) {
                        if (old_value.isSameObjectAs(obj)) {
                            reinserted = true;
                            break;
                        }
                    }
                    if (!reinserted)
                        disconnect_detached(h, old_value);
                }
            },
            py::arg("slice"),
            py::arg("value"))
        .def(
            "__setitem__",
            [](QPDFObjectHandle &h, py::object key, py::object pyvalue) {
                std::string k = string_from_key(key);
                auto value = objecthandle_encode(pyvalue);
                object_set_key(h, k, value);
            },
            py::arg("key"),
            py::arg("value").none())
        .def("wrap_in_array", [](QPDFObjectHandle &h) { return h.wrapInArray(); })
        .def(
            "append",
            [](QPDFObjectHandle &h, py::object pyitem) {
                QpdfLockGuard lock(h.getOwningQPDF());
                auto item = objecthandle_encode(pyitem);
                return h.appendItem(adopt_into(live_owner(h), item));
            },
            py::arg("pyitem").none())
        .def("extend",
            [](QPDFObjectHandle &h, py::iterable iter) {
                QpdfLockGuard lock(h.getOwningQPDF());
                for (auto item : iter) {
                    auto value = objecthandle_encode(item);
                    h.appendItem(adopt_into(live_owner(h), value));
                }
            })
        .def(
            "clear",
            [](QPDFObjectHandle &h) {
                QpdfLockGuard lock(h.getOwningQPDF());
                ensure_array(h, "clear");
                std::vector<QPDFObjectHandle> removed;
                for (int i = h.getArrayNItems() - 1; i >= 0; --i) {
                    removed.push_back(h.getArrayItem(i));
                    h.eraseItem(i);
                }
                for (auto &old_value : removed)
                    disconnect_detached(h, old_value);
            },
            "Remove all items from the array.")
        .def(
            "reverse",
            [](QPDFObjectHandle &h) {
                QpdfLockGuard lock(h.getOwningQPDF());
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
            "insert",
            [](QPDFObjectHandle &h, int index, py::object value) {
                QpdfLockGuard lock(h.getOwningQPDF());
                ensure_array(h, "insert");
                int nitems = h.getArrayNItems();
                if (index < 0)
                    index += nitems;
                if (index < 0)
                    index = 0;
                if (index > nitems)
                    index = nitems;
                auto item = objecthandle_encode(value);
                h.insertItem(index, adopt_into(live_owner(h), item));
            },
            py::arg("index"),
            py::arg("value").none(),
            "Insert an object before the given index (Python list.insert semantics).")
        .def(
            "pop",
            [](QPDFObjectHandle &h, int index) {
                QpdfLockGuard lock(h.getOwningQPDF());
                ensure_array(h, "pop");
                auto u_index = list_range_check(h, index);
                auto item = h.getArrayItem(static_cast<int>(u_index));
                h.eraseItem(static_cast<int>(u_index));
                disconnect_detached(h, item);
                return item;
            },
            py::arg("index") = -1,
            "Remove and return the item at *index* (default last).")
        .def(
            "remove",
            [](QPDFObjectHandle &h, py::object value) {
                QpdfLockGuard lock(h.getOwningQPDF());
                ensure_array(h, "remove");
                auto needle = objecthandle_encode(value);
                int n = h.getArrayNItems();
                for (int i = 0; i < n; ++i) {
                    if (objecthandle_equal(h.getArrayItem(i), needle)) {
                        auto old_value = h.getArrayItem(i);
                        h.eraseItem(i);
                        disconnect_detached(h, old_value);
                        return;
                    }
                }
                throw py::value_error("item not in array");
            },
            py::arg("value"),
            "Remove the first item equal to *value*.")
        .def(
            "index",
            [](QPDFObjectHandle &h, py::object value) {
                QpdfLockGuard lock(h.getOwningQPDF());
                ensure_array(h, "index");
                auto needle = objecthandle_encode(value);
                int n = h.getArrayNItems();
                for (int i = 0; i < n; ++i) {
                    if (objecthandle_equal(h.getArrayItem(i), needle))
                        return i;
                }
                throw py::value_error("item not in array");
            },
            py::arg("value"),
            "Return the index of the first item equal to *value*.")
        .def(
            "count",
            [](QPDFObjectHandle &h, py::object value) {
                QpdfLockGuard lock(h.getOwningQPDF());
                ensure_array(h, "count");
                auto needle = objecthandle_encode(value);
                int count = 0;
                for (auto const &item : h.aitems()) {
                    if (objecthandle_equal(item, needle))
                        ++count;
                }
                return count;
            },
            py::arg("value"),
            "Return the number of items equal to *value*.")
        .def_prop_ro("is_rectangle",
            &QPDFObjectHandle::isRectangle // LCOV_EXCL_LINE
            )
        .def(
            "get_stream_buffer",
            [](QPDFObjectHandle &h, qpdf_stream_decode_level_e decode_level) {
                return get_stream_data(h, decode_level);
            },
            py::arg("decode_level") = qpdf_dl_generalized)
        .def("get_raw_stream_buffer",
            [](QPDFObjectHandle &h) {
                QpdfLockGuard lock(h.getOwningQPDF());
                return h.getRawStreamData();
            })
        .def(
            "read_bytes",
            [](QPDFObjectHandle &h, qpdf_stream_decode_level_e decode_level) {
                auto buf = get_stream_data(h, decode_level);
                return py::bytes((const char *)buf->getBuffer(), buf->getSize());
            },
            py::arg("decode_level") = qpdf_dl_generalized)
        .def("read_raw_bytes",
            [](QPDFObjectHandle &h) {
                QpdfLockGuard lock(h.getOwningQPDF());
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
                QpdfLockGuard lock(h.getOwningQPDF());
                std::string sdata = to_string(data);
                QPDFObjectHandle h_filter = objecthandle_encode(filter);
                QPDFObjectHandle h_decode_parms = objecthandle_encode(decode_parms);
                h.replaceStreamData(sdata, h_filter, h_decode_parms);
            },
            py::arg("data"),
            py::arg("filter").none(),
            py::arg("decode_parms").none())
        .def("_inline_image_raw_bytes",
            [](QPDFObjectHandle &h) {
                auto v = h.getInlineImageValue();
                return py::bytes(v.data(), v.size());
            })
        .def_prop_ro("_objgen", &object_get_objgen)
        .def_prop_ro("objgen", &object_get_objgen)
        .def_static(
            "parse",
            [](py::bytes stream, py::str description) {
                return QPDFObjectHandle::parse(
                    to_string(stream), py::cast<std::string>(description));
            },
            py::arg("stream"),
            py::arg("description") = "")
        .def("_parse_page_contents_grouped",
            [](QPDFObjectHandle &h, std::string const &whitelist) {
                OperandGrouper og(whitelist, h.getKey("/Resources"));
                h.parsePageContents(&og);
                return og.getInstructions();
            })
        .def_static("_parse_stream",
            &QPDFObjectHandle::parseContentStream, // LCOV_EXCL_LINE
            "Helper for parsing PDF content stream; use "
            "``pikepdf.parse_content_stream``.")
        .def_static("_parse_stream_grouped",
            [](QPDFObjectHandle &h, std::string const &whitelist) {
                // A content stream (e.g. a Form XObject) may carry its own
                // /Resources, used to resolve inline images' named colour spaces.
                QPDFObjectHandle resources;
                if (h.isStream())
                    resources = h.getDict().getKey("/Resources");
                OperandGrouper og(whitelist, resources);
                QPDFObjectHandle::parseContentStream(h, &og);
                // LCOV_EXCL_START - warning path depends on qpdf internals
                if (!og.getWarning().empty()) {
                    python_warning(og.getWarning().c_str());
                }
                // LCOV_EXCL_STOP
                return og.getInstructions();
            })
        .def(
            "_get_unique_resource_name",
            [](QPDFObjectHandle &h, std::string const &prefix, int min_suffix) {
                auto name = h.getUniqueResourceName(prefix, min_suffix);
                return std::pair(name, min_suffix);
            },
            py::arg("prefix") = "", // LCOV_EXCL_LINE
            py::arg("min_suffix") = 0)
        .def("_get_resource_names",
            [](QPDFObjectHandle &h) { return h.getResourceNames(); })
        .def(
            "unparse",
            [](QPDFObjectHandle &h, bool resolved) -> py::bytes {
                QpdfLockGuard lock(h.getOwningQPDF());
                auto s = resolved ? h.unparseResolved() : h.unparse();
                return py::bytes(s.data(), s.size());
            },
            py::arg("resolved") = false)
        .def(
            "to_json",
            [](QPDFObjectHandle &h,
                bool dereference = false,
                int schema_version = 2) -> py::bytes {
                QpdfLockGuard lock(h.getOwningQPDF());
                std::string result;
                Pl_String p("json", nullptr, result);
                h.writeJSON(schema_version, &p, dereference);
                return py::bytes(result.data(), result.size());
            },
            py::arg("dereference") = false,
            py::arg("schema_version") = 2); // end of QPDFObjectHandle bindings
}
