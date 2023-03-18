// SPDX-FileCopyrightText: 2022 James R. Barlow
// SPDX-License-Identifier: MPL-2.0

#include <cstring>
#include <cctype>

#include <qpdf/Constants.h>
#include <qpdf/Types.h>
#include <qpdf/DLL.h>
#include <qpdf/QPDFExc.hh>
#include <qpdf/QPDFObjGen.hh>
#include <qpdf/QPDFXRefEntry.hh>
#include <qpdf/Buffer.hh>
#include <qpdf/QPDFObjectHandle.hh>
#include <qpdf/QPDF.hh>
#include <qpdf/QPDFWriter.hh>

#include <pybind11/pybind11.h>
#include <pybind11/stl.h>

#include "pikepdf.h"
#include "utils.h"

#include "parsers.h"

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

For Python users appears to have an unexpected side effect, so this action is
prohibited. You cannot set keys to None.

pikepdf.String is a "type" that can be converted with str() or bytes() as
needed.

*/

py::size_t list_range_check(QPDFObjectHandle h, int index)
{
    if (!h.isArray())
        throw py::type_error("object is not an array");
    if (index < 0)
        index += h.getArrayNItems(); // Support negative indexing
    if (!(0 <= index && index < h.getArrayNItems()))
        throw py::index_error("index out of range");
    return static_cast<py::size_t>(index);
}

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

bool objecthandle_equal(QPDFObjectHandle self, QPDFObjectHandle other)
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

    auto self_typecode  = self.getTypeCode();
    auto other_typecode = other.getTypeCode();

    if (typecode_is_bool(self_typecode) && typecode_is_bool(other_typecode)) {
        return self.getBoolValue() == other.getBoolValue();
    } else if (typecode_is_int(self_typecode) && typecode_is_int(other_typecode)) {
        return self.getIntValue() == other.getIntValue();
    } else if (typecode_is_numeric(self_typecode) &&
               typecode_is_numeric(other_typecode)) {
        // If 'self' and 'other' are different numeric types, convert both to
        // Decimal objects and compare them as such.
        auto a              = decimal_from_pdfobject(self);
        auto b              = decimal_from_pdfobject(other);
        py::object pyresult = a.attr("__eq__")(b);
        bool result         = pyresult.cast<bool>();
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
        // Call operator==() on each element of the arrays, meaning this
        // recurses into this function
        return (self.getArrayAsVector() == other.getArrayAsVector());
    }
    case qpdf_object_type_e::ot_dictionary: {
        // Call operator==() on each element of the arrays, meaning this
        // recurses into this function
        return (self.getDictAsMap() == other.getDictAsMap());
    }
    case qpdf_object_type_e::ot_stream: {
        // Recurse into this function to check if our dictionaries are equal
        if (!objecthandle_equal(self.getDict(), other.getDict()))
            return false;

        // If dictionaries are equal, check our stream
        // We don't go as far as decompressing the data to see if it's equal
        auto self_buffer  = self.getRawStreamData();
        auto other_buffer = other.getRawStreamData();

        // Early out: if underlying QPDF Buffers happen to be the same, the data is
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

bool operator==(QPDFObjectHandle self, QPDFObjectHandle other)
{
    // A lot of functions in QPDFObjectHandle are not tagged const where they
    // should be, but are const-safe
    return objecthandle_equal(self, other);
}

bool object_has_key(QPDFObjectHandle h, std::string const &key)
{
    if (!h.isDictionary() && !h.isStream())
        throw py::value_error("pikepdf.Object is not a Dictionary or Stream");
    QPDFObjectHandle dict = h.isStream() ? h.getDict() : h;
    return dict.hasKey(key);
}

bool array_has_item(QPDFObjectHandle haystack, QPDFObjectHandle needle)
{
    if (!haystack.isArray())
        throw std::logic_error("pikepdf.Object is not an Array"); // LCOV_EXCL_LINE

    auto vec    = haystack.getArrayAsVector();
    auto result = std::find(std::begin(vec), std::end(vec), needle);
    return (result != std::end(vec));
}

QPDFObjectHandle object_get_key(QPDFObjectHandle h, std::string const &key)
{
    if (!h.isDictionary() && !h.isStream())
        throw py::value_error("pikepdf.Object is not a Dictionary or Stream");
    QPDFObjectHandle dict = h.isStream() ? h.getDict() : h;
    if (!dict.hasKey(key))
        throw py::key_error(key);
    return dict.getKey(key);
}

void object_set_key(QPDFObjectHandle h, std::string const &key, QPDFObjectHandle &value)
{
    if (!h.isDictionary() && !h.isStream())
        throw py::value_error("pikepdf.Object is not a Dictionary or Stream");
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
    if (!h.isDictionary() && !h.isStream())
        throw py::value_error("pikepdf.Object is not a Dictionary or Stream");
    if (h.isStream() && key == "/Length") {
        throw py::key_error("/Length may not be deleted");
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

std::shared_ptr<Buffer> get_stream_data(
    QPDFObjectHandle &h, qpdf_stream_decode_level_e decode_level)
{
    try {
        return h.getStreamData(decode_level);
    } catch (const QPDFExc &e) {
        // Make a new exception that has the objgen info, since QPDF's
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

    py::class_<Buffer, std::shared_ptr<Buffer>>(m, "Buffer", py::buffer_protocol())
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

    py::class_<QPDFObjectHandle>(m, "Object")
        .def_property_readonly("_type_code", &QPDFObjectHandle::getTypeCode)
        .def_property_readonly("_type_name", &QPDFObjectHandle::getTypeName)
        .def(
            "is_owned_by",
            [](QPDFObjectHandle &h, QPDF &possible_owner) {
                return (h.getOwningQPDF() == &possible_owner);
            },
            "Test if this object is owned by the indicated *possible_owner*.",
            py::arg("possible_owner"))
        .def(
            "same_owner_as",
            [](QPDFObjectHandle &self, QPDFObjectHandle &other) {
                return self.getOwningQPDF() == other.getOwningQPDF();
            },
            "Test if two objects are owned by the same :class:`pikepdf.Pdf`.")
        .def(
            "with_same_owner_as",
            [](QPDFObjectHandle &self, QPDFObjectHandle &other) {
                QPDF *self_owner  = self.getOwningQPDF();
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
            },
            R"~~~(
                Returns an object that is owned by the same Pdf that owns the *other* object.

                If the objects already have the same owner, this object is returned.
                If the *other* object has a different owner, then a copy is created
                that is owned by *other*'s owner. If this object is a direct object
                (no owner), then an indirect object is created that is owned by
                *other*. An exception is thrown if *other* is a direct object.

                This method may be convenient when a reference to the Pdf is not
                available.

                ..versionadded:: 2.14
            )~~~")
        .def_property_readonly("is_indirect", &QPDFObjectHandle::isIndirect)
        .def("__repr__", &objecthandle_repr)
        .def("__hash__",
            [](QPDFObjectHandle &self) -> py::int_ {
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
        .def("__copy__",
            [](QPDFObjectHandle &h) {
                if (h.isStream())
                    return h.copyStream();
                return h.shallowCopy();
            })
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
        .def("__getitem__",
            [](QPDFObjectHandle &h, std::string const &key) {
                return object_get_key(h, key);
            })
        .def("__getitem__",
            [](QPDFObjectHandle &h, QPDFObjectHandle &name) {
                return object_get_key(h, name.getName());
            })
        .def(
            "__setitem__",
            [](QPDFObjectHandle &h, std::string const &key, QPDFObjectHandle &value) {
                object_set_key(h, key, value);
            },
            "assign dictionary key to new object")
        .def(
            "__setitem__",
            [](QPDFObjectHandle &h, QPDFObjectHandle &name, QPDFObjectHandle &value) {
                object_set_key(h, name.getName(), value);
            },
            "assign dictionary key to new object")
        .def("__setitem__",
            [](QPDFObjectHandle &h, std::string const &key, py::object pyvalue) {
                auto value = objecthandle_encode(pyvalue);
                object_set_key(h, key, value);
            })
        .def("__setitem__",
            [](QPDFObjectHandle &h, QPDFObjectHandle &name, py::object pyvalue) {
                auto value = objecthandle_encode(pyvalue);
                object_set_key(h, name.getName(), value);
            })
        .def(
            "__delitem__",
            [](QPDFObjectHandle &h, std::string const &key) { object_del_key(h, key); },
            "delete a dictionary key")
        .def(
            "__delitem__",
            [](QPDFObjectHandle &h, QPDFObjectHandle &name) {
                object_del_key(h, name.getName());
            },
            "delete a dictionary key")
        .def(
            "__getattr__",
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
                } catch (const py::value_error &e) {
                    if (name == std::string("__name__"))
                        throw py::attribute_error(name);
                    throw;
                }
                return value;
            },
            "attribute lookup name")
        .def_property("stream_dict",
            &QPDFObjectHandle::getDict,
            &QPDFObjectHandle::replaceDict,
            "Access the dictionary key-values for a :class:`pikepdf.Stream`.",
            py::return_value_policy::reference_internal)
        .def(
            "__setattr__",
            [](QPDFObjectHandle &h, std::string const &name, py::object pyvalue) {
                if (h.isDictionary() || (h.isStream() && name != "stream_dict")) {
                    // Map attribute assignment to setting dictionary key
                    std::string key = "/" + name;
                    auto value      = objecthandle_encode(pyvalue);
                    object_set_key(h, key, value);
                    return;
                }

                // If we don't have a special rule, do object.__setattr__()
                py::object baseobj = py::module_::import("builtins").attr("object");
                baseobj.attr("__setattr__")(py::cast(h), py::str(name), pyvalue);
            },
            "attribute access")
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
            "For ``pikepdf.Dictionary`` or ``pikepdf.Stream`` objects, behave as "
            "``dict.get(key, default=None)``",
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
            "For ``pikepdf.Dictionary`` or ``pikepdf.Stream`` objects, behave as "
            "``dict.get(key, default=None)``",
            py::arg("key"),
            py::arg("default") = py::none())
        .def(
            "keys",
            [](QPDFObjectHandle &h) {
                if (h.isStream())
                    return h.getDict().getKeys();
                return h.getKeys();
            },
            "For ``pikepdf.Dictionary`` or ``pikepdf.Stream`` objects, obtain the "
            "keys.")
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
            [](QPDFObjectHandle &h, std::string const &key) {
                if (h.isArray()) {
                    throw py::type_error(
                        "Testing `str in pikepdf.Array` is not supported due to "
                        "ambiguity. Use `pikepdf.String('...') in pikepdf.Array.");
                }
                return object_has_key(h, key);
            })
        .def("__contains__",
            [](QPDFObjectHandle &h, py::object key) {
                if (h.isArray()) {
                    return array_has_item(h, objecthandle_encode(key));
                }
                return false;
            })
        .def("as_list", &QPDFObjectHandle::getArrayAsVector)
        .def("as_dict", &QPDFObjectHandle::getDictAsMap)
        .def(
            "__iter__",
            [](QPDFObjectHandle h) -> py::iterable {
                if (h.isArray()) {
                    auto vec   = h.getArrayAsVector();
                    auto pyvec = py::cast(vec);
                    return pyvec.attr("__iter__")();
                } else if (h.isDictionary() || h.isStream()) {
                    if (h.isStream())
                        h = h.getDict();
                    auto keys   = h.getKeys();
                    auto pykeys = py::cast(keys);
                    return pykeys.attr("__iter__")();
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
                auto dict   = h.getDictAsMap();
                auto pydict = py::cast(dict);
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
        .def("__getitem__",
            [](QPDFObjectHandle &h, int index) {
                auto u_index = list_range_check(h, index);
                return h.getArrayItem(u_index);
            })
        .def("__setitem__",
            [](QPDFObjectHandle &h, int index, QPDFObjectHandle &value) {
                auto u_index = list_range_check(h, index);
                h.setArrayItem(u_index, value);
            })
        .def("__setitem__",
            [](QPDFObjectHandle &h, int index, py::object pyvalue) {
                auto u_index = list_range_check(h, index);
                auto value   = objecthandle_encode(pyvalue);
                h.setArrayItem(u_index, value);
            })
        .def("__delitem__",
            [](QPDFObjectHandle &h, int index) {
                auto u_index = list_range_check(h, index);
                h.eraseItem(u_index);
            })
        .def(
            "wrap_in_array",
            [](QPDFObjectHandle &h) { return h.wrapInArray(); },
            "Return the object wrapped in an array if not already an array.")
        .def(
            "append",
            [](QPDFObjectHandle &h, py::object pyitem) {
                auto item = objecthandle_encode(pyitem);
                return h.appendItem(item);
            },
            "Append another object to an array; fails if the object is not an array.")
        .def(
            "extend",
            [](QPDFObjectHandle &h, py::iterable iter) {
                for (auto item : iter) {
                    h.appendItem(objecthandle_encode(item));
                }
            },
            "Extend a pikepdf.Array with an iterable of other objects.")
        .def_property_readonly("is_rectangle",
            &QPDFObjectHandle::isRectangle, // LCOV_EXCL_LINE
            "Returns True if the object is a rectangle (an array of 4 numbers)")
        .def(
            "get_stream_buffer",
            [](QPDFObjectHandle &h, qpdf_stream_decode_level_e decode_level) {
                return get_stream_data(h, decode_level);
            },
            "Return a buffer protocol buffer describing the decoded stream.",
            py::arg("decode_level") = qpdf_dl_generalized)
        .def(
            "get_raw_stream_buffer",
            [](QPDFObjectHandle &h) { return h.getRawStreamData(); },
            "Return a buffer protocol buffer describing the raw, encoded stream")
        .def(
            "read_bytes",
            [](QPDFObjectHandle &h, qpdf_stream_decode_level_e decode_level) {
                auto buf = get_stream_data(h, decode_level);
                return py::bytes((const char *)buf->getBuffer(), buf->getSize());
            },
            "Decode and read the content stream associated with this object.",
            py::arg("decode_level") = qpdf_dl_generalized)
        .def(
            "read_raw_bytes",
            [](QPDFObjectHandle &h) {
                auto buf = h.getRawStreamData();
                // py::bytes will make a copy of the buffer, so releasing is fine
                return py::bytes((const char *)buf->getBuffer(), buf->getSize());
            },
            "Read the content stream associated with this object without decoding")
        .def(
            "_write",
            [](QPDFObjectHandle &h,
                py::bytes data,
                py::object filter,
                py::object decode_parms) {
                std::string sdata               = data;
                QPDFObjectHandle h_filter       = objecthandle_encode(filter);
                QPDFObjectHandle h_decode_parms = objecthandle_encode(decode_parms);
                h.replaceStreamData(sdata, h_filter, h_decode_parms);
            },
            R"~~~(
            Low level write/replace stream data without argument checking. Use .write().
            )~~~",
            py::arg("data"),
            py::arg("filter"),
            py::arg("decode_parms"))
        .def("_inline_image_raw_bytes",
            [](QPDFObjectHandle &h) { return py::bytes(h.getInlineImageValue()); })
        .def_property_readonly("_objgen", &object_get_objgen)
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
            )~~~")
        .def_static(
            "parse",
            [](std::string const &stream, std::string const &description) {
                return QPDFObjectHandle::parse(stream, description);
            },
            "Parse PDF binary representation into PDF objects.",
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
            "unparse",
            [](QPDFObjectHandle &h, bool resolved) -> py::bytes {
                if (resolved)
                    return h.unparseResolved();
                return h.unparse();
            },
            py::arg("resolved") = false,
            R"~~~(
            Convert PDF objects into their binary representation, optionally
            resolving indirect objects.

            If you want to unparse content streams, which are a collection of
            objects that need special treatment, use
            :func:`pikepdf.unparse_content_stream` instead.

            Returns ``bytes()`` that can be used with :meth:`Object.parse`
            to reconstruct the ``pikepdf.Object``. If reconstruction is not possible,
            a relative object reference is returned, such as ``4 0 R``.

            Args:
                resolved: If True, deference indirect objects where possible.
            )~~~")
        .def(
            "to_json",
            [](QPDFObjectHandle &h,
                bool dereference   = false,
                int schema_version = 2) -> py::bytes {
                return h.getJSON(schema_version, dereference).unparse();
            },
            py::arg("schema_version") = 2,
            py::arg("dereference")    = false,
            R"~~~(
            Convert to a QPDF JSON representation of the object.

            See the QPDF manual for a description of its JSON representation.
            https://qpdf.readthedocs.io/en/stable/json.html#qpdf-json-format

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
                dereference (bool): If True, dereference the object if this is an
                    indirect object.
                schema_version (int): The version of the JSON schema. Defaults to 2.

            Returns:
                JSON bytestring of object. The object is UTF-8 encoded
                and may be decoded to a Python str that represents the binary
                values ``\x00-\xFF`` as ``U+0000`` to ``U+00FF``; that is,
                it may contain mojibake.

            .. versionchanged:: 6.0
                Added *schema_version*.
            )~~~"); // end of QPDFObjectHandle bindings

    m.def("_new_boolean", &QPDFObjectHandle::newBool, "Construct a PDF Boolean object");
    m.def("_new_integer",
        &QPDFObjectHandle::newInteger,
        "Construct a PDF Integer object");
    m.def(
        "_new_real",
        [](const std::string &value) { return QPDFObjectHandle::newReal(value); },
        "Construct a PDF Real value, that is, a decimal number");
    m.def(
        "_new_real",
        [](double value, uint places) {
            return QPDFObjectHandle::newReal(value, places);
        },
        "Construct PDF real",
        py::arg("value"),
        py::arg("places") = 0);
    m.def(
        "_new_name",
        [](const std::string &s) {
            if (s.length() < 2)
                throw py::value_error("Name must be at least one character long");
            if (s.at(0) != '/')
                throw py::value_error("Name objects must begin with '/'");
            return QPDFObjectHandle::newName(s);
        },
        "Create a Name from a string. Must begin with '/'. All other characters except "
        "null are valid.");
    m.def(
        "_new_string",
        [](const std::string &s) { return QPDFObjectHandle::newString(s); },
        "Construct a PDF String object.");
    m.def(
        "_new_string_utf8",
        [](const std::string &utf8) {
            return QPDFObjectHandle::newUnicodeString(utf8);
        },
        "Construct a PDF String object from UTF-8 bytes.");
    m.def(
        "_new_array",
        [](py::iterable iterable) {
            return QPDFObjectHandle::newArray(array_builder(iterable));
        },
        "Construct a PDF Array object from an iterable of PDF objects or types that "
        "can be coerced to PDF objects.");
    m.def(
        "_new_dictionary",
        [](py::dict dict) {
            return QPDFObjectHandle::newDictionary(dict_builder(dict));
        },
        "Construct a PDF Dictionary from a mapping of PDF objects or Python types that "
        "can be coerced to PDF objects.");
    m.def(
        "_new_stream",
        [](QPDF &owner, py::bytes data) {
            // This makes a copy of the data
            return QPDFObjectHandle::newStream(&owner, data);
        },
        "Construct a PDF Stream object from binary data");
    m.def(
        "_new_operator",
        [](const std::string &op) { return QPDFObjectHandle::newOperator(op); },
        "Construct a PDF Operator object for use in content streams.",
        py::arg("op"));
    m.def("_Null", &QPDFObjectHandle::newNull, "Construct a PDF Null object");

    py::class_<QPDFObjectHandle::ParserCallbacks, PyParserCallbacks>(m,
        "StreamParser",
        R"~~~(
            A simple content stream parser, which must be subclassed to be used.

            In practice, the performance of this class may be quite poor on long
            content streams because it creates objects and involves multiple
            function calls for every object in a content stream, some of which
            may be only a single byte long.

            Consider instead using :func:`pikepdf.parse_content_stream`.
        )~~~")
        .def(py::init<>(), "You must call ``super.__init__()`` in subclasses.")
        // LCOV_EXCL_START
        // coverage misses the virtual function call ::handleObject here.
        .def(
            "handle_object",
            [](QPDFObjectHandle::ParserCallbacks &parsercallbacks,
                QPDFObjectHandle &h,
                size_t offset,
                size_t length) { parsercallbacks.handleObject(h, offset, length); },
            R"~~~(
                This is an abstract method that must be overloaded in a subclass.

                This function will be called back once for each object that is
                parsed in the content stream.
            )~~~")
        // LCOV_EXCL_STOP
        .def("handle_eof",
            &QPDFObjectHandle::ParserCallbacks::handleEOF,
            R"~~~(
                This is an abstract method that may be overloaded in a subclass.

                Called at the end of a content stream.
            )~~~");

    // Since QPDFEmbeddedFileDocumentHelper::getEmbeddedFiles returns
    // std::map<std::string, std::shared_ptr<QPDFFileSpecObjectHelper>>
    // we must ensure that the entire QPDFObjectHelper type hierarchy is held in
    // std::shared_ptr or repackage that interface so it does not return a
    // std::shared_ptr<QPDFFileSpecObjectHelper>> to Python.
    py::class_<QPDFObjectHelper, std::shared_ptr<QPDFObjectHelper>>(m,
        "ObjectHelper",
        R"~~~(
            Base class for wrapper/helper around an Object.

            Used to expose additional functionality specific to that object type.
        )~~~")
        .def(
            "__eq__",
            [](QPDFObjectHelper &self, QPDFObjectHelper &other) {
                // Pages that are copies
                return objecthandle_equal(
                    self.getObjectHandle(), other.getObjectHandle());
            },
            py::is_operator())
        .def_property_readonly(
            "obj",
            [](QPDFObjectHelper &poh) -> QPDFObjectHandle {
                return poh.getObjectHandle();
            },
            R"~~~(
                Get the underlying :class:`pikepdf.Object`.
            )~~~");

    m.def("_encode", [](py::handle handle) { return objecthandle_encode(handle); });
    m.def("unparse", [](py::object obj) -> py::bytes {
        return objecthandle_encode(obj).unparseBinary();
    });
} // init_object
