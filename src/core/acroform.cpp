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
    py::class_<QPDFFormFieldObjectHelper,
        std::shared_ptr<QPDFFormFieldObjectHelper>,
        QPDFObjectHelper>(m, "FormField")
        .def(py::init<QPDFObjectHandle &>(), py::keep_alive<0, 1>())
        .def_property_readonly("is_null", 
            &QPDFFormFieldObjectHelper::isNull)
        .def_property_readonly("parent", 
            &QPDFFormFieldObjectHelper::getParent)
        .def_property_readonly("top_level_field",
            [](QPDFFormFieldObjectHelper &field) {
                return field.getTopLevelField();
            })
        .def_property_readonly("is_top_level",
            [](QPDFFormFieldObjectHelper &field) {
                bool is_different;
                field.getTopLevelField(&is_different);
                return !is_different;
            })
        .def("get_inheritable_field_value",
            &QPDFFormFieldObjectHelper::getInheritableFieldValue,
            py::arg("name"))
        .def("get_inheritable_field_value_as_string",
            &QPDFFormFieldObjectHelper::getInheritableFieldValueAsString,
            py::arg("name"))
        .def("get_inheritable_field_value_as_name",
            &QPDFFormFieldObjectHelper::getInheritableFieldValueAsName,
            py::arg("name"))
        .def_property_readonly("field_type",
            &QPDFFormFieldObjectHelper::getFieldType)
        .def_property_readonly("fully_qualified_name",
            &QPDFFormFieldObjectHelper::getFullyQualifiedName)
        .def_property_readonly("partial_name",
            &QPDFFormFieldObjectHelper::getPartialName)
        .def_property_readonly("alternate_name",
            &QPDFFormFieldObjectHelper::getAlternativeName)
        .def_property_readonly("mapping_name",
            &QPDFFormFieldObjectHelper::getMappingName)
        .def_property_readonly("value",
            &QPDFFormFieldObjectHelper::getValue)
        .def_property_readonly("value_as_string",
            &QPDFFormFieldObjectHelper::getValueAsString)
        .def_property_readonly("default_value",
            &QPDFFormFieldObjectHelper::getDefaultValue)
        .def_property_readonly("default_value_as_string",
            &QPDFFormFieldObjectHelper::getDefaultValueAsString)
        .def_property_readonly("default_appearance",
            &QPDFFormFieldObjectHelper::getDefaultAppearance)
        .def_property_readonly("default_resources",
            &QPDFFormFieldObjectHelper::getDefaultResources)
        .def_property_readonly("quadding",
            &QPDFFormFieldObjectHelper::getQuadding)
        .def_property_readonly("flags",
            &QPDFFormFieldObjectHelper::getFlags)
        .def_property_readonly("is_text",
            &QPDFFormFieldObjectHelper::isText)
        .def_property_readonly("is_checkbox",
            &QPDFFormFieldObjectHelper::isCheckbox)
        // .def_property_readonly("is_checked",
        //     &QPDFFormFieldObjectHelper::isChecked)
        .def_property_readonly("is_radio_button",
            &QPDFFormFieldObjectHelper::isRadioButton)
        .def_property_readonly("is_pushbutton",
            &QPDFFormFieldObjectHelper::isPushbutton)
        .def_property_readonly("is_choice",
            &QPDFFormFieldObjectHelper::isChoice)
        .def_property_readonly("choices",
            &QPDFFormFieldObjectHelper::getChoices)
        ;

    py::class_<QPDFAcroFormDocumentHelper,
        std::shared_ptr<QPDFAcroFormDocumentHelper>
        >(m, "AcroForm")
        .def(py::init<QPDF &>(), py::keep_alive<0, 1>())
        .def_property_readonly("exists", 
            &QPDFAcroFormDocumentHelper::hasAcroForm)
        .def("add_field",
            &QPDFAcroFormDocumentHelper::addFormField,
            py::arg("field"))
        .def("add_and_rename_fields",
            &QPDFAcroFormDocumentHelper::addAndRenameFormFields,
            py::arg("fields"))
        .def("add_and_rename_fields",
            [](QPDFAcroFormDocumentHelper &acroform, std::vector<QPDFObjectHelper> fields) {
                // convert fields to object handles
                std::vector<QPDFObjectHandle> objects;
                for (auto & field : fields){
                    objects.push_back(field.getObjectHandle());
                }
                acroform.removeFormFields(objects);
            },
            &QPDFAcroFormDocumentHelper::addAndRenameFormFields,
            py::arg("fields"))
        .def("remove_fields",
            [](QPDFAcroFormDocumentHelper &acroform, std::vector<QPDFObjectHelper> fields) {
                // convert fields to obj/gen refs
                std::set<QPDFObjGen> refs;
                for (auto & field : fields){
                    refs.insert(field.getObjectHandle().getObjGen());
                }
                acroform.removeFormFields(refs);
            },
            py::arg("fields"))
        .def("remove_fields",
            [](QPDFAcroFormDocumentHelper &acroform, std::vector<QPDFObjectHandle> fields) {
                // convert fields to obj/gen refs
                std::set<QPDFObjGen> refs;
                for (auto & field : fields){
                    refs.insert(field.getObjGen());
                }
                acroform.removeFormFields(refs);
            },
            py::arg("fields"))
        .def("set_field_name",
            &QPDFAcroFormDocumentHelper::setFormFieldName,
            py::arg("field"), py::arg("name"))
        .def_property_readonly("fields", 
            &QPDFAcroFormDocumentHelper::getFormFields)
        .def("get_fields_with_qualified_name",
            [](QPDFAcroFormDocumentHelper &acroform, std::string const& name) {
                auto refs = acroform.getFieldsWithQualifiedName(name);
                // Convert obj/gen refs to field object helpers
                std::vector<QPDFFormFieldObjectHelper> fields;
                QPDF& qpdf = acroform.getQPDF();
                for(auto ref : refs) {
                    auto object = qpdf.getObjectByObjGen(ref);
                    auto field = new QPDFFormFieldObjectHelper(object);
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
        .def("_transform_annotations",
            &QPDFAcroFormDocumentHelper::transformAnnotations,
            py::arg("old_annots"),
            py::arg("new_annots"),
            py::arg("new_fields"),
            py::arg("old_fields"),
            py::arg("matrix"),
            py::arg("from_pdf") = py::none(),
            py::arg("from_acroform") = py::none())
        .def("_fix_copied_annotations",
            &QPDFAcroFormDocumentHelper::fixCopiedAnnotations,
            py::arg("to_page"), 
            py::arg("from_page"), 
            py::arg("from_acroform"),
            py::arg("new_fields"))
        ;
}
