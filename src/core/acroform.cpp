// SPDX-FileCopyrightText: 2022 James R. Barlow
// SPDX-License-Identifier: MPL-2.0

#include <qpdf/QPDF.hh>
#include <qpdf/Constants.h>
#include <qpdf/Types.h>
#include <qpdf/DLL.h>
#include <qpdf/QPDFExc.hh>

#include <qpdf/QPDFObjectHandle.hh>
#include <qpdf/QPDFAcroFormDocumentHelper.hh>

#include <pybind11/pybind11.h>
#include <pybind11/stl.h>

#include "pikepdf.h"

void init_acroform(py::module_ &m)
{
    py::class_<QPDFAcroFormDocumentHelper,
        std::shared_ptr<QPDFAcroFormDocumentHelper>,
        QPDFObjectHelper>(m, "AcroFormDocument")
        .def(
            py::init([](QPDF &q) {
                QPDFAcroFormDocumentHelper afdh(q);

                return afdh;
            }),
            py::keep_alive<0, 1>(), // LCOV_EXCL_LINE
            py::arg("q")
        )
        .def(
            "set_form_field_name",
            [](QPDFAcroFormDocumentHelper &afdh, QPDFObjectHandle annot, std::string const& name) {
                QPDFFormFieldObjectHelper ffh = afdh.getFieldForAnnotation(annot);
                auto ffh_oh = ffh.getObjectHandle();
                if (ffh_oh.hasKey("/Parent")) {
                    QPDFObjectHandle parent = ffh_oh.getKey("/Parent");
                    QPDFFormFieldObjectHelper ph(parent);
                    afdh.setFormFieldName(ph, name);
                } else {
                    afdh.setFormFieldName(ffh, name);
                }
            }
        );
}