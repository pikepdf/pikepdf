// SPDX-FileCopyrightText: 2026 James R. Barlow
// SPDX-License-Identifier: MPL-2.0

#include "pikepdf.h"

#include <string>

#include <qpdf/QPDFObjectHandle.hh>

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------
//
// We build the facade metaclasses the way `class M(base): ...` does: by calling
// type(name, (base,), namespace). The namespace's dunder methods are nanobind
// functions created with py::is_method() so they are nb_method objects (which
// carry Py_TPFLAGS_METHOD_DESCRIPTOR) and therefore bind `self` (the class)
// correctly when CPython's slot dispatch invokes them. __getattr__ given this
// way automatically has fallback-only semantics (it fires only when normal
// attribute lookup raises AttributeError).
//
// Why this route instead of PyType_FromSpecWithBases?
//   `type` is a variable-sized type (non-zero tp_itemsize), and before Python
//   3.12 the PyType_FromSpec* family did not robustly support creating a
//   *metaclass* (a subclass of `type`): getting basicsize/itemsize/GC right is
//   version-dependent and can silently mis-size instances rather than fail
//   cleanly. Calling type(...) goes through type_new -- the exact path the
//   interpreter uses for `class M(type): ...` -- so it is correct on every
//   supported version (our floor is requires-python >= 3.10).
//
//   TODO(py>=3.12): once the minimum supported Python is 3.12, replace the
//   make_metaclass() / type(...) dance with PyType_FromMetaclass(), which was
//   added precisely to create metaclasses and to handle metaclass itemsize.
//   That is the newer, cleaner API and lets these dunders be plain C slot
//   functions (Py_tp_getattro / Py_tp_setattro / Py_mp_subscript) again,
//   dropping the py::is_method() requirement. The same revision applies to the
//   _NamePathMeta construction in namepath.cpp.

// type(name, (base,), ns)
static py::object make_metaclass(const char *name, py::handle base, py::dict ns)
{
    py::tuple bases = py::make_tuple(base);
    PyObject *t = PyObject_CallFunction(
        (PyObject *)&PyType_Type, "sOO", name, bases.ptr(), ns.ptr());
    if (t == nullptr)
        throw py::python_error();
    return py::steal(t);
}

// meta(name, (object,), ns) -- create a facade type as an instance of `meta`.
// ns must contain __new__ (already staticmethod-wrapped); object_type is added here.
// Docstrings live in the src/pikepdf/_core stubs, not here.
static py::object make_facade(
    py::handle meta, const char *name, py::object object_type, py::dict ns)
{
    ns["object_type"] = object_type;
    ns["__module__"] = py::str("pikepdf._core");
    ns["__qualname__"] = py::str(name);
    py::tuple bases = py::make_tuple(py::handle((PyObject *)&PyBaseObject_Type));
    PyObject *t = PyObject_CallFunction(meta.ptr(), "sOO", name, bases.ptr(), ns.ptr());
    if (t == nullptr)
        throw py::python_error();
    return py::steal(t);
}

// Wrap a nanobind cpp_function as a staticmethod and put it under __new__.
// Use the staticmethod() builtin rather than PyStaticMethod_New, which is not
// part of the limited API (abi3) that our stable-ABI wheels are built against.
static void set_new(py::dict ns, py::object fn)
{
    py::object staticmethod = py::module_::import_("builtins").attr("staticmethod");
    ns["__new__"] = staticmethod(fn);
}

// ---------------------------------------------------------------------------
// init
// ---------------------------------------------------------------------------

void init_object_construct(py::module_ &m)
{
    py::object ObjectType = m.attr("ObjectType");
    py::object Rectangle = m.attr("Rectangle");
    py::object Matrix = m.attr("Matrix");

    // ---- _ObjectMeta(type): isinstance via QPDF type code ----
    py::dict object_meta_ns;
    object_meta_ns["__instancecheck__"] = py::cpp_function(
        [](py::handle cls, py::handle instance) -> bool {
            try {
                if (!py::isinstance<QPDFObjectHandle>(instance))
                    return false;
                auto &oh = py::cast<QPDFObjectHandle &>(instance);
                int inst_code = static_cast<int>(oh.getTypeCode());
                int cls_code = py::cast<int>(cls.attr("object_type").attr("value"));
                return inst_code == cls_code;
            } catch (py::python_error &e) {
                if (e.matches(PyExc_AttributeError))
                    return false; // mirror objects.py: False when type info is absent
                throw;
            }
        },
        py::is_method(),
        py::arg("instance").none());
    py::object object_meta = make_metaclass(
        "_ObjectMeta", py::handle((PyObject *)&PyType_Type), object_meta_ns);

    // ---- _NameObjectMeta(_ObjectMeta): Name.Foo / Name['x'] / Name.Foo=1 ----
    py::dict name_meta_ns;
    // Name.Foo -> Name('/Foo'). __getattr__ fires only on normal-lookup miss.
    name_meta_ns["__getattr__"] = py::cpp_function(
        [](py::handle cls, std::string attr) -> py::object {
            // __getattr__ only fires on a normal-lookup miss; raising here for
            // dunder/private names is equivalent to the Python delegation.
            if (!attr.empty() && attr[0] == '_')
                throw py::attribute_error(attr.c_str());
            return py::cast(QPDFObjectHandle::newName("/" + attr));
        },
        py::is_method(),
        py::arg("attr"));
    name_meta_ns["__setattr__"] = py::cpp_function(
        [](py::handle cls, py::str name, py::handle value) -> void {
            std::string attr = py::cast<std::string>(name);
            if ((!attr.empty() && attr[0] == '_') || attr == "object_type") {
                // Delegate to type.__setattr__. PyType_Type.tp_setattro is not
                // usable under the limited API (PyTypeObject is opaque there).
                py::module_::import_("builtins")
                    .attr("type")
                    .attr("__setattr__")(cls, name, value);
                return;
            }
            throw py::attribute_error(
                "Attributes may not be set on pikepdf.Name. Perhaps you meant "
                "to modify a Dictionary rather than a Name?");
        },
        py::is_method(),
        py::arg("name"),
        py::arg("value"));
    name_meta_ns["__getitem__"] = py::cpp_function(
        [](py::handle cls, py::object item) -> py::object {
            std::string suffix;
            if (py::isinstance<py::str>(item)) {
                suffix = py::cast<std::string>(item);
                if (!suffix.empty() && suffix[0] == '/')
                    suffix = suffix.substr(1);
            }
            std::string msg = "pikepdf.Name is not subscriptable. You probably meant:\n"
                              "    pikepdf.Name." +
                              suffix + "\nor\n    pikepdf.Name('/" + suffix + "')\n";
            throw py::type_error(msg.c_str());
        },
        py::is_method(),
        py::arg("item"));
    py::object name_meta = make_metaclass("_NameObjectMeta", object_meta, name_meta_ns);

    // ---- Name ----
    {
        py::dict ns;
        py::object name_new = py::cpp_function(
            [](py::handle cls, py::object name) -> py::object {
                if (py::isinstance<py::bytes>(name))
                    throw py::type_error("Name should be str");
                if (py::isinstance<QPDFObjectHandle>(name)) {
                    auto &oh = py::cast<QPDFObjectHandle &>(name);
                    if (oh.isName())
                        return py::borrow(name);
                }
                std::string s;
                try {
                    s = py::cast<std::string>(name);
                } catch (const py::cast_error &) {
                    throw py::type_error("Name should be str");
                }
                if (s.size() < 2)
                    throw py::value_error("Name must be at least one character long");
                if (s[0] != '/')
                    throw py::value_error("Name objects must begin with '/'");
                return py::cast(QPDFObjectHandle::newName(s));
            },
            py::arg("cls"),
            py::arg("name"));
        set_new(ns, name_new);

        // Name.random: keep the cryptographic RNG in Python's secrets module.
        py::object name_random = py::cpp_function(
            [](py::handle cls, int len_, std::string prefix) -> py::object {
                py::object token =
                    py::module_::import_("secrets").attr("token_urlsafe")(len_);
                std::string s = "/" + prefix + py::cast<std::string>(token);
                return py::cast(QPDFObjectHandle::newName(s));
            },
            py::arg("cls"),
            py::arg("len_") = 16,
            py::arg("prefix") = "");
        // classmethod() builtin (not PyClassMethod_New) for limited-API safety.
        ns["random"] =
            py::module_::import_("builtins").attr("classmethod")(name_random);

        m.attr("Name") = make_facade(name_meta, "Name", ObjectType.attr("name_"), ns);
    }

    // ---- Operator ----
    {
        py::dict ns;
        py::object fn = py::cpp_function(
            [](py::handle cls, py::object name) -> py::object {
                return py::cast(QPDFObjectHandle::newOperator(to_string(name)));
            },
            py::arg("cls"),
            py::arg("name"));
        set_new(ns, fn);
        m.attr("Operator") =
            make_facade(object_meta, "Operator", ObjectType.attr("operator"), ns);
    }

    // ---- String ----
    {
        py::dict ns;
        py::object fn = py::cpp_function(
            [](py::handle cls, py::object s) -> py::object {
                if (py::isinstance<py::bytes>(s) || py::isinstance<py::bytearray>(s) ||
                    PyMemoryView_Check(s.ptr())) {
                    // bytearray/memoryview fall through to to_string, which
                    // raises TypeError -- preserving current behavior.
                    return py::cast(QPDFObjectHandle::newString(to_string(s)));
                }
                try {
                    return py::cast(
                        QPDFObjectHandle::newUnicodeString(py::cast<std::string>(s)));
                } catch (const py::cast_error &) {
                    throw py::type_error("String should be a str or bytes");
                }
            },
            py::arg("cls"),
            py::arg("s"));
        set_new(ns, fn);
        m.attr("String") =
            make_facade(object_meta, "String", ObjectType.attr("string"), ns);
    }

    // ---- Array ----
    {
        py::dict ns;
        py::object fn = py::cpp_function(
            [Rectangle, Matrix](py::handle cls, py::object a) -> py::object {
                if (py::isinstance<py::str>(a) || py::isinstance<py::bytes>(a))
                    throw py::type_error(
                        "Strings cannot be converted to arrays of chars");
                if (a.is_none())
                    return py::cast(QPDFObjectHandle::newArray());
                if (py::isinstance(a, Rectangle) || py::isinstance(a, Matrix))
                    return a.attr("as_array")();
                if (py::isinstance<QPDFObjectHandle>(a)) {
                    auto &oh = py::cast<QPDFObjectHandle &>(a);
                    if (oh.isArray())
                        return a.attr("__copy__")();
                }
                try {
                    return py::cast(QPDFObjectHandle::newArray(
                        array_builder(py::cast<py::iterable>(a))));
                } catch (const py::cast_error &) {
                    throw py::type_error(
                        "Array must be constructed from an iterable of objects");
                }
            },
            py::arg("cls"),
            py::arg("a") = py::none());
        set_new(ns, fn);
        m.attr("Array") =
            make_facade(object_meta, "Array", ObjectType.attr("array"), ns);
    }

    // ---- Dictionary ----
    {
        py::dict ns;
        py::object fn = py::cpp_function(
            [](py::handle cls, py::object d, py::kwargs kwargs) -> py::object {
                bool has_kwargs = py::len(kwargs) > 0;
                if (has_kwargs && !d.is_none())
                    throw py::value_error(
                        "Cannot use both a mapping object and keyword args");
                if (has_kwargs) {
                    py::dict newd;
                    for (auto item : kwargs) {
                        std::string key = "/" + py::cast<std::string>(item.first);
                        newd[py::str(key.c_str())] = item.second;
                    }
                    return py::cast(
                        QPDFObjectHandle::newDictionary(dict_builder(newd)));
                }
                if (py::isinstance<QPDFObjectHandle>(d)) {
                    auto &oh = py::cast<QPDFObjectHandle &>(d);
                    if (oh.isDictionary())
                        return d.attr("__copy__")();
                }
                int truthy = PyObject_IsTrue(d.ptr());
                if (truthy < 0)
                    throw py::python_error();
                if (!truthy) // None or empty mapping -> empty dictionary
                    return py::cast(QPDFObjectHandle::newDictionary({}));
                py::dict dd;
                try {
                    dd = py::cast<py::dict>(d);
                } catch (const py::cast_error &) {
                    // Mirror the old Python facade, which iterated d.keys():
                    // a non-mapping (e.g. a list) raises AttributeError.
                    if (!py::hasattr(d, "keys"))
                        throw py::attribute_error("object has no attribute 'keys'");
                    throw py::type_error(
                        "Dictionary must be constructed from a dict with "
                        "'/'-prefixed string keys");
                }
                for (auto item : dd) {
                    std::string key = py::cast<std::string>(item.first);
                    if (key.empty() || key[0] != '/' || key == "/")
                        throw py::key_error(
                            "Dictionary created from strings must begin "
                            "with '/'");
                }
                return py::cast(QPDFObjectHandle::newDictionary(dict_builder(dd)));
            },
            py::arg("cls"),
            py::arg("d") = py::none(),
            py::arg("kwargs"));
        set_new(ns, fn);
        m.attr("Dictionary") =
            make_facade(object_meta, "Dictionary", ObjectType.attr("dictionary"), ns);
    }

    // ---- Stream ----  (capture Dictionary to build the stream dict)
    {
        py::object DictionaryT = m.attr("Dictionary");
        py::dict ns;
        py::object fn = py::cpp_function(
            [DictionaryT](py::handle cls,
                py::object owner,
                py::object data,
                py::object d,
                py::kwargs kwargs) -> py::object {
                if (data.is_none())
                    throw py::type_error("Must make Stream from binary data");
                py::object stream_dict = py::none();
                bool have_dict = (!d.is_none()) || (py::len(kwargs) > 0);
                if (have_dict)
                    stream_dict = DictionaryT(d, **kwargs);

                QPDF &q = py::cast<QPDF &>(owner);
                QPDFObjectHandle s;
                {
                    QpdfLockGuard lock(&q);
                    s = QPDFObjectHandle::newStream(&q, to_string(data));
                }
                py::object pys = py::cast(s);
                if (!stream_dict.is_none())
                    pys.attr("stream_dict") = stream_dict;
                return pys;
            },
            py::arg("cls"),
            py::arg("owner"),
            py::arg("data") = py::none(),
            py::arg("d") = py::none(),
            py::arg("kwargs"));
        set_new(ns, fn);
        m.attr("Stream") =
            make_facade(object_meta, "Stream", ObjectType.attr("stream"), ns);
    }

    // ---- Integer ----
    // Integer/Boolean/Real __new__ route newly-constructed handles through
    // py::cast(), which invokes the conversion-mode type_caster: a native
    // int/bool/Decimal in implicit mode and a pikepdf.Object in explicit mode
    // (see pikepdf.h type_caster). An already-typed argument is returned as the
    // same Python object to preserve identity (mirroring the old facade).
    {
        py::dict ns;
        py::object fn = py::cpp_function(
            [](py::handle cls, py::object val) -> py::object {
                // Passthrough: return the same Python object to preserve
                // identity, mirroring the old Python facade (val is val).
                if (py::isinstance<QPDFObjectHandle>(val)) {
                    auto &oh = py::cast<QPDFObjectHandle &>(val);
                    if (oh.isInteger())
                        return py::borrow(val);
                }
                // Construction: route through the conversion-mode type_caster
                // (py::cast) so implicit mode yields a native int.
                if (PyLong_Check(val.ptr()))
                    return py::cast(
                        QPDFObjectHandle::newInteger(pdf_integer_from_pylong(val)));
                try {
                    return py::cast(
                        QPDFObjectHandle::newInteger(py::cast<long long>(val)));
                } catch (const py::cast_error &) {
                    throw py::type_error("Integer requires an integer value");
                }
            },
            py::arg("cls"),
            py::arg("val"));
        set_new(ns, fn);
        m.attr("Integer") =
            make_facade(object_meta, "Integer", ObjectType.attr("integer"), ns);
    }

    // ---- Boolean ----
    {
        py::dict ns;
        py::object fn = py::cpp_function(
            [](py::handle cls, py::object val) -> py::object {
                if (py::isinstance<QPDFObjectHandle>(val)) {
                    auto &oh = py::cast<QPDFObjectHandle &>(val);
                    if (oh.isBool())
                        return py::borrow(val);
                }
                try {
                    return py::cast(QPDFObjectHandle::newBool(py::cast<bool>(val)));
                } catch (const py::cast_error &) {
                    throw py::type_error("Boolean requires a boolean value");
                }
            },
            py::arg("cls"),
            py::arg("val"));
        set_new(ns, fn);
        m.attr("Boolean") =
            make_facade(object_meta, "Boolean", ObjectType.attr("boolean"), ns);
    }

    // ---- Real ----
    {
        py::dict ns;
        py::object fn = py::cpp_function(
            [](py::handle cls, py::object val, unsigned int places) -> py::object {
                if (py::isinstance<QPDFObjectHandle>(val)) {
                    auto &oh = py::cast<QPDFObjectHandle &>(val);
                    if (oh.isReal())
                        return py::borrow(val);
                }
                if (py::isinstance<py::float_>(val))
                    return py::cast(
                        QPDFObjectHandle::newReal(py::cast<double>(val), places));
                return py::cast(
                    QPDFObjectHandle::newReal(py::cast<std::string>(py::str(val))));
            },
            py::arg("cls"),
            py::arg("val"),
            py::arg("places") = 6);
        set_new(ns, fn);
        m.attr("Real") = make_facade(object_meta, "Real", ObjectType.attr("real"), ns);
    }
}
