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

void init_numbertree(py::module_ &m)
{
    py::class_<QPDFNumberTreeObjectHelper::iterator,
        std::shared_ptr<QPDFNumberTreeObjectHelper::iterator>>(m, "NumberTreeIterator")
        .def("__next__",
            [](QPDFNumberTreeObjectHelper::iterator &nti) {
                ++nti;
                return *nti;
            })
        .def("__iter__", [](QPDFNumberTreeObjectHelper::iterator &nti) { return nti; });

    py::class_<QPDFNumberTreeObjectHelper, std::shared_ptr<QPDFNumberTreeObjectHelper>>(
        m, "NumberTree")
        .def(py::init([](QPDFObjectHandle &oh, bool auto_repair = true) {
            return std::make_shared<QPDFNumberTreeObjectHelper>(
                oh, *oh.getOwningQPDF(), auto_repair);
        }),
            py::arg("oh"),
            py::kw_only(),
            py::arg("auto_repair") = true,
            py::keep_alive<0, 1>())
        .def_property_readonly(
            "obj",
            [](QPDFNumberTreeObjectHelper &nt) { return nt.getObjectHandle(); },
            "Returns the underlying root object for this name tree.")
        .def("_contains",
            [](QPDFNumberTreeObjectHelper &nt, numtree_number idx) {
                return nt.hasIndex(idx);
            })
        .def("_getitem",
            [](QPDFNumberTreeObjectHelper &nt, numtree_number key) {
                QPDFObjectHandle oh;
                if (nt.findObject(key, oh)) // writes to 'oh'
                    return oh;
                else
                    throw py::index_error(std::to_string(key));
            })
        .def("_setitem",
            [](QPDFNumberTreeObjectHelper &nt,
                numtree_number key,
                QPDFObjectHandle oh) { nt.insert(key, oh); })
        .def("_delitem",
            [](QPDFNumberTreeObjectHelper &nt, numtree_number key) { nt.remove(key); })
        .def(
            "_iter",
            [](QPDFNumberTreeObjectHelper &nt) { return nt.begin(); },
            py::keep_alive<0, 1>())
        .def("_as_map", [](QPDFNumberTreeObjectHelper &nt) { return nt.getAsMap(); });
}
