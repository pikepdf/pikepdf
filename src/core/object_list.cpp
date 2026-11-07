// SPDX-FileCopyrightText: 2022 James R. Barlow
// SPDX-License-Identifier: MPL-2.0

// Binding for ObjectList ("_ObjectList"), a std::vector<QPDFObjectHandle>.

#include "object.h"
#include "pikepdf.h"

#include <string>

#include <qpdf/QPDFObjectHandle.hh>

// nanobind's bind_vector and bind_map generate methods whose value parameters
// are typed strictly on QPDFObjectHandle, and that compare values with
// QPDFObjectHandle::operator==, which only reports whether two handles refer to
// the same underlying object. Neither suits pikepdf: every other container here
// accepts any Python value that objecthandle_encode() understands, and compares
// objects by value with objecthandle_equal(). These helpers back the
// replacement methods installed after bind_vector() in init_object_list();
// object_map.cpp does the same for bind_map().

// Interpret `other` as a list of PDF objects for element-wise comparison.
// Returns false if it is not a list-like object, or if any element has no PDF
// representation; the caller then reports NotImplemented or inequality.
static bool objectlist_coerce(py::handle other, ObjectList &out)
{
    if (py::isinstance<ObjectList>(other)) {
        out = py::cast<ObjectList>(other);
        return true;
    }
    if (!py::isinstance<py::list>(other) && !py::isinstance<py::tuple>(other))
        return false;
    for (py::handle item : py::borrow<py::sequence>(other)) {
        QPDFObjectHandle encoded;
        if (!pdfobject_try_encode(item, encoded))
            return false;
        out.push_back(encoded);
    }
    return true;
}

static bool objectlist_equal(const ObjectList &self, const ObjectList &other)
{
    if (self.size() != other.size())
        return false;
    for (size_t i = 0; i < self.size(); ++i) {
        if (!pdfobject_equal_locked(self.at(i), other.at(i)))
            return false;
    }
    return true;
}

// Encode every element of a Python iterable, or raise.
static ObjectList objectlist_encode_all(py::iterable values)
{
    ObjectList result;
    for (py::handle item : values)
        result.push_back(objecthandle_encode(item));
    return result;
}

void init_object_list(py::module_ &m)
{
    // LCOV_EXCL_START - gcov misattributes lines inside this lambda; covered by
    // tests/test_objectlist.py::test_objectlist_repr
    //
    // A list belongs to no Pdf, so on a free-threaded build it is protected
    // as bind_vector protects the methods it generates: each method locks the
    // list itself, with py::lock_self(). That lock is a critical section,
    // which is given up whenever the thread blocks or runs Python code, as it
    // may while it compares or converts an object. So the methods below do
    // that work on a copy of the list, or before they touch it, and never
    // hold an iterator into the list across it.
    auto objectlist =
        py::bind_vector<ObjectList>(m, "_ObjectList", py::type_slots(pikepdf_gc_slots));
    objectlist.def(
        "__repr__",
        [](ObjectList &ol) {
            ObjectList items = ol;
            std::string s = "pikepdf._core._ObjectList([";
            const char *sep = "";
            for (auto &h : items) {
                s += sep;
                sep = ", ";
                s += objecthandle_repr(h);
            }
            s += "])";
            return s;
        },
        py::lock_self());
    // LCOV_EXCL_STOP

    // Discard the comparison methods bind_vector generated, so that the
    // replacements below become the only overloads instead of being appended
    // behind bind_vector's stricter and identity-based ones.
    for (const char *method : {"__eq__", "__ne__", "__contains__", "count", "remove"})
        py::delattr(objectlist, method);

    objectlist
        .def(
            "__eq__",
            [](const ObjectList &self, py::handle other) -> py::object {
                ObjectList rhs;
                if (!objectlist_coerce(other, rhs))
                    return py::borrow<py::object>(py::handle(Py_NotImplemented));
                ObjectList lhs = self;
                return py::cast(objectlist_equal(lhs, rhs));
            },
            py::lock_self(),
            py::arg().lock())
        .def(
            "__ne__",
            [](const ObjectList &self, py::handle other) -> py::object {
                ObjectList rhs;
                if (!objectlist_coerce(other, rhs))
                    return py::borrow<py::object>(py::handle(Py_NotImplemented));
                ObjectList lhs = self;
                return py::cast(!objectlist_equal(lhs, rhs));
            },
            py::lock_self(),
            py::arg().lock())
        .def(
            "__contains__",
            [](const ObjectList &self, py::handle value) {
                QPDFObjectHandle needle;
                if (!pdfobject_try_encode(value, needle))
                    return false;
                ObjectList items = self;
                for (auto &item : items) {
                    if (pdfobject_equal_locked(item, needle))
                        return true;
                }
                return false;
            },
            py::lock_self())
        .def(
            "count",
            [](const ObjectList &self, py::handle value) {
                QPDFObjectHandle needle;
                Py_ssize_t count = 0;
                if (!pdfobject_try_encode(value, needle))
                    return count;
                ObjectList items = self;
                for (auto &item : items) {
                    if (pdfobject_equal_locked(item, needle))
                        count++;
                }
                return count;
            },
            py::lock_self(),
            py::arg("value"),
            "Return number of occurrences of `value`.")
        .def(
            "remove",
            [](ObjectList &self, py::handle value) {
                QPDFObjectHandle needle;
                if (pdfobject_try_encode(value, needle)) {
                    ObjectList items = self;
                    for (auto &item : items) {
                        if (!pdfobject_equal_locked(item, needle))
                            continue;
                        // The list may have changed during the comparison,
                        // so find the item that matched again, by identity.
                        for (auto it = self.begin(); it != self.end(); ++it) {
                            if (it->isSameObjectAs(item)) {
                                self.erase(it);
                                return;
                            }
                        }
                    }
                }
                throw py::value_error("_ObjectList.remove(x): x not in list");
            },
            py::lock_self(),
            py::arg("value"),
            "Remove first occurrence of `value`.");

    // Overloads that accept any encodable Python value. bind_vector's
    // QPDFObjectHandle-typed versions are registered first and still handle
    // pikepdf.Object arguments; these pick up everything else, which also stops
    // nanobind from falling back to converting the argument to an _ObjectList
    // (a conversion that fails noisily on stderr). Fixes #742.
    objectlist
        .def(
            "append",
            [](ObjectList &self, py::handle value) {
                auto encoded = objecthandle_encode(value);
                self.push_back(encoded);
            },
            py::lock_self())
        .def(
            "insert",
            [](ObjectList &self, Py_ssize_t index, py::handle value) {
                auto encoded = objecthandle_encode(value);
                if (index < 0)
                    index += (Py_ssize_t)self.size();
                if (index < 0 || (size_t)index > self.size())
                    throw py::index_error();
                self.insert(self.begin() + index, encoded);
            },
            py::lock_self())
        .def(
            "extend",
            [](ObjectList &self, py::iterable values) {
                ObjectList encoded = objectlist_encode_all(values);
                self.insert(self.end(), encoded.begin(), encoded.end());
            },
            py::lock_self())
        .def(
            "__setitem__",
            [](ObjectList &self, Py_ssize_t index, py::handle value) {
                auto encoded = objecthandle_encode(value);
                self.at(py::detail::wrap(index, self.size())) = encoded;
            },
            py::lock_self())
        .def(
            "__setitem__",
            [](ObjectList &self, const py::slice &slice, py::iterable values) {
                ObjectList encoded = objectlist_encode_all(values);
                auto [start, stop, step, length] = slice.compute(self.size());
                if (length != encoded.size())
                    throw py::index_error("The left and right hand side of the "
                                          "slice assignment have mismatched sizes!");
                for (size_t i = 0; i < length; ++i) {
                    self.at((size_t)start) = encoded.at(i);
                    start += step;
                }
            },
            py::lock_self());
}
