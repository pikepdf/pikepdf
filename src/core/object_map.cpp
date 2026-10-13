// SPDX-FileCopyrightText: 2022 James R. Barlow
// SPDX-License-Identifier: MPL-2.0

// Binding for ObjectMap ("_ObjectMapping"), a
// std::map<std::string, QPDFObjectHandle>.

#include "object.h"
#include "pikepdf.h"

#include <string>

#include <qpdf/QPDFObjectHandle.hh>

// Normalize an _ObjectMapping key: a str, or a pikepdf.Name spelled the way it
// appears as a key. Returns false if the key is neither.
static bool objectmap_key(py::handle key, std::string &out)
{
    if (py::isinstance<py::str>(key)) {
        out = py::cast<std::string>(key);
        return true;
    }
    if (py::isinstance<QPDFObjectHandle>(key)) {
        auto handle = py::cast<QPDFObjectHandle>(key);
        if (handle.isName()) {
            out = handle.getName();
            return true;
        }
    }
    return false;
}

// Normalize an _ObjectMapping key, for the methods that address a single entry
// and so have no sensible answer for a key that cannot name one.
static std::string objectmap_key_or_raise(py::handle key)
{
    std::string name;
    if (!objectmap_key(key, name))
        throw py::type_error("_ObjectMapping keys must be str or pikepdf.Name");
    return name;
}

// Interpret `other` as a mapping of PDF objects, for comparison or update().
// Returns false if it is not a mapping, or if any key or value has no PDF
// representation; the caller then reports NotImplemented or inequality.
static bool objectmap_coerce(py::handle other, ObjectMap &out)
{
    if (py::isinstance<ObjectMap>(other)) {
        out = py::cast<ObjectMap>(other);
        return true;
    }
    if (!py::isinstance<py::dict>(other))
        return false;
    for (auto [key, value] : py::borrow<py::dict>(other)) {
        std::string name;
        QPDFObjectHandle encoded;
        if (!objectmap_key(key, name) || !pdfobject_try_encode(value, encoded))
            return false;
        out.emplace(name, encoded);
    }
    return true;
}

static bool objectmap_equal(const ObjectMap &self, const ObjectMap &other)
{
    if (self.size() != other.size())
        return false;
    for (const auto &[key, value] : self) {
        auto it = other.find(key);
        if (it == other.end() || !pdfobject_equal_locked(value, it->second))
            return false;
    }
    return true;
}

void init_object_map(py::module_ &m)
{
    // The methods defined here lock the mapping itself, as bind_map's own do,
    // and for the same reasons as _ObjectList in object_list.cpp they convert
    // and compare objects before, or on a copy of, the mapping.
    auto objectmapping =
        py::bind_map<ObjectMap>(m, "_ObjectMapping", py::type_slots(pikepdf_gc_slots));

    // Same treatment as _ObjectList in object_list.cpp: bind_map's __eq__/__ne__
    // compare values with QPDFObjectHandle::operator== (identity), and its
    // __setitem__/update() only accept pikepdf.Object values, which a caller
    // cannot produce for the numbers that mappings routinely hold. Its key-based
    // methods accept only str, but pikepdf spells PDF dictionary keys as
    // pikepdf.Name, so those are replaced too.
    for (const char *method : {"__eq__",
             "__ne__",
             "__contains__",
             "__getitem__",
             "__setitem__",
             "__delitem__"})
        py::delattr(objectmapping, method);

    objectmapping
        .def(
            "__eq__",
            [](const ObjectMap &self, py::handle other) -> py::object {
                ObjectMap rhs;
                if (!objectmap_coerce(other, rhs))
                    return py::borrow<py::object>(py::handle(Py_NotImplemented));
                ObjectMap lhs = self;
                return py::cast(objectmap_equal(lhs, rhs));
            },
            py::lock_self(),
            py::arg().lock())
        .def(
            "__ne__",
            [](const ObjectMap &self, py::handle other) -> py::object {
                ObjectMap rhs;
                if (!objectmap_coerce(other, rhs))
                    return py::borrow<py::object>(py::handle(Py_NotImplemented));
                ObjectMap lhs = self;
                return py::cast(!objectmap_equal(lhs, rhs));
            },
            py::lock_self(),
            py::arg().lock())
        .def(
            "__contains__",
            [](const ObjectMap &self, py::handle key) {
                std::string name;
                // A key that cannot name an entry simply is not in the mapping,
                // the same way list.__contains__ does not raise.
                if (!objectmap_key(key, name))
                    return false;
                return self.find(name) != self.end();
            },
            py::lock_self())
        .def(
            "__getitem__",
            [](ObjectMap &self, py::handle key) {
                auto name = objectmap_key_or_raise(key);
                auto it = self.find(name);
                if (it == self.end())
                    throw py::key_error(name.c_str());
                // Return a copy of the handle rather than a reference into the
                // map: a QPDFObjectHandle is a shared_ptr wrapper, so the copy
                // still refers to the same PDF object, and it does not dangle
                // once the mapping -- often a temporary, as in
                // page.get_images()['/Im0'] -- goes away.
                return it->second;
            },
            py::lock_self())
        .def(
            "__setitem__",
            [](ObjectMap &self, py::handle key, py::handle value) {
                auto name = objectmap_key_or_raise(key);
                auto encoded = objecthandle_encode(value);
                self[name] = encoded;
            },
            py::lock_self())
        .def(
            "__delitem__",
            [](ObjectMap &self, py::handle key) {
                auto name = objectmap_key_or_raise(key);
                auto it = self.find(name);
                if (it == self.end())
                    throw py::key_error(name.c_str());
                self.erase(it);
            },
            py::lock_self())
        .def(
            "get",
            [](ObjectMap &self, py::handle key, py::handle default_) -> py::object {
                auto name = objectmap_key_or_raise(key);
                auto it = self.find(name);
                if (it == self.end())
                    return py::borrow<py::object>(default_);
                auto found = it->second;
                return py::cast(found);
            },
            py::lock_self(),
            py::arg("key"),
            py::arg("default").none() = py::none())
        .def(
            "update",
            [](ObjectMap &self, py::handle other) {
                ObjectMap parsed;
                if (!objectmap_coerce(other, parsed))
                    throw py::type_error(
                        "update() expects a mapping of str to pikepdf.Object");
                for (const auto &[key, value] : parsed)
                    self[key] = value;
            },
            py::lock_self());
}
