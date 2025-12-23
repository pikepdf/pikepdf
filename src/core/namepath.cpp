// SPDX-FileCopyrightText: 2025 James R. Barlow
// SPDX-License-Identifier: MPL-2.0

#include "namepath.h"

#include "pikepdf.h"

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
    py::class_<NamePath>(m, "_NamePath")
        .def(py::init<>())
        .def(py::init([](py::args args) {
            std::vector<PathComponent> components;
            for (auto const &arg : args) {
                if (py::isinstance<py::str>(arg)) {
                    auto s = arg.cast<std::string>();
                    // Ensure name starts with /
                    if (!s.empty() && s[0] != '/') {
                        components.push_back("/" + s);
                    } else {
                        components.push_back(s);
                    }
                } else if (py::isinstance<py::int_>(arg)) {
                    components.push_back(arg.cast<int>());
                } else {
                    // Try to cast to QPDFObjectHandle (Name object)
                    try {
                        auto h = arg.cast<QPDFObjectHandle>();
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
            return NamePath(std::move(components));
        }))
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
                    return p.append_name(arg.cast<std::string>());
                } else if (py::isinstance<py::int_>(arg)) {
                    return p.append_index(arg.cast<int>());
                } else {
                    // Try to cast to QPDFObjectHandle (Name object)
                    try {
                        auto h = arg.cast<QPDFObjectHandle>();
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
                throw py::attribute_error(name);
            }
            return p.append_name(name);
        });
}
