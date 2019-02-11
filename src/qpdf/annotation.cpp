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
#include <qpdf/QPDFAnnotationObjectHelper.hh>

#include <pybind11/pybind11.h>
#include <pybind11/stl.h>

#include "pikepdf.h"


void init_annotation(py::module &m)
{
    py::class_<QPDFAnnotationObjectHelper>(m, "Annotation")
        .def(py::init<QPDFObjectHandle &>(), py::keep_alive<0, 1>())
        .def_property_readonly("subtype", &QPDFAnnotationObjectHelper::getSubtype)
        .def_property_readonly("flags", &QPDFAnnotationObjectHelper::getFlags)
        .def_property_readonly("appearance_state", &QPDFAnnotationObjectHelper::getAppearanceState)
        .def_property_readonly("appearance_dict", &QPDFAnnotationObjectHelper::getAppearanceDictionary)
        .def("get_appearance_stream",
            [](QPDFAnnotationObjectHelper& anno, QPDFObjectHandle& which, std::string const& state = "") {
                // if (!which.isName())
                //     throw py::type_error("which must be pikepdf.Name");
                return anno.getAppearanceStream(which.getName(), state);
            },
            py::arg("which"),
            py::arg("state") = ""
        )
        .def("get_page_content_for_appearance",
            [](QPDFAnnotationObjectHelper& anno, QPDFObjectHandle& name, int rotate, int required_flags, int forbidden_flags) {
                //auto name = name_.getName();
                return anno.getPageContentForAppearance(name.getName(), rotate, required_flags, forbidden_flags);
            },
            py::arg("name"),
            py::arg("rotate"),
            py::arg("required_flags") = 0,
            py::arg("forbidden_flags") = an_invisible | an_hidden
        )
        ;
}
