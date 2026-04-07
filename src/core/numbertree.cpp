// SPDX-FileCopyrightText: 2022 James R. Barlow
// SPDX-License-Identifier: MPL-2.0

#include <qpdf/Constants.h>
#include <qpdf/DLL.h>
#include <qpdf/QPDFExc.hh>
#include <qpdf/QPDFNumberTreeObjectHelper.hh>
#include <qpdf/Types.h>

#include <nanobind/make_iterator.h>

#include "pikepdf.h"

using numtree_number = QPDFNumberTreeObjectHelper::numtree_number;

using NumberTree = QPDFNumberTreeObjectHelper;

void init_numbertree(py::module_ &m)
{
    py::class_<NumberTree, QPDFObjectHelper>(m, "NumberTree")
        .def(
            "__init__",
            [](NumberTree *self, QPDFObjectHandle &oh, bool auto_repair) {
                if (!oh.getOwningQPDF())
                    throw py::value_error(
                        "NumberTree must wrap a Dictionary that is owned by a Pdf");
                new (self) NumberTree(oh, *oh.getOwningQPDF(), auto_repair);
            },
            py::arg("oh"), // LCOV_EXCL_LINE
            py::kw_only(),
            py::arg("auto_repair") = true,
            py::keep_alive<0, 1>())
        .def_static(
            "new",
            [](QPDF &pdf, bool auto_repair = true) {
                return NumberTree::newEmpty(pdf, auto_repair);
            },
            py::arg("pdf"), // LCOV_EXCL_LINE
            py::kw_only(),
            py::arg("auto_repair") = true,
            py::keep_alive<0, 1>())
        .def("__contains__",
            [](NumberTree &nt, numtree_number idx) { return nt.hasIndex(idx); })
        .def("__contains__", [](NumberTree &nt, py::object idx) { return false; })
        .def("__getitem__",
            [](NumberTree &nt, numtree_number key) {
                QPDFObjectHandle oh;
                if (nt.findObject(key, oh)) // writes to 'oh'
                    return oh;
                else
                    throw py::index_error(std::to_string(key).c_str());
            })
        .def("__setitem__",
            [](NumberTree &nt, numtree_number key, QPDFObjectHandle oh) {
                nt.insert(key, oh);
            })
        .def("__setitem__",
            [](NumberTree &nt, numtree_number key, py::object obj) {
                nt.insert(key, objecthandle_encode(obj));
            })
        .def("__delitem__", [](NumberTree &nt, numtree_number key) { nt.remove(key); })
        .def(
            "__iter__",
            [](py::handle self) {
                auto &nt = py::cast<NumberTree &>(self);
                return py::make_key_iterator(
                    py::type<NumberTree>(), "key_iterator", nt.begin(), nt.end());
            },
            py::keep_alive<0, 1>())
        .def("_as_map", [](NumberTree &nt) { return nt.getAsMap(); })
        .def("__len__", [](NumberTree &nt) { return nt.getAsMap().size(); });
}
