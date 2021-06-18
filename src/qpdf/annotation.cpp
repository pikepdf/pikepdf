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

void init_annotation(py::module_ &m)
{
    py::class_<QPDFAnnotationObjectHelper>(m, "Annotation")
        .def(py::init<QPDFObjectHandle &>(), py::keep_alive<0, 1>())
        .def_property_readonly(
            "obj",
            [](QPDFAnnotationObjectHelper &anno) { return anno.getObjectHandle(); },
            "Returns the underlying object for this annotation.")
        .def_property_readonly(
            "subtype",
            [](QPDFAnnotationObjectHelper &anno) {
                // Don't use QPDF because the method returns std::string
                return anno.getObjectHandle().getKey("/Subtype");
            },
            "Returns the subtype of this annotation.")
        .def_property_readonly("flags",
            &QPDFAnnotationObjectHelper::getFlags,
            "Returns the annotation's flags.")
        .def_property_readonly(
            "appearance_state",
            [](QPDFAnnotationObjectHelper &anno) {
                // Don't use QPDF because the method returns std::string
                auto key = anno.getObjectHandle().getKey("/AS");
                if (key.isName())
                    return key;
                return QPDFObjectHandle::newNull();
            },
            R"~~~(
            Returns the annotation's appearance state (or None).

            For a checkbox or radio button, the appearance state may be ``pikepdf.Name.On``
            or ``pikepdf.Name.Off``.
            )~~~")
        .def_property_readonly("appearance_dict",
            &QPDFAnnotationObjectHelper::getAppearanceDictionary,
            "Returns the annotations appearance dictionary.")
        .def(
            "get_appearance_stream",
            [](QPDFAnnotationObjectHelper &anno, QPDFObjectHandle &which) {
                return anno.getAppearanceStream(which.getName());
            },
            R"~~~(
            Returns one of the appearance streams associated with an annotation.

            Args:
                which: Usually one of ``pikepdf.Name.N``, ``pikepdf.Name.R`` or
                    ``pikepdf.Name.D``, indicating the normal, rollover or down
                    appearance stream, respectively. If any other name is passed, an
                    an appearance stream with that name is returned.
            )~~~",
            py::arg("which"))
        .def(
            "get_appearance_stream",
            [](QPDFAnnotationObjectHelper &anno,
                QPDFObjectHandle &which,
                QPDFObjectHandle &state) {
                return anno.getAppearanceStream(which.getName(), state.getName());
            },
            R"~~~(
            Returns one of the appearance streams associated with an annotation.

            Args:
                which: Usually one of ``pikepdf.Name.N``, ``pikepdf.Name.R`` or
                    ``pikepdf.Name.D``, indicating the normal, rollover or down
                    appearance stream, respectively. If any other name is passed, an
                    an appearance stream with that name is returned.
                state: The appearance state. For checkboxes or radio buttons, the
                    appearance state is usually whether the button is on or off.
            )~~~",
            py::arg("which"),
            py::arg("state"))
        .def(
            "get_page_content_for_appearance",
            [](QPDFAnnotationObjectHelper &anno,
                QPDFObjectHandle &name,
                int rotate,
                int required_flags,
                int forbidden_flags) {
                return py::bytes(anno.getPageContentForAppearance(
                    name.getName(), rotate, required_flags, forbidden_flags));
            },
            R"~~~(
            Generate content stream text that draws this annotation as a Form XObject.

            Args:
                name (pikepdf.Name): What to call the object we create.
                rotate: Should be set to the page's /Rotate value or 0.
            Note:
                This method is done mainly with QPDF. Its behavior may change when
                different QPDF versions are used.
            )~~~",
            py::arg("name"),
            py::arg("rotate"),
            py::arg("required_flags")  = 0,
            py::arg("forbidden_flags") = an_invisible | an_hidden);
}
