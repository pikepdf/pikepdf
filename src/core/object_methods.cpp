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

#include <cctype>
#include <cmath>
#include <cstring>

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
                QpdfLockGuard lock(h.getOwningQPDF());
                auto u_index = list_range_check(h, index);
                h.eraseItem(u_index);
            })
        .def("__delitem__",
            [](QPDFObjectHandle &h, QPDFObjectHandle &name) {
                object_del_key(h, name.getName());
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
        .def_prop_rw("stream_dict",
            &QPDFObjectHandle::getDict,
            &QPDFObjectHandle::replaceDict,
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
        .def("as_list", &QPDFObjectHandle::getArrayAsVector)
        .def("as_dict", &QPDFObjectHandle::getDictAsMap)
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
                h.setArrayItem(u_index, value);
            })
        .def(
            "__setitem__",
            [](QPDFObjectHandle &h, int index, py::object pyvalue) {
                auto u_index = list_range_check(h, index);
                auto value = objecthandle_encode(pyvalue);
                h.setArrayItem(u_index, value);
            },
            py::arg("index"),
            py::arg("value").none())
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
                return h.appendItem(item);
            },
            py::arg("pyitem").none())
        .def("extend",
            [](QPDFObjectHandle &h, py::iterable iter) {
                QpdfLockGuard lock(h.getOwningQPDF());
                for (auto item : iter) {
                    h.appendItem(objecthandle_encode(item));
                }
            })
        .def(
            "clear",
            [](QPDFObjectHandle &h) {
                QpdfLockGuard lock(h.getOwningQPDF());
                ensure_array(h, "clear");
                for (int i = h.getArrayNItems() - 1; i >= 0; --i)
                    h.eraseItem(i);
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
                h.insertItem(index, objecthandle_encode(value));
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
                        h.eraseItem(i);
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
