// SPDX-FileCopyrightText: 2022 James R. Barlow
// SPDX-License-Identifier: MPL-2.0

#include <qpdf/Constants.h>
#include <qpdf/DLL.h>
#include <qpdf/QPDFAnnotationObjectHelper.hh>
#include <qpdf/QPDFExc.hh>
#include <qpdf/Types.h>

#include "pikepdf.h"

void init_annotation(py::module_ &m)
{
    py::enum_<pdf_annotation_flag_e>(m, "AnnotationFlag", py::is_flag())
        .value("invisible", pdf_annotation_flag_e::an_invisible)
        .value("hidden", pdf_annotation_flag_e::an_hidden)
        .value("print", pdf_annotation_flag_e::an_print)
        .value("no_zoom", pdf_annotation_flag_e::an_no_zoom)
        .value("no_rotate", pdf_annotation_flag_e::an_no_rotate)
        .value("no_view", pdf_annotation_flag_e::an_no_view)
        .value("read_only", pdf_annotation_flag_e::an_read_only)
        .value("locked", pdf_annotation_flag_e::an_locked)
        .value("toggle_no_view", pdf_annotation_flag_e::an_toggle_no_view)
        .value("locked_contents", pdf_annotation_flag_e::an_locked_contents);

    py::class_<QPDFAnnotationObjectHelper, QPDFObjectHelper>(m, "Annotation")
        .def(py::init<QPDFObjectHandle &>(), py::keep_alive<0, 1>())
        .def_prop_ro("subtype",
            [](QPDFAnnotationObjectHelper &anno) {
                // Don't use qpdf because the method returns std::string
                return anno.getObjectHandle().getKey("/Subtype");
            })
        .def_prop_ro("rect", &QPDFAnnotationObjectHelper::getRect)
        .def_prop_ro("flags", &QPDFAnnotationObjectHelper::getFlags)
        .def_prop_ro("appearance_state",
            [](QPDFAnnotationObjectHelper &anno) {
                // Don't use qpdf because the method returns std::string
                auto key = anno.getObjectHandle().getKey("/AS");
                if (key.isName())
                    return key;
                return QPDFObjectHandle::newNull();
            })
        .def_prop_ro("appearance_dict",
            &QPDFAnnotationObjectHelper::getAppearanceDictionary // LCOV_EXCL_LINE
            )
        .def(
            "get_appearance_stream",
            [](QPDFAnnotationObjectHelper &anno, QPDFObjectHandle &which) {
                return anno.getAppearanceStream(which.getName());
            },
            py::arg("which"))
        .def(
            "get_appearance_stream",
            [](QPDFAnnotationObjectHelper &anno,
                QPDFObjectHandle &which, // LCOV_EXCL_LINE
                QPDFObjectHandle &state) {
                return anno.getAppearanceStream(which.getName(), state.getName());
            },
            py::arg("which"), // LCOV_EXCL_LINE
            py::arg("state"))
        .def(
            "get_page_content_for_appearance",
            [](QPDFAnnotationObjectHelper &anno,
                QPDFObjectHandle &name,
                int rotate,
                int required_flags,
                int forbidden_flags) {
                auto content = anno.getPageContentForAppearance(
                    name.getName(), rotate, required_flags, forbidden_flags);
                return py::bytes(content.data(), content.size());
            },
            py::arg("name"),
            py::arg("rotate"),
            py::arg("required_flags") = 0,
            py::arg("forbidden_flags") = an_invisible | an_hidden);
}
