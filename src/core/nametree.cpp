// SPDX-FileCopyrightText: 2022 James R. Barlow
// SPDX-License-Identifier: MPL-2.0

#include <qpdf/Constants.h>
#include <qpdf/DLL.h>
#include <qpdf/QPDFExc.hh>
#include <qpdf/QPDFNameTreeObjectHelper.hh>
#include <qpdf/Types.h>

#include <nanobind/make_iterator.h>

#include "pikepdf.h"

using NameTree = QPDFNameTreeObjectHelper;

void init_nametree(py::module_ &m)
{
    py::class_<NameTree, QPDFObjectHelper>(m, "NameTree")
        .def(
            "__init__",
            [](NameTree *self, QPDFObjectHandle &oh, bool auto_repair) {
                if (!oh.getOwningQPDF())
                    throw py::value_error(
                        "NameTree must wrap a Dictionary that is owned by a Pdf");
                new (self) NameTree(oh, *oh.getOwningQPDF(), auto_repair);
            },
            py::arg("oh"), // LCOV_EXCL_LINE
            py::kw_only(), // LCOV_EXCL_LINE
            py::arg("auto_repair") = true,
            py::keep_alive<0, 1>())
        .def_static(
            "new",
            [](QPDF &pdf, bool auto_repair = true) {
                return NameTree::newEmpty(pdf, auto_repair);
            },
            py::arg("pdf"), // LCOV_EXCL_LINE
            py::kw_only(),
            py::arg("auto_repair") = true,
            py::keep_alive<0, 1>())
        .def_prop_ro("obj", [](NameTree &nt) { return nt.getObjectHandle(); })
        .def(
            "__eq__",
            [](NameTree &self, NameTree &other) {
                return objecthandle_equal(
                    self.getObjectHandle(), other.getObjectHandle());
            },
            py::is_operator())
        .def("__contains__",
            [](NameTree &nt, std::string const &name) { return nt.hasName(name); })
        .def("__getitem__",
            [](NameTree &nt, std::string const &name) {
                QPDFObjectHandle oh;
                if (nt.findObject(name, oh)) // writes to 'oh'
                    return oh;
                else
                    throw py::key_error(name.c_str());
            })
        .def("__setitem__",
            [](NameTree &nt, std::string const &name, QPDFObjectHandle oh) {
                nt.insert(name, oh);
            })
        .def("__setitem__",
            [](NameTree &nt, std::string const &name, py::object obj) {
                auto oh = objecthandle_encode(obj);
                nt.insert(name, oh);
            })
        .def("__delitem__",
            [](NameTree &nt, std::string const &name) {
                bool result = nt.remove(name);
                if (!result)
                    throw py::key_error(name.c_str());
            })
        .def(
            "__iter__",
            [](py::handle self) {
                auto &nt = py::cast<NameTree &>(self);
                return py::make_key_iterator(
                    py::type<NameTree>(), "key_iterator", nt.begin(), nt.end());
            },
            py::keep_alive<0, 1>())
        .def(
            "_as_map",
            [](NameTree &nt) { return nt.getAsMap(); },
            py::rv_policy::reference_internal)
        .def("__len__", [](NameTree &nt) { return nt.getAsMap().size(); });
}
