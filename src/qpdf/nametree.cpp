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
#include <qpdf/QPDFNameTreeObjectHelper.hh>

#include <pybind11/pybind11.h>
#include <pybind11/stl.h>

#include "pikepdf.h"

void init_nametree(py::module_ &m)
{
    py::class_<QPDFNameTreeObjectHelper>(m, "NameTree")
        .def(py::init<QPDFObjectHandle>(), py::keep_alive<0, 1>())
        .def_property_readonly(
            "obj",
            [](QPDFNameTreeObjectHelper &nt) { return nt.getObjectHandle(); },
            "Returns the underlying root object for this name tree.")
        .def(
            "__contains__",
            [](QPDFNameTreeObjectHelper &nt, std::string const &name) {
                return nt.hasName(name);
            },
            R"~~~(
            Returns True if the name tree contains the specified name.

            Args:
                name (str or bytes): The name to search for in the name tree.
                    This is not a PDF /Name object, but an arbitrary key.
                    If name is a *str*, we search the name tree for the UTF-8
                    encoded form of name. If *bytes*, we search for a key
                    equal to those bytes.
            )~~~")
        .def("__getitem__",
            [](QPDFNameTreeObjectHelper &nt, std::string const &name) {
                QPDFObjectHandle oh;
                if (nt.findObject(name, oh))
                    return py::cast(oh);
                else
                    throw py::key_error(name);
            })
        .def("_as_map", [](QPDFNameTreeObjectHelper &nt) { return nt.getAsMap(); });
}
