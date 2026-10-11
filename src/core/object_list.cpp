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
    auto objectlist =
        py::bind_vector<ObjectList>(m, "_ObjectList", py::type_slots(pikepdf_gc_slots));
    objectlist.def("__repr__", [](ObjectList &ol) {
        std::string s = "pikepdf._core._ObjectList([";
        const char *sep = "";
        for (auto &h : ol) {
            s += sep;
            sep = ", ";
            s += objecthandle_repr(h);
        }
        s += "])";
        return s;
    });
    // LCOV_EXCL_STOP

    // Discard the comparison methods bind_vector generated, so that the
    // replacements below become the only overloads instead of being appended
    // behind bind_vector's stricter and identity-based ones.
    for (const char *method : {"__eq__", "__ne__", "__contains__", "count", "remove"})
        py::delattr(objectlist, method);

    objectlist
        .def("__eq__",
            [](const ObjectList &self, py::handle other) -> py::object {
                ObjectList rhs;
                if (!objectlist_coerce(other, rhs))
                    return py::borrow<py::object>(py::handle(Py_NotImplemented));
                return py::cast(objectlist_equal(self, rhs));
            })
        .def("__ne__",
            [](const ObjectList &self, py::handle other) -> py::object {
                ObjectList rhs;
                if (!objectlist_coerce(other, rhs))
                    return py::borrow<py::object>(py::handle(Py_NotImplemented));
                return py::cast(!objectlist_equal(self, rhs));
            })
        .def("__contains__",
            [](const ObjectList &self, py::handle value) {
                QPDFObjectHandle needle;
                if (!pdfobject_try_encode(value, needle))
                    return false;
                for (auto &item : self) {
                    if (pdfobject_equal_locked(item, needle))
                        return true;
                }
                return false;
            })
        .def(
            "count",
            [](const ObjectList &self, py::handle value) {
                QPDFObjectHandle needle;
                Py_ssize_t count = 0;
                if (!pdfobject_try_encode(value, needle))
                    return count;
                for (auto &item : self) {
                    if (pdfobject_equal_locked(item, needle))
                        count++;
                }
                return count;
            },
            py::arg("value"),
            "Return number of occurrences of `value`.")
        .def(
            "remove",
            [](ObjectList &self, py::handle value) {
                QPDFObjectHandle needle;
                if (pdfobject_try_encode(value, needle)) {
                    for (auto it = self.begin(); it != self.end(); ++it) {
                        if (pdfobject_equal_locked(*it, needle)) {
                            self.erase(it);
                            return;
                        }
                    }
                }
                throw py::value_error("_ObjectList.remove(x): x not in list");
            },
            py::arg("value"),
            "Remove first occurrence of `value`.");

    // Overloads that accept any encodable Python value. bind_vector's
    // QPDFObjectHandle-typed versions are registered first and still handle
    // pikepdf.Object arguments; these pick up everything else, which also stops
    // nanobind from falling back to converting the argument to an _ObjectList
    // (a conversion that fails noisily on stderr). Fixes #742.
    objectlist
        .def("append",
            [](ObjectList &self, py::handle value) {
                self.push_back(objecthandle_encode(value));
            })
        .def("insert",
            [](ObjectList &self, Py_ssize_t index, py::handle value) {
                if (index < 0)
                    index += (Py_ssize_t)self.size();
                if (index < 0 || (size_t)index > self.size())
                    throw py::index_error();
                self.insert(self.begin() + index, objecthandle_encode(value));
            })
        .def("extend",
            [](ObjectList &self, py::iterable values) {
                ObjectList encoded = objectlist_encode_all(values);
                self.insert(self.end(), encoded.begin(), encoded.end());
            })
        .def("__setitem__",
            [](ObjectList &self, Py_ssize_t index, py::handle value) {
                self.at(py::detail::wrap(index, self.size())) =
                    objecthandle_encode(value);
            })
        .def("__setitem__",
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
            });
}
