// SPDX-FileCopyrightText: 2022 James R. Barlow
// SPDX-License-Identifier: MPL-2.0

#include <qpdf/Constants.h>
#include <qpdf/DLL.h>
#include <qpdf/QPDFEFStreamObjectHelper.hh>
#include <qpdf/QPDFEmbeddedFileDocumentHelper.hh>
#include <qpdf/QPDFExc.hh>
#include <qpdf/QPDFFileSpecObjectHelper.hh>
#include <qpdf/Types.h>

#include "pikepdf.h"
#include "pipeline.h"

QPDFFileSpecObjectHelper create_filespec(QPDF &q,
    py::bytes data,
    std::string description,
    std::string filename,
    std::string mime_type,
    std::string creation_date,
    std::string mod_date,
    QPDFObjectHandle relationship)
{
    auto efstream =
        QPDFEFStreamObjectHelper::createEFStream(q, py::cast<std::string>(data));
    auto filespec = QPDFFileSpecObjectHelper::createFileSpec(q, filename, efstream);

    if (!description.empty())
        filespec.setDescription(description);
    if (!mime_type.empty())
        efstream.setSubtype(mime_type);
    if (!creation_date.empty())
        efstream.setCreationDate(creation_date);
    if (!mod_date.empty())
        efstream.setModDate(mod_date);

    if (relationship.isName()) {
        filespec.getObjectHandle().replaceKey("/AFRelationship", relationship);
    }
    return filespec;
}

void init_embeddedfiles(py::module_ &m)
{
    py::class_<QPDFFileSpecObjectHelper, QPDFObjectHelper>(
        m, "AttachedFileSpec") // /Type /Filespec
        .def(
            "__init__",
            [](QPDFFileSpecObjectHelper *self,
                QPDF &q,
                py::bytes data,
                std::string description,
                std::string filename,
                std::string mime_type,
                std::string creation_date,
                std::string mod_date,
                QPDFObjectHandle &relationship) {
                auto fs = create_filespec(q,
                    data,
                    description,
                    filename,
                    mime_type,
                    creation_date,
                    mod_date,
                    relationship);
                new (self) QPDFFileSpecObjectHelper(fs);
            },
            py::keep_alive<0, 1>(), // LCOV_EXCL_LINE
            py::arg("q"),
            py::arg("data"),
            py::kw_only(), // LCOV_EXCL_LINE
            py::arg("description") = std::string(""),
            py::arg("filename") = std::string(""),
            py::arg("mime_type") = std::string(""),
            py::arg("creation_date") = std::string(""),
            py::arg("mod_date") = std::string(""),
            py::arg("relationship") = QPDFObjectHandle::newName("/Unspecified"))
        .def_prop_rw("description",
            &QPDFFileSpecObjectHelper::getDescription,
            &QPDFFileSpecObjectHelper::setDescription // LCOV_EXCL_LINE
            )
        .def_prop_rw(
            "filename",
            [](QPDFFileSpecObjectHelper &spec) { return spec.getFilename(); },
            [](QPDFFileSpecObjectHelper &spec, std::string const &value) {
                spec.setFilename(value);
            })
        .def("get_all_filenames",
            [](QPDFFileSpecObjectHelper &spec) -> py::dict {
                auto filenames = spec.getFilenames();
                py::dict result;
                for (auto key_filename : filenames) {
                    auto key = key_filename.first;
                    auto filename = key_filename.second;
                    auto key_as_name = QPDFObjectHandle::newName(key);
                    result[py::cast(key_as_name)] =
                        py::bytes(filename.data(), filename.size());
                }
                return result;
            })
        .def(
            "get_file",
            [](QPDFFileSpecObjectHelper &spec) {
                return QPDFEFStreamObjectHelper(spec.getEmbeddedFileStream());
            },
            py::rv_policy::reference_internal)
        .def(
            "get_file",
            [](QPDFFileSpecObjectHelper &spec, QPDFObjectHandle &name) {
                if (!name.isName())
                    throw py::type_error("Argument must be a pikepdf.Name");
                return QPDFEFStreamObjectHelper(
                    spec.getEmbeddedFileStream(name.getName()));
            },
            py::rv_policy::reference_internal);

    py::class_<QPDFEFStreamObjectHelper, QPDFObjectHelper>(
        m, "AttachedFile") // /Type /EmbeddedFile
        .def_prop_ro("size",
            &QPDFEFStreamObjectHelper::getSize // LCOV_EXCL_LINE
            )
        .def_prop_rw("mime_type",
            &QPDFEFStreamObjectHelper::getSubtype,
            &QPDFEFStreamObjectHelper::setSubtype, // LCOV_EXCL_LINE
            "")
        .def_prop_ro("md5",
            [](QPDFEFStreamObjectHelper &efstream) {
                auto checksum = efstream.getChecksum();
                return py::bytes(checksum.data(), checksum.size());
            })
        .def_prop_rw("_creation_date",
            &QPDFEFStreamObjectHelper::getCreationDate,
            &QPDFEFStreamObjectHelper::setCreationDate)
        .def_prop_rw("_mod_date",
            &QPDFEFStreamObjectHelper::getModDate,
            &QPDFEFStreamObjectHelper::setModDate);

    py::class_<QPDFEmbeddedFileDocumentHelper>(m, "Attachments")
        .def_prop_ro(
            "_has_embedded_files", &QPDFEmbeddedFileDocumentHelper::hasEmbeddedFiles)
        .def("_attach_data",
            [](QPDFEmbeddedFileDocumentHelper &efdh, py::str key, py::bytes data) {
                auto ef = create_filespec(efdh.getQPDF(),
                    data,
                    std::string(""),
                    py::cast<std::string>(key),
                    std::string(""),
                    std::string(""),
                    std::string(""),
                    QPDFObjectHandle::newName("/Unspecified"));
                efdh.replaceEmbeddedFile(py::cast<std::string>(key), ef);
            })
        .def("_get_all_filespecs",
            &QPDFEmbeddedFileDocumentHelper::getEmbeddedFiles,
            py::rv_policy::reference_internal)
        .def("_get_filespec",
            &QPDFEmbeddedFileDocumentHelper::getEmbeddedFile,
            py::rv_policy::reference_internal)
        .def("_add_replace_filespec",
            &QPDFEmbeddedFileDocumentHelper::replaceEmbeddedFile,
            py::keep_alive<0, 2>())
        .def("_remove_filespec", &QPDFEmbeddedFileDocumentHelper::removeEmbeddedFile);
}
