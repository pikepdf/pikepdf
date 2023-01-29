// SPDX-FileCopyrightText: 2022 James R. Barlow
// SPDX-License-Identifier: MPL-2.0

#include <qpdf/Constants.h>
#include <qpdf/Types.h>
#include <qpdf/DLL.h>
#include <qpdf/QPDFExc.hh>
#include <qpdf/QPDFNumberTreeObjectHelper.hh>

#include <pybind11/pybind11.h>
#include <pybind11/stl.h>

#include "pikepdf.h"

using numtree_number = QPDFNumberTreeObjectHelper::numtree_number;

using NumberTree = QPDFNumberTreeObjectHelper;

void init_numbertree(py::module_ &m)
{
    py::class_<NumberTree, std::shared_ptr<NumberTree>, QPDFObjectHelper>(
        m, "NumberTree")
        .def(py::init([](QPDFObjectHandle &oh, bool auto_repair = true) {
            if (!oh.getOwningQPDF())
                throw py::value_error(
                    "NumberTree must wrap a Dictionary that is owned by a Pdf");
            return NumberTree(oh, *oh.getOwningQPDF(), auto_repair);
        }),
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
            py::keep_alive<0, 1>(),
            R"~~~(
                Create a new NumberTree in the provided Pdf.

                You will probably need to insert the number tree in the PDF's
                catalog. For example, to insert this number tree in 
                /Root /PageLabels:

                .. code-block:: python

                    nt = NumberTree.new(pdf)
                    pdf.Root.PageLabels = nt.obj
            )~~~")
        .def("__contains__",
            [](NumberTree &nt, numtree_number idx) { return nt.hasIndex(idx); })
        .def("__contains__", [](NumberTree &nt, py::object idx) { return false; })
        .def("__getitem__",
            [](NumberTree &nt, numtree_number key) {
                QPDFObjectHandle oh;
                if (nt.findObject(key, oh)) // writes to 'oh'
                    return oh;
                else
                    throw py::index_error(std::to_string(key));
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
            [](NumberTree &nt) { return py::make_key_iterator(nt); },
            py::return_value_policy::reference_internal)
        .def("_as_map", [](NumberTree &nt) { return nt.getAsMap(); })
        .def("__len__", [](NumberTree &nt) { return nt.getAsMap().size(); });
}
