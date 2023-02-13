// SPDX-FileCopyrightText: 2022 James R. Barlow
// SPDX-License-Identifier: MPL-2.0

#include <qpdf/Constants.h>
#include <qpdf/Types.h>
#include <qpdf/DLL.h>
#include <qpdf/QPDFExc.hh>
#include <qpdf/QPDFFileSpecObjectHelper.hh>
#include <qpdf/QPDFEFStreamObjectHelper.hh>
#include <qpdf/QPDFEmbeddedFileDocumentHelper.hh>

#include <pybind11/pybind11.h>
#include <pybind11/stl.h>

#include "pikepdf.h"
#include "pipeline.h"

void init_embeddedfiles(py::module_ &m)
{
    py::class_<QPDFFileSpecObjectHelper,
        std::shared_ptr<QPDFFileSpecObjectHelper>,
        QPDFObjectHelper>(m, "AttachedFileSpec")
        .def(py::init([](QPDF &q,
                          py::bytes data,
                          std::string description,
                          std::string filename,
                          std::string mime_type,
                          std::string creation_date,
                          std::string mod_date) {
            auto efstream =
                QPDFEFStreamObjectHelper::createEFStream(q, std::string(data));
            auto filespec =
                QPDFFileSpecObjectHelper::createFileSpec(q, filename, efstream);

            if (!description.empty())
                filespec.setDescription(description);
            if (!mime_type.empty())
                efstream.setSubtype(mime_type);
            if (!creation_date.empty())
                efstream.setCreationDate(creation_date);
            if (!mod_date.empty())
                efstream.setModDate(mod_date);

            return filespec;
        }),
            py::keep_alive<0, 1>(),
            py::arg("q"),
            py::arg("data"),
            py::kw_only(),
            py::arg("description")   = std::string(""),
            py::arg("filename")      = std::string(""),
            py::arg("mime_type")     = std::string(""),
            py::arg("creation_date") = std::string(""),
            py::arg("mod_date")      = std::string(""),
            R"~~~(
            Construct a attached file spec from data in memory.

            To construct a file spec from a file on the computer's file system,
            use :meth:`from_filepath`.

            Args:
                data: Resource to load.
                description: Any description text for the attachment. May be
                    shown in PDF viewers.
                filename: Filename to display in PDF viewers.
                mime_type: Helps PDF viewers decide how to display the information.
                creation_date: PDF date string for when this file was created.
                mod_date: PDF date string for when this file was last modified.
            )~~~")
        .def_property("description",
            &QPDFFileSpecObjectHelper::getDescription,
            &QPDFFileSpecObjectHelper::setDescription,
            "Description text associated with the embedded file.")
        .def_property(
            "filename",
            [](QPDFFileSpecObjectHelper &spec) { return spec.getFilename(); },
            [](QPDFFileSpecObjectHelper &spec, std::string const &value) {
                spec.setFilename(value);
            },
            R"~~~(
            The main filename for this file spec.

            In priority order, getting this returns the first of /UF, /F, /Unix,
            /DOS, /Mac if multiple filenames are set. Setting this will set a UTF-8
            encoded Unicode filename and write it to /UF.
            )~~~")
        .def(
            "get_all_filenames",
            [](QPDFFileSpecObjectHelper &spec) -> py::dict {
                auto filenames = spec.getFilenames();
                py::dict result;
                for (auto key_filename : filenames) {
                    auto key                      = key_filename.first;
                    auto filename                 = key_filename.second;
                    auto key_as_name              = QPDFObjectHandle::newName(key);
                    result[py::cast(key_as_name)] = py::bytes(filename);
                }
                return result;
            },
            R"~~~(
            Return a Python dictionary that describes all filenames.

            The returned dictionary is not a pikepdf Object.

            Multiple filenames are generally a holdover from the pre-Unicode era.
            Modern PDFs can generally set UTF-8 filenames and avoid using
            punctuation or other marks that are forbidden in filenames.
            )~~~")
        .def(
            "get_file",
            [](QPDFFileSpecObjectHelper &spec) {
                return QPDFEFStreamObjectHelper(spec.getEmbeddedFileStream());
            },
            py::return_value_policy::reference_internal,
            R"~~~(
            Return the primary (usually only) attached file.
            )~~~")
        .def(
            "get_file",
            [](QPDFFileSpecObjectHelper &spec, QPDFObjectHandle &name) {
                if (!name.isName())
                    throw py::type_error("Argument must be a pikepdf.Name");
                return QPDFEFStreamObjectHelper(
                    spec.getEmbeddedFileStream(name.getName()));
            },
            py::return_value_policy::reference_internal,
            R"~~~(
            Return an attached file selected by :class:`pikepdf.Name`.

            Typical names would be ``/UF`` and ``/F``. See |pdfrm| for other obsolete
            names.
            )~~~");

    py::class_<QPDFEFStreamObjectHelper,
        std::shared_ptr<QPDFEFStreamObjectHelper>,
        QPDFObjectHelper>(m, "AttachedFile")
        .def_property_readonly("size",
            &QPDFEFStreamObjectHelper::getSize,
            "Get length of the attached file in bytes according to the PDF creator.")
        .def_property("mime_type",
            &QPDFEFStreamObjectHelper::getSubtype,
            &QPDFEFStreamObjectHelper::setSubtype,
            "Get the MIME type of the attached file according to the PDF creator.")
        .def_property_readonly(
            "md5",
            [](QPDFEFStreamObjectHelper &efstream) {
                return py::bytes(efstream.getChecksum());
            },
            "Get the MD5 checksum of the attached file according to the PDF creator.")
        .def_property("_creation_date",
            &QPDFEFStreamObjectHelper::getCreationDate,
            &QPDFEFStreamObjectHelper::setCreationDate)
        .def_property("_mod_date",
            &QPDFEFStreamObjectHelper::getModDate,
            &QPDFEFStreamObjectHelper::setModDate);

    py::class_<QPDFEmbeddedFileDocumentHelper>(m, "Attachments")
        .def_property_readonly(
            "_has_embedded_files", &QPDFEmbeddedFileDocumentHelper::hasEmbeddedFiles)
        .def("_get_all_filespecs",
            &QPDFEmbeddedFileDocumentHelper::getEmbeddedFiles,
            py::return_value_policy::reference_internal)
        .def("_get_filespec",
            &QPDFEmbeddedFileDocumentHelper::getEmbeddedFile,
            py::return_value_policy::reference_internal)
        .def("_add_replace_filespec",
            &QPDFEmbeddedFileDocumentHelper::replaceEmbeddedFile,
            py::keep_alive<0, 2>())
        .def("_remove_filespec", &QPDFEmbeddedFileDocumentHelper::removeEmbeddedFile);
}