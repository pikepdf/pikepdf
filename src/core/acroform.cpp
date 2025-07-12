// SPDX-FileCopyrightText: 2022 James R. Barlow
// SPDX-License-Identifier: MPL-2.0

#include <qpdf/Constants.h>
#include <qpdf/Types.h>
#include <qpdf/DLL.h>
#include <qpdf/QPDFExc.hh>
#include <qpdf/QPDFFormFieldObjectHelper.hh>
#include <qpdf/QPDFAcroFormDocumentHelper.hh>

#include <pybind11/pybind11.h>
#include <pybind11/stl.h>

#include "pikepdf.h"

void init_acroform(py::module_ &m)
{
    py::enum_<pdf_form_field_flag_e>(m, "FormFieldFlag", py::arithmetic())
        .value("read_only", pdf_form_field_flag_e::ff_all_read_only)
        .value("required", pdf_form_field_flag_e::ff_all_required)
        .value("no_export", pdf_form_field_flag_e::ff_all_no_export)
        .value("btn_no_toggle_off", pdf_form_field_flag_e::ff_btn_no_toggle_off)
        .value("btn_radio", pdf_form_field_flag_e::ff_btn_radio)
        .value("btn_pushbutton", pdf_form_field_flag_e::ff_btn_pushbutton)
        .value("btn_radios_in_unison", pdf_form_field_flag_e::ff_btn_radios_in_unison)
        .value("tx_multiline", pdf_form_field_flag_e::ff_tx_multiline)
        .value("tx_password", pdf_form_field_flag_e::ff_tx_password)
        .value("tx_file_select", pdf_form_field_flag_e::ff_tx_file_select)
        .value("tx_do_not_spell_check", pdf_form_field_flag_e::ff_tx_do_not_spell_check)
        .value("tx_do_not_scroll", pdf_form_field_flag_e::ff_tx_do_not_scroll)
        .value("tx_comb", pdf_form_field_flag_e::ff_tx_comb)
        .value("tx_rich_text", pdf_form_field_flag_e::ff_tx_rich_text)
        .value("ch_combo", pdf_form_field_flag_e::ff_ch_combo)
        .value("ch_edit", pdf_form_field_flag_e::ff_ch_edit)
        .value("ch_sort", pdf_form_field_flag_e::ff_ch_sort)
        .value("ch_multi_select", pdf_form_field_flag_e::ff_ch_multi_select)
        .value("ch_do_not_spell_check", pdf_form_field_flag_e::ff_ch_do_not_spell_check)
        .value("ch_commit_on_sel_change",
            pdf_form_field_flag_e::ff_ch_commit_on_sel_change);

    py::class_<QPDFFormFieldObjectHelper, py::smart_holder, QPDFObjectHelper>(
        m, "AcroFormField")
        .def(py::init<QPDFObjectHandle &>(), py::keep_alive<0, 1>())
        .def_property_readonly("is_null", &QPDFFormFieldObjectHelper::isNull)
        .def_property_readonly("parent", &QPDFFormFieldObjectHelper::getParent)
        .def_property_readonly("top_level_field",
            [](QPDFFormFieldObjectHelper &field) { return field.getTopLevelField(); })
        .def("get_inheritable_field_value",
            &QPDFFormFieldObjectHelper::getInheritableFieldValue,
            py::arg("name"))
        .def("get_inheritable_field_value_as_string",
            &QPDFFormFieldObjectHelper::getInheritableFieldValueAsString,
            py::arg("name"))
        .def("get_inheritable_field_value_as_name",
            &QPDFFormFieldObjectHelper::getInheritableFieldValueAsName,
            py::arg("name"))
        .def_property_readonly("field_type", &QPDFFormFieldObjectHelper::getFieldType)
        .def_property_readonly(
            "fully_qualified_name", &QPDFFormFieldObjectHelper::getFullyQualifiedName)
        .def_property_readonly(
            "partial_name", &QPDFFormFieldObjectHelper::getPartialName)
        .def_property_readonly(
            "alternate_name", &QPDFFormFieldObjectHelper::getAlternativeName)
        .def_property_readonly(
            "mapping_name", &QPDFFormFieldObjectHelper::getMappingName)
        .def_property("value",
            &QPDFFormFieldObjectHelper::getValue,
            [](QPDFFormFieldObjectHelper &field, QPDFObjectHandle value) {
                field.setV(value, true);
            })
        .def_property("value_as_string",
            &QPDFFormFieldObjectHelper::getValueAsString,
            [](QPDFFormFieldObjectHelper &field, std::string value) {
                field.setV(value, true);
            })
        .def_property_readonly(
            "default_value", &QPDFFormFieldObjectHelper::getDefaultValue)
        .def_property_readonly("default_value_as_string",
            &QPDFFormFieldObjectHelper::getDefaultValueAsString)
        .def_property_readonly("default_appearance",
            [](QPDFFormFieldObjectHelper &field) {
                return py::bytes(field.getDefaultAppearance());
            })
        .def_property_readonly(
            "default_resources", &QPDFFormFieldObjectHelper::getDefaultResources)
        .def_property_readonly("quadding", &QPDFFormFieldObjectHelper::getQuadding)
        .def_property_readonly("flags", &QPDFFormFieldObjectHelper::getFlags)
        .def_property_readonly("is_text", &QPDFFormFieldObjectHelper::isText)
        .def_property_readonly("is_checkbox", &QPDFFormFieldObjectHelper::isCheckbox)
        .def_property_readonly("is_checked",
            [](QPDFFormFieldObjectHelper &field) {
                // This is the same as the QPDF implementation, but re-implemented here
                // for versions of QPDF that did not define this method.
                return field.isCheckbox() && field.getValue().isName() &&
                       (field.getValue().getName() != "/Off");
            })
        .def_property_readonly(
            "is_radio_button", &QPDFFormFieldObjectHelper::isRadioButton)
        .def_property_readonly(
            "is_pushbutton", &QPDFFormFieldObjectHelper::isPushbutton)
        .def_property_readonly("is_choice", &QPDFFormFieldObjectHelper::isChoice)
        .def_property_readonly("choices", &QPDFFormFieldObjectHelper::getChoices)
        .def(
            "set_value",
            [](QPDFFormFieldObjectHelper &field,
                QPDFObjectHandle value,
                bool need_appearances) {
                // We get an error if we try to pass setV directly, so we wrap it
                field.setV(value, need_appearances);
            },
            py::arg("value"),
            py::arg("need_appearance") = py::bool_(true))
        .def(
            "set_value",
            [](QPDFFormFieldObjectHelper &field,
                std::string value,
                bool need_appearances) {
                // We get an error if we try to pass setV directly, so we wrap it
                field.setV(value, need_appearances);
            },
            py::arg("value"),
            py::arg("need_appearance") = py::bool_(true))
        .def("generate_appearance",
            &QPDFFormFieldObjectHelper::generateAppearance,
            py::arg("annot"));

    py::class_<QPDFAcroFormDocumentHelper, py::smart_holder>(m, "AcroForm")
        .def(py::init<QPDF &>(), py::keep_alive<0, 1>())
        .def_property_readonly("exists", &QPDFAcroFormDocumentHelper::hasAcroForm)
        .def("add_field", &QPDFAcroFormDocumentHelper::addFormField, py::arg("field"))
        .def("add_and_rename_fields",
            &QPDFAcroFormDocumentHelper::addAndRenameFormFields,
            py::arg("fields"))
        .def(
            "add_and_rename_fields",
            [](QPDFAcroFormDocumentHelper &acroform,
                const std::vector<QPDFObjectHelper> &fields) {
                // convert fields to object handles
                std::set<QPDFObjGen> objects;
                for (auto &field : fields) {
                    objects.insert(field.getObjectHandle().getObjGen());
                }
                acroform.removeFormFields(objects);
            },
            py::arg("fields"))
        .def(
            "remove_fields",
            [](QPDFAcroFormDocumentHelper &acroform,
                const std::vector<QPDFObjectHelper> &fields) {
                // convert fields to obj/gen refs
                std::set<QPDFObjGen> refs;
                for (auto &field : fields) {
                    refs.insert(field.getObjectHandle().getObjGen());
                }
                acroform.removeFormFields(refs);
            },
            py::arg("fields"))
        .def(
            "remove_fields",
            [](QPDFAcroFormDocumentHelper &acroform,
                const std::vector<QPDFObjectHandle> &fields) {
                // convert fields to obj/gen refs
                std::set<QPDFObjGen> refs;
                for (auto &field : fields) {
                    refs.insert(field.getObjGen());
                }
                acroform.removeFormFields(refs);
            },
            py::arg("fields"))
        .def("set_field_name",
            &QPDFAcroFormDocumentHelper::setFormFieldName,
            py::arg("field"),
            py::arg("name"))
        .def_property_readonly("fields", &QPDFAcroFormDocumentHelper::getFormFields)
        .def(
            "get_fields_with_qualified_name",
            [](QPDFAcroFormDocumentHelper &acroform, std::string const &name) {
                auto refs = acroform.getFieldsWithQualifiedName(name);
                // Convert obj/gen refs to field object helpers
                std::vector<QPDFFormFieldObjectHelper> fields;
                QPDF &qpdf = acroform.getQPDF();
                for (auto ref : refs) {
                    auto object = qpdf.getObjectByObjGen(ref);
                    auto field  = new QPDFFormFieldObjectHelper(object);
                    fields.push_back(*field);
                }
                return fields;
            },
            py::arg("name"))
        .def("get_annotations_for_field",
            &QPDFAcroFormDocumentHelper::getAnnotationsForField,
            py::arg("field"))
        .def("get_widget_annotations_for_page",
            &QPDFAcroFormDocumentHelper::getWidgetAnnotationsForPage,
            py::arg("page"))
        .def("get_form_fields_for_page",
            &QPDFAcroFormDocumentHelper::getFormFieldsForPage,
            py::arg("page"))
        .def("get_field_for_annotation",
            &QPDFAcroFormDocumentHelper::getFieldForAnnotation,
            py::arg("annotation"))
        .def_property("needs_appearances",
            &QPDFAcroFormDocumentHelper::getNeedAppearances,
            &QPDFAcroFormDocumentHelper::setNeedAppearances)
        .def("generate_appearances_if_needed",
            &QPDFAcroFormDocumentHelper::generateAppearancesIfNeeded)
        .def("disable_digital_signatures",
            &QPDFAcroFormDocumentHelper::disableDigitalSignatures)
        .def(
            "fix_copied_annotations",
            [](QPDFAcroFormDocumentHelper &acroform,
                QPDFPageObjectHelper to_page,
                QPDFPageObjectHelper from_page,
                QPDFAcroFormDocumentHelper &from_afdh) {
                std::set<QPDFObjGen> refs;
                acroform.fixCopiedAnnotations(to_page.getObjectHandle(),
                    from_page.getObjectHandle(),
                    from_afdh,
                    &refs);
                std::vector<QPDFFormFieldObjectHelper> fields;
                QPDF &qpdf = acroform.getQPDF();
                for (auto ref : refs) {
                    auto object = qpdf.getObjectByObjGen(ref);
                    auto field  = new QPDFFormFieldObjectHelper(object);
                    fields.push_back(*field);
                }
                return fields;
            },
            py::arg("to_page"),
            py::arg("from_page"),
            py::arg("from_acroform"));
}
