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
#include <qpdf/QPDFFileSpecObjectHelper.hh>
#include <qpdf/QPDFEFStreamObjectHelper.hh>

#include <pybind11/pybind11.h>
#include <pybind11/stl.h>

#include "pikepdf.h"

void init_filespec(py::module_ &m)
{
    py::class_<QPDFFileSpecObjectHelper>(m, "FileSpec")
        .def(py::init<QPDFFileSpecObjectHelper>(), py::keep_alive<0, 1>())
        .def_property_readonly("obj",
            [](QPDFFileSpecObjectHelper &spec) { return spec.getObjectHandle(); })
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
            The main filename for this file.

            In priority order, getting this returns /UF, /F, /Unix, /DOS, /Mac if
            multiple filenames are set. Setting this will set a UTF-8 encoded
            Unicode filename.
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

            To set any of these, write directly to the underlying object using, e.g.
            ``FileSpec.obj.Mac = 'unixfilename.txt'.encode('macroman')``. The
            encoding must be appropriate to the platform if not Unicode.
            )~~~")
        .def("get_attached_file_stream",
            [](QPDFFileSpecObjectHelper &spec) {
                return QPDFEFStreamObjectHelper(spec.getEmbeddedFileStream());
            })
        .def("get_attached_file_stream",
            [](QPDFFileSpecObjectHelper &spec, std::string const &name) {
                return QPDFEFStreamObjectHelper(spec.getEmbeddedFileStream(name));
            })
        .def("get_attached_file_stream",
            [](QPDFFileSpecObjectHelper &spec, QPDFObjectHandle &name) {
                if (!name.isName())
                    throw py::type_error("Parameter must be a pikepdf.Name");
                return QPDFEFStreamObjectHelper(
                    spec.getEmbeddedFileStream(name.getName()));
            });

    py::class_<QPDFEFStreamObjectHelper>(m, "AttachedFile")
        .def(py::init<QPDFEFStreamObjectHelper>(), py::keep_alive<0, 1>())
        .def_property_readonly("size",
            &QPDFEFStreamObjectHelper::getSize,
            "Get length of the attached file in bytes according to the PDF creator.")
        .def_property("mime_type",
            &QPDFEFStreamObjectHelper::getSubtype,
            &QPDFEFStreamObjectHelper::setSubtype,
            "Get the MIME type of the attached file according to the PDF creator.")
        .def_property_readonly("md5",
            &QPDFEFStreamObjectHelper::getChecksum,
            "Get the MD5 checksum of the attached file according to the PDF creator.")
        .def_property("_creation_date",
            &QPDFEFStreamObjectHelper::getCreationDate,
            &QPDFEFStreamObjectHelper::setCreationDate)
        .def_property("_mod_date",
            &QPDFEFStreamObjectHelper::getModDate,
            &QPDFEFStreamObjectHelper::setModDate);
}