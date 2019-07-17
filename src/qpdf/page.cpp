/*
 * This Source Code Form is subject to the terms of the Mozilla Public
 * License, v. 2.0. If a copy of the MPL was not distributed with this
 * file, You can obtain one at http://mozilla.org/MPL/2.0/.
 *
 * Copyright (C) 2017, James R. Barlow (https://github.com/jbarlow83/)
 */

#include <sstream>
#include <iostream>
#include <iomanip>
#include <cctype>

#include <qpdf/DLL.h>
#include <qpdf/QPDFPageObjectHelper.hh>

#include <pybind11/pybind11.h>
#include <pybind11/stl.h>

#include "pikepdf.h"


void init_page(py::module& m)
{
    py::class_<QPDFPageObjectHelper>(m, "Page")
        .def(py::init<QPDFObjectHandle &>())
        .def_property_readonly("obj",
            [](QPDFPageObjectHelper &poh) {
                return poh.getObjectHandle();
            }
        )
        .def_property_readonly("images", &QPDFPageObjectHelper::getPageImages)
        .def("externalize_inline_images", &QPDFPageObjectHelper::externalizeInlineImages)
        .def("rotate", &QPDFPageObjectHelper::rotatePage)
        .def("page_contents_coalesce", &QPDFPageObjectHelper::coalesceContentStreams)
        .def("_parse_page_contents", &QPDFPageObjectHelper::parsePageContents)
        .def("remove_unreferenced_resources", &QPDFPageObjectHelper::removeUnreferencedResources)
        .def("as_form_xobject", &QPDFPageObjectHelper::getFormXObjectForPage)
        ;
}
