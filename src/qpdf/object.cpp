/*
 * This Source Code Form is subject to the terms of the Mozilla Public
 * License, v. 2.0. If a copy of the MPL was not distributed with this
 * file, You can obtain one at http://mozilla.org/MPL/2.0/.
 *
 * Copyright (C) 2017, James R. Barlow (https://github.com/jbarlow83/)
 */

#include <cctype>

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

#include "object_parsers.h"

/*
Type table

See objects.rst. In short and with technical details:

These QPDF types are directly mapped to a native Python equivalent. The C++
object is never returned to Python; a Python object is returned instead.
Adding one of these to a QPDF container type causes the appropriate conversion.
    Boolean <-> bool
    Integer <-> int
    Real <-> Decimal
    Real <- float
    Null <-> None

PDF semantics dictate that setting a dictionary key to Null deletes the key.

    d['/Key'] = None  # would delete /Key

For Python users appears to have an unxpected side effect, so this action is
prohibited. You cannot set keys to None.

pikepdf.String is a "type" that can be converted with str() or bytes() as
needed.

*/


size_t list_range_check(QPDFObjectHandle h, int index)
{
    if (!h.isArray())
        throw py::value_error("object is not an array");
    if (index < 0)
        index += h.getArrayNItems(); // Support negative indexing
    if (!(0 <= index && index < h.getArrayNItems()))
        throw py::index_error("index out of range");
    return (size_t)index;
}


bool objecthandle_equal(QPDFObjectHandle self, QPDFObjectHandle other)
{
    StackGuard sg(" objecthandle_equal");

    // Uninitialized objects are never equal
    if (!self.isInitialized() || !other.isInitialized())
        return false;

    // Indirect objects (objid != 0) with the same obj-gen are equal and same owner
    // are equal (in fact, they are identical; they reference the same underlying
    // QPDFObject, even if the handles are different).
    // This lets us compare deeply nested and cyclic structures without recursing
    // into them.
    if (self.getObjectID() != 0
        && other.getObjectID() != 0
        && self.getOwningQPDF() == other.getOwningQPDF()) {
        return self.getObjGen() == other.getObjGen();
    }

    // If 'self' is a numeric type, convert both to Decimal objects
    // and compare them as such.
    if (self.getTypeCode() == QPDFObject::object_type_e::ot_integer ||
        self.getTypeCode() == QPDFObject::object_type_e::ot_real ||
        self.getTypeCode() == QPDFObject::object_type_e::ot_boolean) {
        try {
            auto a = decimal_from_pdfobject(self);
            auto b = decimal_from_pdfobject(other);
            py::object pyresult = a.attr("__eq__")(b);
            bool result = pyresult.cast<bool>();
            return result;
        } catch (const py::type_error&) {
            return false;
        }
    }

    // Apart from numeric types, disimilar types are never equal
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
        {
            // We don't know what encoding the string is in
            // This ensures UTF-16 coded ASCII strings will compare equal to
            // UTF-8/ASCII coded.
            return self.getStringValue() == other.getStringValue() ||
                self.getUTF8Value() == other.getUTF8Value();
        }
        case QPDFObject::object_type_e::ot_array:
        {
            // Call operator==() on each element of the arrays, meaning this
            // recurses into this function
            return (self.getArrayAsVector() == other.getArrayAsVector());
        }
        case QPDFObject::object_type_e::ot_dictionary:
        {
            // Call operator==() on each element of the arrays, meaning this
            // recurses into this function
            return (self.getDictAsMap() == other.getDictAsMap());
        }
        default:
            break;
    }
    return false;
}


bool operator==(QPDFObjectHandle self, QPDFObjectHandle other)
{
    // A lot of functions in QPDFObjectHandle are not tagged const where they
    // should be, but are const-safe
    return objecthandle_equal(self, other);
}


bool object_has_key(QPDFObjectHandle h, std::string const& key)
{
    if (!h.isDictionary() && !h.isStream())
        throw py::value_error("object is not a dictionary or a stream");
    QPDFObjectHandle dict = h.isStream() ? h.getDict() : h;
    return dict.hasKey(key);
}


QPDFObjectHandle object_get_key(QPDFObjectHandle h, std::string const& key)
{
    if (!h.isDictionary() && !h.isStream())
        throw py::value_error("object is not a dictionary or a stream");
    QPDFObjectHandle dict = h.isStream() ? h.getDict() : h;
    if (!dict.hasKey(key))
        throw py::key_error(key);
    return dict.getKey(key);
}

void object_set_key(QPDFObjectHandle h, std::string const& key, QPDFObjectHandle& value)
{
    if (!h.isDictionary() && !h.isStream())
        throw py::value_error("object is not a dictionary or a stream");
    if (value.isNull())
        throw py::value_error("PDF Dictionary keys may not be set to None - use 'del' to remove");
    if (h.isStream() && key == "/Length") {
        PyErr_WarnEx(PyExc_DeprecationWarning,
            "Modifications to /Length have no effect and will be forbidden in a future release.",
            0
        );
    }

    // For streams, the actual dictionary is attached to stream object
    QPDFObjectHandle dict = h.isStream() ? h.getDict() : h;

    // A stream dictionary has no owner, so use the stream object in this comparison
    dict.replaceKey(key, value);
}

void object_del_key(QPDFObjectHandle h, std::string const& key)
{
    if (!h.isDictionary() && !h.isStream())
        throw py::value_error("object is not a dictionary or a stream");
    if (h.isStream() && key == "/Length") {
        PyErr_WarnEx(PyExc_DeprecationWarning,
            "Deleting /Length has no effect and will be forbidden in a future release.",
            0
        );
    }

    // For streams, the actual dictionary is attached to stream object
    QPDFObjectHandle dict = h.isStream() ? h.getDict() : h;

    if (!dict.hasKey(key))
        throw py::key_error(key);

    dict.removeKey(key);
}

std::pair<int, int> object_get_objgen(QPDFObjectHandle h)
{
    auto objgen = h.getObjGen();
    return std::pair<int, int>(objgen.getObj(), objgen.getGen());
}


void init_object(py::module& m)
{
    py::enum_<QPDFObject::object_type_e>(m, "ObjectType")
        .value("uninitialized", QPDFObject::object_type_e::ot_uninitialized)
        .value("reserved", QPDFObject::object_type_e::ot_reserved)
        .value("null", QPDFObject::object_type_e::ot_null)
        .value("boolean", QPDFObject::object_type_e::ot_boolean)
        .value("integer", QPDFObject::object_type_e::ot_integer)
        .value("real", QPDFObject::object_type_e::ot_real)
        .value("string", QPDFObject::object_type_e::ot_string)
        .value("name", QPDFObject::object_type_e::ot_name)
        .value("array", QPDFObject::object_type_e::ot_array)
        .value("dictionary", QPDFObject::object_type_e::ot_dictionary)
        .value("stream", QPDFObject::object_type_e::ot_stream)
        .value("operator", QPDFObject::object_type_e::ot_operator)
        .value("inlineimage", QPDFObject::object_type_e::ot_inlineimage);


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

    py::bind_vector<std::vector<QPDFObjectHandle>>(m, "_ObjectList");
    py::bind_map<std::map<std::string, QPDFObjectHandle>>(m, "_ObjectMapping");

    py::class_<QPDFObjectHandle>(m, "Object")
        .def_property_readonly("_type_code", &QPDFObjectHandle::getTypeCode)
        .def_property_readonly("_type_name", &QPDFObjectHandle::getTypeName)
        .def("is_owned_by",
            [](QPDFObjectHandle &h, std::shared_ptr<QPDF> possible_owner) {
                return (h.getOwningQPDF() == possible_owner.get());
            },
            "Test if this object is owned by the indicated *possible_owner*.",
            py::arg("possible_owner")
        )
        .def("same_owner_as",
            [](QPDFObjectHandle &self, QPDFObjectHandle &other) {
                return self.getOwningQPDF() == other.getOwningQPDF();
            },
            "Test if two objects are owned by the same :class:`pikepdf.Pdf`."
        )
        .def_property_readonly("is_indirect", &QPDFObjectHandle::isIndirect)
        .def("__repr__", &objecthandle_repr)
        .def("__hash__",
            [](QPDFObjectHandle &self) -> py::int_ {
                py::object hash = py::module::import("builtins").attr("hash");

                //Objects which compare equal must have the same hash value
                switch (self.getTypeCode()) {
                    case QPDFObject::object_type_e::ot_string:
                    {
                        return hash(py::bytes(self.getUTF8Value()));
                    }
                    case QPDFObject::object_type_e::ot_name:
                        return hash(py::bytes(self.getName()));
                    case QPDFObject::object_type_e::ot_operator:
                        return hash(py::bytes(self.getOperatorValue()));
                    case QPDFObject::object_type_e::ot_array:
                    case QPDFObject::object_type_e::ot_dictionary:
                    case QPDFObject::object_type_e::ot_stream:
                    case QPDFObject::object_type_e::ot_inlineimage:
                        throw py::type_error("Can't hash mutable object");
                    default:
                        break;
                }
                throw std::logic_error("don't know how to hash this");
            }
        )
        .def("__eq__",
            [](QPDFObjectHandle &self, QPDFObjectHandle &other) {
                return (self == other); // overloaded
            }
        )
        .def("__eq__",
            [](QPDFObjectHandle &self, py::str other) {
                std::string utf8_other = other.cast<std::string>();
                switch (self.getTypeCode()) {
                    case QPDFObject::object_type_e::ot_string:
                        return self.getUTF8Value() == utf8_other;
                    case QPDFObject::object_type_e::ot_name:
                        return self.getName() == utf8_other;
                    default:
                        return false;
                }
            }
        )
        .def("__eq__",
            [](QPDFObjectHandle &self, py::object other) -> py::object {
                QPDFObjectHandle q_other;
                try {
                    q_other = objecthandle_encode(other);
                } catch (const py::cast_error&) {
                    return py::globals()["__builtins__"]["NotImplemented"];
                }
                bool result = (self == objecthandle_encode(other));
                return py::bool_(result);
            }
        )
        .def("__copy__",
            [](QPDFObjectHandle &h) {
                return h.shallowCopy();
            }
        )
        .def("__len__",
            [](QPDFObjectHandle &h) {
                if (h.isDictionary())
                    return (Py_ssize_t)h.getDictAsMap().size(); // getKeys constructs a new object, so this is better
                else if (h.isArray())
                    return (Py_ssize_t)h.getArrayNItems();
                if (h.isStream())
                    throw py::type_error(
                        "length not defined for object - "
                        "use len(obj.keys()) for number of dictionary keys, "
                        "or len(bytes(obj)) for length of stream data"
                    );
                throw py::type_error("length not defined for object");
            }
        )
        .def("__getitem__",
            [](QPDFObjectHandle &h, std::string const& key) {
                return object_get_key(h, key);
            }
        )
        .def("__getitem__",
            [](QPDFObjectHandle &h, QPDFObjectHandle &name) {
                return object_get_key(h, name.getName());
            }
        )
        .def("__setitem__",
            [](QPDFObjectHandle &h, std::string const& key, QPDFObjectHandle &value) {
                object_set_key(h, key, value);
            },
            "assign dictionary key to new object",
            py::keep_alive<1, 3>()
        )
        .def("__setitem__",
            [](QPDFObjectHandle &h, QPDFObjectHandle &name, QPDFObjectHandle &value) {
                object_set_key(h, name.getName(), value);
            },
            "assign dictionary key to new object",
            py::keep_alive<1, 3>()
        )
        .def("__setitem__",
            [](QPDFObjectHandle &h, std::string const& key, py::object pyvalue) {
                auto value = objecthandle_encode(pyvalue);
                object_set_key(h, key, value);
            }
        )
        .def("__setitem__",
            [](QPDFObjectHandle &h, QPDFObjectHandle &name, py::object pyvalue) {
                auto value = objecthandle_encode(pyvalue);
                object_set_key(h, name.getName(), value);
            }
        )
        .def("__delitem__",
            [](QPDFObjectHandle &h, std::string const& key) {
                object_del_key(h, key);
            },
            "delete a dictionary key"
        )
        .def("__delitem__",
            [](QPDFObjectHandle &h, QPDFObjectHandle &name) {
                object_del_key(h, name.getName());
            },
            "delete a dictionary key"
        )
        .def("__getattr__",
            [](QPDFObjectHandle &h, std::string const& name) {
                QPDFObjectHandle value;
                std::string key = "/" + name;
                try {
                    value = object_get_key(h, key);
                } catch (const py::key_error &e) {
                    if (std::isupper(name[0]))
                        throw py::attr_error(e.what());
                    else
                        throw py::attr_error(name);
                } catch (const py::value_error &e) {
                    if (name == std::string("__name__"))
                        throw py::attr_error(name);
                    throw;
                }
                return value;
            },
            "attribute lookup name"
        )
        .def_property("stream_dict",
            &QPDFObjectHandle::getDict, &QPDFObjectHandle::replaceDict,
            "Access the dictionary key-values for a :class:`pikepdf.Stream`.",
            py::return_value_policy::reference_internal
        )
        .def("__setattr__",
            [](QPDFObjectHandle &h, std::string const& name, py::object pyvalue) {
                std::string key = "/" + name;
                auto value = objecthandle_encode(pyvalue);
                object_set_key(h, key, value);
            },
            "attribute access"
        )
        .def("__delattr__",
            [](QPDFObjectHandle &h, std::string const& name) {
                std::string key = "/" + name;
                object_del_key(h, key);
            }
        )
        .def("__dir__",
            [](QPDFObjectHandle &h) {
                py::list result;
                py::object obj = py::cast(h);
                py::object class_keys = obj.attr("__class__").attr("__dict__").attr("keys")();
                for (auto attr: class_keys) {
                    result.append(attr);
                }
                if (h.isDictionary() || h.isStream()) {
                    for (auto key_attr: h.getKeys()) {
                        std::string s = key_attr.substr(1);
                        result.append(py::str(s));
                    }
                }
                return result;
            }
        )
        .def("get",
            [](QPDFObjectHandle &h, std::string const& key, py::object default_) {
                QPDFObjectHandle value;
                try {
                    value = object_get_key(h, key);
                } catch (const py::key_error&) {
                    return default_;
                }
                return py::cast(value);
            },
            "For ``pikepdf.Dictionary`` or ``pikepdf.Stream`` objects, behave as ``dict.get(key, default=None)``",
            py::arg("key"),
            py::arg("default") = py::none(),
            py::return_value_policy::reference_internal
        )
        .def("get",
            [](QPDFObjectHandle &h, QPDFObjectHandle &name, py::object default_) {
                QPDFObjectHandle value;
                try {
                    value = object_get_key(h, name.getName());
                } catch (const py::key_error&) {
                    return default_;
                }
                return py::cast(value);
            },
            "For ``pikepdf.Dictionary`` or ``pikepdf.Stream`` objects, behave as ``dict.get(key, default=None)``",
            py::arg("key"),
            py::arg("default") = py::none(),
            py::return_value_policy::reference_internal
        )
        .def("keys",
            [](QPDFObjectHandle h) {
                if (h.isStream())
                    h = h.getDict();
                return h.getKeys();
            },
            "For ``pikepdf.Dictionary`` or ``pikepdf.Stream`` objects, obtain the keys."
        )
        .def("__contains__",
            [](QPDFObjectHandle &h, QPDFObjectHandle &key) {
                if (!key.isName())
                    throw py::type_error("Dictionaries can only contain Names");
                return object_has_key(h, key.getName());
            }
        )
        .def("__contains__",
            [](QPDFObjectHandle &h, std::string const& key) {
                return object_has_key(h, key);
            }
        )
        .def("as_list", &QPDFObjectHandle::getArrayAsVector)
        .def("as_dict", &QPDFObjectHandle::getDictAsMap)
        .def("__iter__",
            [](QPDFObjectHandle h) -> py::iterable {
                if (h.isArray()) {
                    auto vec = h.getArrayAsVector();
                    auto pyvec = py::cast(vec);
                    return pyvec.attr("__iter__")();
                } else if (h.isDictionary() || h.isStream()) {
                    if (h.isStream())
                        h = h.getDict();
                    auto keys = h.getKeys();
                    auto pykeys = py::cast(keys);
                    return pykeys.attr("__iter__")();
                } else {
                    throw py::type_error("__iter__ not available on this type");
                }
            },
            py::return_value_policy::reference_internal
        )
        .def("items",
            [](QPDFObjectHandle h) -> py::iterable {
                if (h.isStream())
                    h = h.getDict();
                if (!h.isDictionary())
                    throw py::type_error("items() not available on this type");
                auto dict = h.getDictAsMap();
                auto pydict = py::cast(dict);
                return pydict.attr("items")();
            },
            py::return_value_policy::reference_internal
        )
        .def("__str__",
            [](QPDFObjectHandle &h) -> py::str {
                if (h.isName())
                    return h.getName();
                else if (h.isOperator())
                    return h.getOperatorValue();
                else if (h.isString())
                    return h.getUTF8Value();
                throw py::notimpl_error("don't know how to __str__ this object");
            }
        )
        .def("__bytes__",
            [](QPDFObjectHandle &h) {
                if (h.isName())
                    return py::bytes(h.getName());
                if (h.isStream()) {
                    PointerHolder<Buffer> buf = h.getStreamData();
                    // py::bytes will make a copy of the buffer, so releasing is fine
                    return py::bytes((const char*)buf->getBuffer(), buf->getSize());
                }
                return py::bytes(h.getStringValue());
            }
        )
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
            [](QPDFObjectHandle &h, int index, py::object pyvalue) {
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
        .def("wrap_in_array",
            [](QPDFObjectHandle &h) {
                return h.wrapInArray();
            },
            "Return the object wrapped in an array if not already an array."
        )
        .def("append",
            [](QPDFObjectHandle &h, py::object pyitem) {
                auto item = objecthandle_encode(pyitem);
                return h.appendItem(item);
            },
            "Append another object to an array; fails if the object is not an array."
        )
        .def("extend",
            [](QPDFObjectHandle &h, py::iterable iter) {
                for (auto item: iter) {
                    h.appendItem(objecthandle_encode(item));
                }
            },
            "Extend a pikepdf.Array with an iterable of other objects."
        )
        .def_property_readonly("is_rectangle", &QPDFObjectHandle::isRectangle,
            "Returns True if the object is a rectangle (an array of 4 numbers)"
        )
        .def("get_stream_buffer",
            [](QPDFObjectHandle &h, qpdf_stream_decode_level_e decode_level) {
                PointerHolder<Buffer> phbuf = h.getStreamData(decode_level);
                return phbuf;
            },
            "Return a buffer protocol buffer describing the decoded stream.",
            py::arg("decode_level") = qpdf_dl_generalized
        )
        .def("get_raw_stream_buffer",
            [](QPDFObjectHandle &h) {
                PointerHolder<Buffer> phbuf = h.getRawStreamData();
                return phbuf;
            },
            "Return a buffer protocol buffer describing the raw, encoded stream"
        )
        .def("read_bytes",
            [](QPDFObjectHandle &h, qpdf_stream_decode_level_e decode_level) {
                PointerHolder<Buffer> buf = h.getStreamData(decode_level);
                // py::bytes will make a copy of the buffer, so releasing is fine
                return py::bytes((const char*)buf->getBuffer(), buf->getSize());
            },
            "Decode and read the content stream associated with this object.",
            py::arg("decode_level") = qpdf_dl_generalized
        )
        .def("read_raw_bytes",
            [](QPDFObjectHandle &h) {
                PointerHolder<Buffer> buf = h.getRawStreamData();
                // py::bytes will make a copy of the buffer, so releasing is fine
                return py::bytes((const char*)buf->getBuffer(), buf->getSize());
            },
            "Read the content stream associated with this object without decoding"
        )
        .def("_write",
            [](QPDFObjectHandle &h, py::bytes data, py::object filter, py::object decode_parms) {
                std::string sdata = data;
                QPDFObjectHandle h_filter = objecthandle_encode(filter);
                QPDFObjectHandle h_decode_parms = objecthandle_encode(decode_parms);
                h.replaceStreamData(sdata, h_filter, h_decode_parms);
            },
            R"~~~(
            Low level write/replace stream data without argument checking. Use .write().
            )~~~",
            py::arg("data"), py::arg("filter"), py::arg("decode_parms")
        )
        .def_property_readonly("images",
            [](QPDFObjectHandle &h) {
                if (!h.isPageObject())
                    throw py::type_error("Not a Page");
                return h.getPageImages();
            }
        )
        .def("_inline_image_raw_bytes",
            [](QPDFObjectHandle &h) {
                return py::bytes(h.getInlineImageValue());
            }
        )
        .def("page_contents_add",
            [](QPDFObjectHandle &h, QPDFObjectHandle &contents, bool prepend) {
                if (!h.isPageObject())
                    throw py::type_error("Not a Page");
                h.addPageContents(contents, prepend);
            },
            "Append or prepend to an existing page's content stream.",
            py::arg("contents"),
            py::arg("prepend") = false,
            py::keep_alive<1, 2>()
        )
        .def("page_contents_coalesce", &QPDFObjectHandle::coalesceContentStreams,
            R"~~~(
            Coalesce an array of page content streams into a single content stream.

            The PDF specification allows the ``/Contents`` object to contain either
            an array of content streams or a single content stream. However, it
            simplifies parsing and editing if there is only a single content stream.
            This function merges all content streams.
            )~~~"
        )
        .def_property_readonly("_objgen",
            &object_get_objgen
        )
        .def_property_readonly("objgen",
            &object_get_objgen,
            R"~~~(
            Return the object-generation number pair for this object.

            If this is a direct object, then the returned value is ``(0, 0)``.
            By definition, if this is an indirect object, it has a "objgen",
            and can be looked up using this in the cross-reference (xref) table.
            Direct objects cannot necessarily be looked up.

            The generation number is usually 0, except for PDFs that have been
            incrementally updated. Incrementally updated PDFs are now uncommon,
            since it does not take too long for modern CPUs to reconstruct an
            entire PDF. pikepdf will consolidate all incremental updates
            when saving.

            )~~~"
        )
        .def_static("parse",
            [](std::string const& stream, std::string const& description) {
                return QPDFObjectHandle::parse(stream, description);
            },
            "Parse PDF binary representation into PDF objects.",
            py::arg("stream"),
            py::arg("description") = ""
        )
        .def("_parse_page_contents",
            &QPDFObjectHandle::parsePageContents,
            "Helper for parsing page contents; use ``pikepdf.parse_content_stream``."
        )
        .def("_parse_page_contents_grouped",
            [](QPDFObjectHandle &h, std::string const& whitelist) {
                OperandGrouper og(whitelist);
                h.parsePageContents(&og);
                return og.getInstructions();
            }
        )
        .def_static("_parse_stream",
            &QPDFObjectHandle::parseContentStream,
            "Helper for parsing PDF content stream; use ``pikepdf.parse_content_stream``."
        )
        .def_static("_parse_stream_grouped",
            [](QPDFObjectHandle &h, std::string const& whitelist) {
                OperandGrouper og(whitelist);
                QPDFObjectHandle::parseContentStream(h, &og);
                if (!og.getWarning().empty()) {
                    auto warn = py::module::import("warnings").attr("warn");
                    warn(og.getWarning());
                }
                return og.getInstructions();
            }
        )
        .def("unparse",
            [](QPDFObjectHandle &h, bool resolved) -> py::bytes {
                if (resolved)
                    return h.unparseResolved();
                return h.unparse();
            },
            py::arg("resolved") = false,
            "Convert PDF objects into their binary representation, optionally resolving indirect objects."
        )
        .def("to_json",
            [](QPDFObjectHandle &h, bool dereference = false) -> py::bytes {
                return h.getJSON(dereference).unparse();
            },
            py::arg("dereference") = false,
            R"~~~(
            Convert to a QPDF JSON representation of the object.

            See the QPDF manual for a description of its JSON representation.
            http://qpdf.sourceforge.net/files/qpdf-manual.html#ref.json

            Not necessarily compatible with other PDF-JSON representations that
            exist in the wild.

            * Names are encoded as UTF-8 strings
            * Indirect references are encoded as strings containing ``obj gen R``
            * Strings are encoded as UTF-8 strings with unrepresentable binary
              characters encoded as ``\uHHHH``
            * Encoding streams just encodes the stream's dictionary; the stream
              data is not represented
            * Object types that are only valid in content streams (inline
              image, operator) as well as "reserved" objects are not
              representable and will be serialized as ``null``.

            Args:
                dereference (bool): If True, dereference the object is this is an
                    indirect object.

            Returns:
                bytes: JSON bytestring of object. The object is UTF-8 encoded
                and may be decoded to a Python str that represents the binary
                values ``\x00-\xFF`` as ``U+0000`` to ``U+00FF``; that is,
                it may contain mojibake.
            )~~~"
        )
        ; // end of QPDFObjectHandle bindings

    m.def("_new_boolean", &QPDFObjectHandle::newBool, "Construct a PDF Boolean object");
    m.def("_new_integer", &QPDFObjectHandle::newInteger, "Construct a PDF Integer object");
    m.def("_new_real",
        [](const std::string& value) {
            return QPDFObjectHandle::newReal(value);
        },
        "Construct a PDF Real value, that is, a decimal number"
    );
    m.def("_new_real",
        [](double value, uint places) {
            return QPDFObjectHandle::newReal(value, places);
        },
        "Construct PDF real",
        py::arg("value"),
        py::arg("places") = 0
    );
    m.def("_new_name",
        [](const std::string& s) {
            if (s.length() < 2)
                throw py::value_error("Name must be at least one character long");
            if (s.at(0) != '/')
                throw py::value_error("Name objects must begin with '/'");
            return QPDFObjectHandle::newName(s);
        },
        "Create a Name from a string. Must begin with '/'. All other characters except null are valid."
    );
    m.def("_new_string",
        [](const std::string& s) {
            return QPDFObjectHandle::newString(s);
        },
        "Construct a PDF String object."
    );
    m.def("_new_string_utf8",
        [](const std::string& utf8) {
            return QPDFObjectHandle::newUnicodeString(utf8);
        },
        "Construct a PDF String object from UTF-8 bytes."
    );
    m.def("_new_array",
        [](py::iterable iterable) {
            return QPDFObjectHandle::newArray(array_builder(iterable));
        },
        "Construct a PDF Array object from an iterable of PDF objects or types that can be coerced to PDF objects."
    );
    m.def("_new_dictionary",
        [](py::dict dict) {
            return QPDFObjectHandle::newDictionary(dict_builder(dict));
        },
        "Construct a PDF Dictionary from a mapping of PDF objects or Python types that can be coerced to PDF objects."
    );
    m.def("_new_stream",
        [](std::shared_ptr<QPDF> owner, py::bytes data) {
            std::string s = data;
            return QPDFObjectHandle::newStream(owner.get(), data); // This makes a copy of the data
        },
        "Construct a PDF Stream object from binary data",
        py::keep_alive<0, 1>() // returned object references the owner
    );
    m.def("_new_stream",
        [](std::shared_ptr<QPDF> owner, py::iterable content_stream) {
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
            return QPDFObjectHandle::newStream(owner.get(), data.str());
        },
        "Construct a PDF Stream object from a list of operand-operator tuples [((operands,), operator)]",
        py::keep_alive<0, 1>() // returned object references the owner
    );
    m.def("Operator",
        [](const std::string& op) {
            return QPDFObjectHandle::newOperator(op);
        },
        "Construct a PDF Operator object for use in content streams.",
        py::arg("op")
    );
    m.def("_Null", &QPDFObjectHandle::newNull,
        "Construct a PDF Null object"
    );

    py::class_<QPDFObjectHandle::ParserCallbacks, PyParserCallbacks>(m, "StreamParser")
        .def(py::init<>())
        .def("handle_object",
            [](QPDFObjectHandle::ParserCallbacks &parsercallbacks, QPDFObjectHandle &h) {
                parsercallbacks.handleObject(h);
            }
        )
        .def("handle_eof", &QPDFObjectHandle::ParserCallbacks::handleEOF)
        ;

    m.def("_encode",
        [](py::handle handle) {
            return objecthandle_encode(handle);
        }
    );
    m.def("_roundtrip",
        [](py::object obj) {
            return obj;
        }
    );
    m.def("_roundtrip",
        [](QPDFObjectHandle &h) {
            return h;
        }
    );
    m.def("unparse",
        [](py::object obj) -> py::bytes {
            return objecthandle_encode(obj).unparseBinary();
        }
    );
    m.def("unparse",
        [](QPDFObjectHandle &h) -> py::bytes {
            return h.unparseBinary();
        }
    );



} // init_object
