// SPDX-FileCopyrightText: 2022 James R. Barlow
// SPDX-License-Identifier: MPL-2.0

#include "object.h"
#include "pikepdf.h"
#include "qpdf_lock.h"
#include "utils.h"

#include "namepath.h"
#include "parsers.h"

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

// Encodes Python key to bytes, handling surrogates for invalid UTF-8.
std::string string_from_key(py::handle key)
{
    if (py::isinstance<py::bytes>(key)) {
        py::bytes b = py::borrow<py::bytes>(key);
        return std::string(static_cast<const char *>(b.data()), b.size());
    }
    if (py::isinstance<py::str>(key)) {
        py::bytes encoded_key =
            py::borrow<py::bytes>(key.attr("encode")("utf-8", "surrogateescape"));
        return std::string(
            static_cast<const char *>(encoded_key.data()), encoded_key.size());
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
        throw py::python_error(); // LCOV_EXCL_LINE
    }

    return py::steal<py::str>(py_s);
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

size_t list_range_check(QPDFObjectHandle h, int index)
{
    QpdfLockGuard lock(h.getOwningQPDF());
    if (!h.isArray())
        throw py::type_error("object is not an array");
    if (index < 0)
        index += h.getArrayNItems(); // Support negative indexing
    if (!(0 <= index && index < h.getArrayNItems()))
        throw py::index_error("index out of range");
    return static_cast<size_t>(index);
}

static void ensure_keyed(
    QPDFObjectHandle &h, const char *action, std::string const &key)
{
    if (!h.isDictionary() && !h.isStream()) {
        throw py::value_error(("pikepdf.Object is not a Dictionary or Stream: cannot " +
                               std::string(action) + " key '" + key +
                               "' on object of type " + h.getTypeName())
                .c_str());
    }
}

bool object_has_key(QPDFObjectHandle h, std::string const &key)
{
    QpdfLockGuard lock(h.getOwningQPDF());
    ensure_keyed(h, "check existence of", key);
    QPDFObjectHandle dict = h.isStream() ? h.getDict() : h;
    return dict.hasKey(key);
}

bool array_has_item(QPDFObjectHandle haystack, QPDFObjectHandle needle)
{
    if (!haystack.isArray())
        throw std::logic_error("pikepdf.Object is not an Array"); // LCOV_EXCL_LINE

    for (auto &item : haystack.aitems()) {
        if (objecthandle_equal(item, needle))
            return true;
    }
    return false;
}

QPDFObjectHandle object_get_key(QPDFObjectHandle h, std::string const &key)
{
    QpdfLockGuard lock(h.getOwningQPDF());
    ensure_keyed(h, "get", key);
    QPDFObjectHandle dict = h.isStream() ? h.getDict() : h;
    if (!dict.hasKey(key))
        throw py::key_error(key.c_str());
    return dict.getKey(key);
}

void object_set_key(QPDFObjectHandle h, std::string const &key, QPDFObjectHandle &value)
{
    QpdfLockGuard lock(h.getOwningQPDF());
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
    QpdfLockGuard lock(h.getOwningQPDF());
    ensure_keyed(h, "delete", key);
    if (h.isStream() && key == "/Length") {
        throw py::key_error("/Length may not be deleted");
    }

    // For streams, the actual dictionary is attached to stream object
    QPDFObjectHandle dict = h.isStream() ? h.getDict() : h;

    if (!dict.hasKey(key))
        throw py::key_error(key.c_str());

    dict.removeKey(key);
}

// Traverse a NamePath, returning the final object or throwing with context
QPDFObjectHandle traverse_namepath(
    QPDFObjectHandle h, NamePath const &path, bool for_set)
{
    QpdfLockGuard lock(h.getOwningQPDF());
    auto const &components = path.components();
    size_t end = for_set ? components.size() - 1 : components.size();

    QPDFObjectHandle current = h;
    for (size_t i = 0; i < end; ++i) {
        if (std::holds_alternative<std::string>(components[i])) {
            auto const &key = std::get<std::string>(components[i]);
            if (!current.isDictionary() && !current.isStream()) {
                throw py::type_error(
                    ("Expected Dictionary or Stream at " + path.format_path(i) +
                        ", got " + current.getTypeName())
                        .c_str());
            }
            QPDFObjectHandle dict = current.isStream() ? current.getDict() : current;
            if (!dict.hasKey(key)) {
                throw py::key_error(
                    ("Key " + key + " not found; traversed " + path.format_path(i))
                        .c_str());
            }
            current = dict.getKey(key);
        } else {
            int index = std::get<int>(components[i]);
            if (!current.isArray()) {
                throw py::type_error(("Expected Array at " + path.format_path(i) +
                                      ", got " + current.getTypeName())
                        .c_str());
            }
            int size = current.getArrayNItems();
            if (index < 0)
                index += size;
            if (index < 0 || index >= size) {
                throw py::index_error(("Index " + std::to_string(index) +
                                       " out of range at " + path.format_path(i))
                        .c_str());
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
    QpdfLockGuard lock(h.getOwningQPDF());
    if (h.isStream())
        return h.copyStream();
    return h.shallowCopy();
}

std::shared_ptr<Buffer> get_stream_data(
    QPDFObjectHandle &h, qpdf_stream_decode_level_e decode_level)
{
    QpdfLockGuard lock(h.getOwningQPDF());
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

    // Buffer protocol implementation for Buffer class via PyType_Slot.
    // This is needed because nanobind removed py::buffer_protocol().
    static PyType_Slot buffer_slots[] = {
        {Py_tp_traverse,
            (void *)+[](PyObject *self, visitproc visit, void *arg) -> int {
                Py_VISIT(Py_TYPE(self));
                return 0;
            }},
        {Py_tp_clear, (void *)+[](PyObject *) -> int { return 0; }},
        {Py_bf_getbuffer,
            (void *)+[](PyObject *exporter, Py_buffer *view, int flags) -> int {
                // LCOV_EXCL_START - defensive; CPython always passes a valid view
                if (view == nullptr) {
                    PyErr_SetString(PyExc_BufferError, "NULL Py_buffer pointer");
                    return -1;
                }
                // LCOV_EXCL_STOP
                Buffer *b = py::inst_ptr<Buffer>(exporter);
                view->buf = b->getBuffer();
                view->obj = exporter;
                Py_INCREF(exporter);
                view->len = static_cast<Py_ssize_t>(b->getSize());
                view->itemsize = 1;
                view->readonly = 1;
                view->ndim = 1;
                view->format =
                    (flags & PyBUF_FORMAT) ? const_cast<char *>("B") : nullptr;
                view->shape = (flags & PyBUF_ND) ? &view->len : nullptr;
                view->strides = (flags & PyBUF_STRIDES) ? &view->itemsize : nullptr;
                view->suboffsets = nullptr;
                view->internal = nullptr;
                return 0;
            }},
        {Py_bf_releasebuffer,
            (void *)+[](PyObject *, Py_buffer *) -> void {
                // Nothing to release
            }},
        {0, nullptr}};

    py::class_<Buffer>(m, "Buffer", py::type_slots(buffer_slots))
        .def("__bytes__",
            [](Buffer &b) {
                return py::bytes((const char *)b.getBuffer(), b.getSize());
            })
        .def("__len__", [](Buffer &b) { return b.getSize(); });

    // LCOV_EXCL_START - gcov misattributes lines inside this lambda; covered by
    // tests/test_objectlist.py::test_objectlist_repr
    py::bind_vector<ObjectList>(m, "_ObjectList", py::type_slots(pikepdf_gc_slots))
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
    // LCOV_EXCL_STOP

    py::bind_map<ObjectMap>(m, "_ObjectMapping", py::type_slots(pikepdf_gc_slots));

// MSVC raises a false positive warning here
#if _MSC_VER
#    pragma warning(suppress : 4267)
#endif
    auto object =
        py::class_<QPDFObjectHandle>(m, "Object", py::type_slots(pikepdf_gc_slots));
    object.def_prop_ro("_type_code", &QPDFObjectHandle::getTypeCode)
        .def_prop_ro("_type_code_int",
            [](QPDFObjectHandle &self) { return static_cast<int>(self.getTypeCode()); })
        .def_prop_ro("_type_name", &QPDFObjectHandle::getTypeName)
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
                DualQpdfLockGuard lock(self_owner, other_owner);

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
        .def_prop_ro("is_indirect", &QPDFObjectHandle::isIndirect)
        .def("__repr__",
            [](QPDFObjectHandle &self) {
                QpdfLockGuard lock(self.getOwningQPDF());
                return objecthandle_repr(self);
            })
        .def("__hash__",
            [](QPDFObjectHandle &self) -> py::int_ {
                QpdfLockGuard lock(self.getOwningQPDF());
                if (self.isIndirect())
                    throw py::type_error("Can't hash indirect object");

                // Objects which compare equal must have the same hash value
                switch (self.getTypeCode()) {
                case qpdf_object_type_e::ot_string: {
                    auto v = self.getUTF8Value();
                    return py::int_(py::hash(py::bytes(v.data(), v.size())));
                }
                case qpdf_object_type_e::ot_name: {
                    auto v = self.getName();
                    return py::int_(py::hash(py::bytes(v.data(), v.size())));
                }
                case qpdf_object_type_e::ot_operator: {
                    auto v = self.getOperatorValue();
                    return py::int_(py::hash(py::bytes(v.data(), v.size())));
                }
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
                DualQpdfLockGuard lock(self.getOwningQPDF(), other.getOwningQPDF());
                return objecthandle_equal(self, other);
            },
            py::is_operator())
        .def(
            "__eq__",
            [](QPDFObjectHandle &self, py::str other) {
                QpdfLockGuard lock(self.getOwningQPDF());
                std::string utf8_other = py::cast<std::string>(other);
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
                QpdfLockGuard lock(self.getOwningQPDF());
                std::string bytes_other = to_string(other);
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
                QpdfLockGuard lock(self.getOwningQPDF());
                QPDFObjectHandle q_other;
                try {
                    q_other = objecthandle_encode(other);
                } catch (const std::exception &) {
                    return py::borrow<py::object>(py::handle(Py_NotImplemented));
                }
                bool result = objecthandle_equal(self, q_other);
                return py::bool_(result);
            },
            py::is_operator())
        .def("__copy__", &copy_object)
        .def("__len__",
            [](QPDFObjectHandle &h) -> size_t {
                QpdfLockGuard lock(h.getOwningQPDF());
                if (h.isDictionary()) {
                    // getKeys constructs a new object, so this is better
                    return static_cast<size_t>(h.getDictAsMap().size());
                } else if (h.isArray()) {
                    int nitems = h.getArrayNItems();
                    // LCOV_EXCL_START
                    if (nitems < 0) {
                        throw std::logic_error("Array items < 0");
                    }
                    // LCOV_EXCL_STOP
                    return static_cast<size_t>(nitems);
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
                QpdfLockGuard lock(h.getOwningQPDF());
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
                // LCOV_EXCL_START
                PyErr_SetString(PyExc_NotImplementedError, "code is unreachable");
                throw py::python_error();
                // LCOV_EXCL_STOP
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
                    throw py::type_error( // LCOV_EXCL_LINE
                        "Object is not a real number");
                return h.getRealValue();
            })
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
        .def(
            "__add__",
            [](QPDFObjectHandle &h, py::object other) -> py::object {
                if (!h.isInteger() && !h.isReal())
                    throw py::type_error("Object is not numeric");
                return py::borrow<py::object>(py::handle(Py_NotImplemented));
            },
            py::is_operator())
        .def(
            "__radd__",
            [](QPDFObjectHandle &h, py::object other) -> py::object {
                if (!h.isInteger() && !h.isReal())
                    throw py::type_error("Object is not numeric");
                return py::borrow<py::object>(py::handle(Py_NotImplemented));
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
                return py::borrow<py::object>(py::handle(Py_NotImplemented));
            },
            py::is_operator())
        .def(
            "__rsub__",
            [](QPDFObjectHandle &h, py::object other) -> py::object {
                if (!h.isInteger() && !h.isReal())
                    throw py::type_error("Object is not numeric");
                return py::borrow<py::object>(py::handle(Py_NotImplemented));
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
                return py::borrow<py::object>(py::handle(Py_NotImplemented));
            },
            py::is_operator())
        .def(
            "__rmul__",
            [](QPDFObjectHandle &h, py::object other) -> py::object {
                if (!h.isInteger() && !h.isReal())
                    throw py::type_error("Object is not numeric");
                return py::borrow<py::object>(py::handle(Py_NotImplemented));
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
                return py::borrow<py::object>(py::handle(Py_NotImplemented));
            },
            py::is_operator())
        .def(
            "__rtruediv__",
            [](QPDFObjectHandle &h, py::object other) -> py::object {
                if (!h.isInteger() && !h.isReal())
                    throw py::type_error("Object is not numeric");
                return py::borrow<py::object>(py::handle(Py_NotImplemented));
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
                return py::borrow<py::object>(py::handle(Py_NotImplemented));
            },
            py::is_operator())
        .def(
            "__rfloordiv__",
            [](QPDFObjectHandle &h, py::object other) -> py::object {
                if (!h.isInteger() && !h.isReal())
                    throw py::type_error("Object is not numeric");
                return py::borrow<py::object>(py::handle(Py_NotImplemented));
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
                return py::borrow<py::object>(py::handle(Py_NotImplemented));
            },
            py::is_operator())
        .def(
            "__rmod__",
            [](QPDFObjectHandle &h, py::object other) -> py::object {
                if (!h.isInteger() && !h.isReal())
                    throw py::type_error("Object is not numeric");
                return py::borrow<py::object>(py::handle(Py_NotImplemented));
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
        .def("__abs__", [](QPDFObjectHandle &h) -> py::object {
            if (h.isInteger())
                return py::cast(std::abs(h.getIntValue()));
            if (h.isReal())
                return py::cast(std::abs(std::stod(h.getRealValue())));
            throw py::type_error("Object is not numeric");
        });

    init_object_methods(object);

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
        [](py::handle s) { return QPDFObjectHandle::newString(to_string(s)); });
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
        QpdfLockGuard lock(&owner);
        // This makes a copy of the data
        return QPDFObjectHandle::newStream(&owner, to_string(data));
    });
    m.def(
        "_new_operator",
        [](py::handle op) { return QPDFObjectHandle::newOperator(to_string(op)); },
        py::arg("op"));
    m.def("_Null", &QPDFObjectHandle::newNull, "Construct a PDF Null object");

    py::class_<QPDFObjectHandle::ParserCallbacks, PyParserCallbacks>(
        m, "StreamParser", py::type_slots(pikepdf_gc_slots))
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
    py::class_<QPDFObjectHelper>(m, "ObjectHelper", py::type_slots(pikepdf_gc_slots))
        .def(
            "__eq__",
            [](QPDFObjectHelper &self, QPDFObjectHelper &other) {
                // Object helpers are equal if their object handles are equal
                return objecthandle_equal(
                    self.getObjectHandle(), other.getObjectHandle());
            },
            py::is_operator())
        .def_prop_ro("obj", [](QPDFObjectHelper &poh) -> QPDFObjectHandle {
            return poh.getObjectHandle();
        });

    m.def(
        "_encode",
        [](py::handle handle) { return objecthandle_encode(handle); },
        py::arg("handle").none());
    m.def("unparse", [](py::object obj) -> py::bytes {
        auto s = objecthandle_encode(obj).unparseBinary();
        return py::bytes(s.data(), s.size());
    });
} // init_object
