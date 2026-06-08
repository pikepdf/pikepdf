// SPDX-FileCopyrightText: 2025 James R. Barlow
// SPDX-License-Identifier: MPL-2.0

#include "pikepdf.h"

#include "namepath.h"

NamePath::NamePath(std::vector<PathComponent> components)
    : components_(std::move(components))
{
}

NamePath NamePath::append_name(std::string const &name) const
{
    auto new_components = components_;
    // Ensure name starts with /
    if (!name.empty() && name[0] != '/') {
        new_components.push_back("/" + name);
    } else {
        new_components.push_back(name);
    }
    return NamePath(std::move(new_components));
}

NamePath NamePath::append_index(int index) const
{
    auto new_components = components_;
    new_components.push_back(index);
    return NamePath(std::move(new_components));
}

std::string NamePath::format_path(size_t up_to) const
{
    std::ostringstream ss;
    ss << "NamePath";
    for (size_t i = 0; i < up_to && i < components_.size(); ++i) {
        if (std::holds_alternative<std::string>(components_[i])) {
            auto const &name = std::get<std::string>(components_[i]);
            // Strip leading / for display
            if (!name.empty() && name[0] == '/') {
                ss << "." << name.substr(1);
            } else {
                ss << "." << name;
            }
        } else {
            ss << "[" << std::get<int>(components_[i]) << "]";
        }
    }
    return ss.str();
}

std::string NamePath::format_full() const
{
    return format_path(components_.size());
}

void init_namepath(py::module_ &m)
{
    py::class_<NamePath>(m, "_NamePath", py::type_slots(pikepdf_gc_slots))
        .def(py::init<>())
        .def("__init__",
            [](NamePath *self, py::args args) {
                std::vector<PathComponent> components;
                for (auto const &arg : args) {
                    if (py::isinstance<py::str>(arg)) {
                        auto s = py::cast<std::string>(arg);
                        // Ensure name starts with /
                        if (!s.empty() && s[0] != '/') {
                            components.push_back("/" + s);
                        } else {
                            components.push_back(s);
                        }
                    } else if (py::isinstance<py::int_>(arg)) {
                        components.push_back(py::cast<int>(arg));
                    } else {
                        // Try to cast to QPDFObjectHandle (Name object)
                        try {
                            auto h = py::cast<QPDFObjectHandle>(arg);
                            if (h.isName()) {
                                components.push_back(h.getName());
                                continue;
                            }
                        } catch (const py::cast_error &) { // LCOV_EXCL_LINE
                            // Not a QPDFObjectHandle
                        }
                        throw py::type_error(
                            "NamePath components must be str, int, or Name");
                    }
                }
                new (self) NamePath(std::move(components));
            })
        .def("_append_name", &NamePath::append_name)
        .def("_append_index", &NamePath::append_index)
        .def("_format_path", &NamePath::format_path)
        .def("__repr__", &NamePath::format_full)
        .def("__len__", &NamePath::size)
        .def("__bool__", [](NamePath const &p) { return !p.empty(); })
        .def("_is_empty", &NamePath::empty)
        // __call__ for chaining: path('/A') returns new path with /A appended
        .def("__call__",
            [](NamePath const &p, py::object arg) {
                if (py::isinstance<py::str>(arg)) {
                    return p.append_name(py::cast<std::string>(arg));
                } else if (py::isinstance<py::int_>(arg)) {
                    return p.append_index(py::cast<int>(arg));
                } else {
                    // Try to cast to QPDFObjectHandle (Name object)
                    try {
                        auto h = py::cast<QPDFObjectHandle>(arg);
                        if (h.isName()) {
                            return p.append_name(h.getName());
                        }
                    } catch (const py::cast_error &) { // LCOV_EXCL_LINE
                        // Not a QPDFObjectHandle
                    }
                }
                throw py::type_error("NamePath argument must be str, int, or Name");
            })
        // __getitem__ for array index syntax: path[0]
        .def("__getitem__",
            [](NamePath const &p, int index) { return p.append_index(index); })
        // __getattr__ for name syntax: path.Resources
        .def("__getattr__", [](NamePath const &p, std::string const &name) {
            if (name.empty() || name[0] == '_') {
                throw py::attribute_error(name.c_str());
            }
            return p.append_name(name);
        });

    // The metaclass is built via type(...) + py::is_method() dunders rather
    // than PyType_FromSpec, for the reasons documented at the top of
    // object_construct.cpp (TODO(py>=3.12): switch to PyType_FromMetaclass).

    // Capture the registered _NamePath type so __call__ can delegate to its
    // multi-arg __init__ (handles NamePath('/A', '/B'), NamePath(Name.A), ...).
    py::object NamePathT = m.attr("_NamePath");

    // ---- _NamePathMeta(type) ----
    py::dict meta_ns;
    // NamePath.Foo -> NamePath().append_name("Foo"); fallback-only __getattr__.
    meta_ns["__getattr__"] = py::cpp_function(
        [](py::handle cls, std::string attr) -> py::object {
            if (!attr.empty() && attr[0] == '_')
                throw py::attribute_error(attr.c_str());
            return py::cast(NamePath().append_name(attr));
        },
        py::is_method(),
        py::arg("attr"));
    // NamePath['/A'] / NamePath[0] / NamePath[Name.A]
    meta_ns["__getitem__"] = py::cpp_function(
        [](py::handle cls, py::object item) -> py::object {
            if (py::isinstance<py::str>(item))
                return py::cast(NamePath().append_name(py::cast<std::string>(item)));
            if (py::isinstance<py::int_>(item))
                return py::cast(NamePath().append_index(py::cast<int>(item)));
            if (py::isinstance<QPDFObjectHandle>(item)) {
                auto &oh = py::cast<QPDFObjectHandle &>(item);
                if (oh.isName())
                    return py::cast(NamePath().append_name(oh.getName()));
            }
            throw py::type_error("NamePath key must be str, int, or Name");
        },
        py::is_method(),
        py::arg("item"));
    // NamePath() / NamePath('/A', '/B') -> _NamePath(*args)
    meta_ns["__call__"] = py::cpp_function(
        [NamePathT](py::handle cls, py::args args) -> py::object {
            PyObject *r = PyObject_Call(NamePathT.ptr(), args.ptr(), nullptr);
            if (r == nullptr)
                throw py::python_error();
            return py::steal(r);
        },
        py::is_method());

    py::tuple meta_bases = py::make_tuple(py::handle((PyObject *)&PyType_Type));
    py::object namepath_meta = py::steal(PyObject_CallFunction((PyObject *)&PyType_Type,
        "sOO",
        "_NamePathMeta",
        meta_bases.ptr(),
        meta_ns.ptr()));
    if (!namepath_meta)
        throw py::python_error();

    // ---- NamePath facade (instance of _NamePathMeta) ----
    py::dict ns;
    ns["__module__"] = py::str("pikepdf._core");
    ns["__qualname__"] = py::str("NamePath");
    ns["__doc__"] = py::str(R"(Path for accessing nested Dictionary/Stream values.

    NamePath provides ergonomic access to deeply nested PDF structures with a
    single access operation and helpful error messages when keys are not found.

    Usage examples::

        # Shorthand syntax - most common
        obj[NamePath.Resources.Font.F1]

        # With array indices
        obj[NamePath.Pages.Kids[0].MediaBox]

        # Chained access - supports non Python-identifier names
        NamePath['/A']('/B').C[0]  # equivalent to NamePath.A.B.C[0]

        # Alternate syntax to support lists
        obj[NamePath(Name.Resources, Name.Font)]

        # Using string objects
        obj[NamePath('/Resources', '/Weird-Name')]

        # Empty path returns the object itself
        obj[NamePath()]

        # Setting nested values (all parents must exist)
        obj[NamePath.Root.Info.Title] = pikepdf.String("Test")

        # With default value
        obj.get(NamePath.Root.Metadata, None)

    When a key is not found, the KeyError message identifies the exact failure
    point, e.g.: "Key /C not found; traversed NamePath.A.B"

    .. versionadded:: 10.1
    )");
    py::tuple bases = py::make_tuple(py::handle((PyObject *)&PyBaseObject_Type));
    py::object NamePathFacade = py::steal(PyObject_CallFunction(
        namepath_meta.ptr(), "sOO", "NamePath", bases.ptr(), ns.ptr()));
    if (!NamePathFacade)
        throw py::python_error();
    m.attr("NamePath") = NamePathFacade;
}
