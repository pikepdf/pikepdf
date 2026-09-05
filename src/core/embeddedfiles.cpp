// SPDX-FileCopyrightText: 2022 James R. Barlow
// SPDX-License-Identifier: MPL-2.0

#include "object.h"
#include "pikepdf.h"
#include "pipeline.h"
#include "qpdf_lock.h"

#include <qpdf/Constants.h>
#include <qpdf/DLL.h>
#include <qpdf/QPDFEFStreamObjectHelper.hh>
#include <qpdf/QPDFEmbeddedFileDocumentHelper.hh>
#include <qpdf/QPDFExc.hh>
#include <qpdf/QPDFFileSpecObjectHelper.hh>
#include <qpdf/Types.h>

QPDFFileSpecObjectHelper create_filespec(QPDF &q,
    py::bytes data,
    std::string description,
    std::string filename,
    std::string mime_type,
    std::string creation_date,
    std::string mod_date,
    QPDFObjectHandle relationship)
{
    QpdfLockGuard lock(&q);
    auto efstream = QPDFEFStreamObjectHelper::createEFStream(q, to_string(data));
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

// The names under which files are embedded, in the map's sorted order.
static py::list attachment_keys(QPDFEmbeddedFileDocumentHelper &efdh)
{
    py::list keys;
    for (auto const &item : efdh.getEmbeddedFiles())
        keys.append(py::str(item.first.c_str()));
    return keys;
}

void init_embeddedfiles(py::module_ &m)
{
    py::class_<QPDFFileSpecObjectHelper, QPDFObjectHelper>(
        m, "AttachedFileSpec", py::type_slots(pikepdf_gc_slots)) // /Type /Filespec
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
                py::object relationship) {
                // Resolve the default lazily: None -> /Unspecified. Keeping the
                // default out of py::arg() prevents nanobind from materializing
                // a persistent pikepdf.Object instance at module-init time
                // (which would appear in the shutdown leak report).
                QPDFObjectHandle rel = relationship.is_none()
                                           ? QPDFObjectHandle::newName("/Unspecified")
                                           : py::cast<QPDFObjectHandle>(relationship);
                auto fs = create_filespec(q,
                    data,
                    description,
                    filename,
                    mime_type,
                    creation_date,
                    mod_date,
                    rel);
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
            py::arg("relationship") = py::none())
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
            py::rv_policy::reference_internal)
        .def_prop_rw(
            "relationship",
            [](QPDFFileSpecObjectHelper &spec) -> py::object {
                try {
                    return py::cast(
                        object_get_key(spec.getObjectHandle(), "/AFRelationship"));
                } catch (const py::builtin_exception &) {
                    return py::none();
                }
            },
            [](QPDFFileSpecObjectHelper &spec, py::handle value) {
                auto oh = spec.getObjectHandle();
                if (value.is_none()) {
                    object_del_key(oh, "/AFRelationship");
                } else {
                    auto rel = objecthandle_encode(value);
                    object_set_key(oh, "/AFRelationship", rel);
                }
            },
            py::arg("value").none(),
            R"(The file's relationship to the document, as a :class:`pikepdf.Name`.

Returns ``None`` if the file specification has no ``/AFRelationship``.
Assigning ``None`` removes it.
)")
        .def("__repr__", [](QPDFFileSpecObjectHelper &spec) {
            auto filename = spec.getFilename();
            if (!filename.empty()) {
                return py::str("<pikepdf._core.AttachedFileSpec for {!r}, "
                               "description {!r}>")
                    .format(filename, spec.getDescription());
            }
            return py::str("<pikepdf._core.AttachedFileSpec description {!r}>")
                .format(spec.getDescription());
        });

    py::class_<QPDFEFStreamObjectHelper, QPDFObjectHelper>(
        m, "AttachedFile", py::type_slots(pikepdf_gc_slots)) // /Type /EmbeddedFile
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
            &QPDFEFStreamObjectHelper::setModDate)
        .def(
            "read_bytes",
            [](QPDFEFStreamObjectHelper &efstream) {
                auto oh = efstream.getObjectHandle();
                auto buf = get_stream_data(oh, qpdf_dl_generalized);
                return py::bytes((const char *)buf->getBuffer(), buf->getSize());
            },
            "Read the attached file's decoded contents.");

    py::class_<QPDFEmbeddedFileDocumentHelper>(
        m, "Attachments", py::type_slots(pikepdf_gc_slots))
        .def_prop_ro(
            "_has_embedded_files", &QPDFEmbeddedFileDocumentHelper::hasEmbeddedFiles)
        .def(
            "__getitem__",
            [](QPDFEmbeddedFileDocumentHelper &efdh, std::string const &key) {
                auto filespec = efdh.getEmbeddedFile(key);
                if (!filespec)
                    throw py::key_error(key.c_str());
                return filespec;
            },
            py::rv_policy::reference_internal)
        .def("__setitem__",
            [](QPDFEmbeddedFileDocumentHelper &efdh,
                std::string const &key,
                py::bytes data) {
                efdh.replaceEmbeddedFile(key,
                    create_filespec(efdh.getQPDF(),
                        data,
                        std::string(""),
                        key,
                        std::string(""),
                        std::string(""),
                        std::string(""),
                        QPDFObjectHandle::newName("/Unspecified")));
            })
        .def("__setitem__",
            [](QPDFEmbeddedFileDocumentHelper &efdh,
                std::string const &key,
                QPDFFileSpecObjectHelper &filespec) {
                // A file specification attached under a name it does not carry
                // itself would have no filename to report, so adopt the key.
                if (filespec.getFilename().empty())
                    filespec.setFilename(key);
                efdh.replaceEmbeddedFile(key, filespec);
            })
        .def("__delitem__",
            [](QPDFEmbeddedFileDocumentHelper &efdh, std::string const &key) {
                efdh.removeEmbeddedFile(key);
            })
        .def("__len__",
            [](QPDFEmbeddedFileDocumentHelper &efdh) {
                return efdh.getEmbeddedFiles().size();
            })
        .def("__iter__",
            [](QPDFEmbeddedFileDocumentHelper &efdh) {
                // getEmbeddedFiles() returns the map by value, so an iterator
                // into it would dangle; collect the keys instead. This also
                // avoids building a pikepdf.AttachedFileSpec for every entry
                // just to iterate the names.
                return py::iter(attachment_keys(efdh));
            })
        .def("__repr__", [](QPDFEmbeddedFileDocumentHelper &efdh) {
            return py::str("<pikepdf._core.Attachments: {}>")
                .format(attachment_keys(efdh));
        });
}
