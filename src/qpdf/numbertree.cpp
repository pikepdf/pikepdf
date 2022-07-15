/*
 * This Source Code Form is subject to the terms of the Mozilla Public
 * License, v. 2.0. If a copy of the MPL was not distributed with this
 * file, You can obtain one at http://mozilla.org/MPL/2.0/.
 *
 * Copyright (C) 2019, James R. Barlow (https://github.com/jbarlow83/)
 */

#include <qpdf/Constants.h>
#include <qpdf/Types.h>
#include <qpdf/DLL.h>
#include <qpdf/QPDFExc.hh>
#include <qpdf/PointerHolder.hh>
#include <qpdf/QPDFNumberTreeObjectHelper.hh>

#include <pybind11/pybind11.h>
#include <pybind11/stl.h>

#include "pikepdf.h"

using numtree_number = QPDFNumberTreeObjectHelper::numtree_number;

using NumberTree = QPDFNumberTreeObjectHelper;

void init_numbertree(py::module_ &m)
{
    py::class_<NumberTree, std::shared_ptr<NumberTree>>(m, "NumberTree")
        .def(py::init([](QPDFObjectHandle &oh, bool auto_repair = true) {
            if (!oh.getOwningQPDF())
                throw py::value_error(
                    "NumberTree must wrap a Dictionary that is owned by a Pdf");
            return std::make_shared<NumberTree>(oh, *oh.getOwningQPDF(), auto_repair);
        }),
            py::arg("oh"),
            py::kw_only(),
            py::arg("auto_repair") = true,
            py::keep_alive<0, 1>())
        .def_property_readonly(
            "obj",
            [](NumberTree &nt) { return nt.getObjectHandle(); },
            "Returns the underlying root object for this name tree.")
        .def("__contains__",
            [](NumberTree &nt, numtree_number idx) { return nt.hasIndex(idx); })
        .def("__contains__", [](NumberTree &nt, py::object idx) { return false; })
        .def(
            "__eq__",
            [](NumberTree &self, NumberTree &other) {
                auto self_obj  = self.getObjectHandle();
                auto other_obj = other.getObjectHandle();
                return self_obj.getOwningQPDF() == other_obj.getOwningQPDF() &&
                       self_obj.getObjGen() == other_obj.getObjGen();
            },
            py::is_operator())
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
        .def("__delitem__", [](NumberTree &nt, numtree_number key) { nt.remove(key); })
        .def(
            "__iter__",
            [](NumberTree &nt) { return py::make_key_iterator(nt); },
            py::return_value_policy::reference_internal)
        .def("_as_map", [](NumberTree &nt) { return nt.getAsMap(); })
        .def("__len__", [](NumberTree &nt) { return nt.getAsMap().size(); });
}
