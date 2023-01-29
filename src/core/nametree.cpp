// SPDX-FileCopyrightText: 2022 James R. Barlow
// SPDX-License-Identifier: MPL-2.0

#include <qpdf/Constants.h>
#include <qpdf/Types.h>
#include <qpdf/DLL.h>
#include <qpdf/QPDFExc.hh>
#include <qpdf/QPDFNameTreeObjectHelper.hh>

#include <pybind11/pybind11.h>
#include <pybind11/stl.h>

#include "pikepdf.h"

using NameTree = QPDFNameTreeObjectHelper;

void init_nametree(py::module_ &m)
{
    py::class_<NameTree, std::shared_ptr<NameTree>, QPDFObjectHelper>(m, "NameTree")
        .def(py::init([](QPDFObjectHandle &oh, bool auto_repair = true) {
            if (!oh.getOwningQPDF())
                throw py::value_error(
                    "NameTree must wrap a Dictionary that is owned by a Pdf");
            return NameTree(oh, *oh.getOwningQPDF(), auto_repair);
        }),
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
            py::keep_alive<0, 1>(),
            R"~~~(
                Create a new NameTree in the provided Pdf.

                You will probably need to insert the name tree in the PDF's
                catalog. For example, to insert this name tree in 
                /Root /Names /Dests:

                .. code-block:: python

                    nt = NameTree.new(pdf)
                    pdf.Root.Names.Dests = nt.obj
            )~~~")
        .def_property_readonly(
            "obj",
            [](NameTree &nt) { return nt.getObjectHandle(); },
            "Returns the underlying root object for this name tree.")
        .def(
            "__eq__",
            [](NameTree &self, NameTree &other) {
                return objecthandle_equal(
                    self.getObjectHandle(), other.getObjectHandle());
            },
            py::is_operator())
        .def_property_readonly(
            "_pikepdf_disallow_objecthandle_encode", [](NameTree &nt) { return true; })
        .def("__contains__",
            [](NameTree &nt, std::string const &name) { return nt.hasName(name); })
        .def("__getitem__",
            [](NameTree &nt, std::string const &name) {
                QPDFObjectHandle oh;
                if (nt.findObject(name, oh)) // writes to 'oh'
                    return oh;
                else
                    throw py::key_error(name);
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
                    throw py::key_error(name);
            })
        .def(
            "__iter__",
            [](NameTree &nt) { return py::make_key_iterator(nt); },
            py::return_value_policy::reference_internal)
        .def(
            "_as_map",
            [](NameTree &nt) { return nt.getAsMap(); },
            py::return_value_policy::reference_internal)
        .def("__len__", [](NameTree &nt) { return nt.getAsMap().size(); });
}
