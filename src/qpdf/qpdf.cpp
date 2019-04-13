/*
 * This Source Code Form is subject to the terms of the Mozilla Public
 * License, v. 2.0. If a copy of the MPL was not distributed with this
 * file, You can obtain one at http://mozilla.org/MPL/2.0/.
 *
 * Copyright (C) 2017, James R. Barlow (https://github.com/jbarlow83/)
 */

#include <sstream>
#include <type_traits>
#include <cerrno>
#include <cstring>

#include "pikepdf.h"

#include <qpdf/QPDFExc.hh>
#include <qpdf/QPDFSystemError.hh>
#include <qpdf/QPDFObjGen.hh>
#include <qpdf/QPDFXRefEntry.hh>
#include <qpdf/Buffer.hh>
#include <qpdf/BufferInputSource.hh>
#include <qpdf/QPDFWriter.hh>
#include <qpdf/QPDFPageDocumentHelper.hh>

#include <pybind11/stl.h>
#include <pybind11/iostream.h>
#include <pybind11/buffer_info.h>

#include "qpdf_pagelist.h"
#include "qpdf_inputsource.h"
#include "utils.h"


void check_stream_is_usable(py::object stream)
{
    auto TextIOBase = py::module::import("io").attr("TextIOBase");

    if (py::isinstance(stream, TextIOBase)) {
        throw py::type_error("stream must be binary (no transcoding) and seekable");
    }
}

std::shared_ptr<QPDF>
open_pdf(
    py::object filename_or_stream,
    std::string password,
    bool hex_password=false,
    bool ignore_xref_streams=false,
    bool suppress_warnings=true,
    bool attempt_recovery=true,
    bool inherit_page_attributes=true)
{
    auto q = std::make_shared<QPDF>();

    q->setSuppressWarnings(suppress_warnings);
    q->setPasswordIsHexKey(hex_password);
    q->setIgnoreXRefStreams(ignore_xref_streams);
    q->setAttemptRecovery(attempt_recovery);
    q->setImmediateCopyFrom(true);

    if (py::hasattr(filename_or_stream, "read") && py::hasattr(filename_or_stream, "seek")) {
        // Python code gave us an object with a stream interface
        py::object stream = filename_or_stream;

        check_stream_is_usable(stream);

        // The PythonInputSource object will be owned by q
        InputSource* input_source = new PythonInputSource(stream);
        py::gil_scoped_release release;
        q->processInputSource(input_source, password.c_str());
    } else {
        auto filename = filename_or_stream;
        std::string description = py::str(filename);
        FILE* file = portable_fopen(filename_or_stream, "rb");

        // We can release GIL because Python knows nothing about q at this
        // point; this could also take a moment for large files
        py::gil_scoped_release release;
        q->processFile(
            description.c_str(),
            file, // transferring ownership
            true, // QPDF will close the file
            password.c_str()
        );
        file = nullptr; // QPDF owns the file and will close it
    }

    if (inherit_page_attributes) {
        // This could be expensive for a large file, plausibly (not tested),
        // so release the GIL again.
        py::gil_scoped_release release;
        q->pushInheritedAttributesToPage();
    }

    return q;
}


class PikeProgressReporter : public QPDFWriter::ProgressReporter {
public:
    PikeProgressReporter(py::function callback)
    {
        this->callback = callback;
    }

    virtual ~PikeProgressReporter() = default;

    virtual void reportProgress(int percent) override
    {
        py::gil_scoped_acquire acquire;
        this->callback(percent);
    }
private:
    py::function callback;
};


void update_xmp_pdfversion(QPDF &q, std::string version)
{
    auto impl = py::module::import("pikepdf._cpphelpers").attr("update_xmp_pdfversion");
    auto pypdf = py::cast(q);
    impl(pypdf, version);
}


void save_pdf(
    QPDF& q,
    py::object filename_or_stream,
    bool static_id=false,
    bool preserve_pdfa=true,
    std::string min_version="",
    std::string force_version="",
    bool fix_metadata_version=true,
    bool compress_streams=true,
    qpdf_stream_decode_level_e stream_decode_level=qpdf_dl_generalized,
    qpdf_object_stream_e object_stream_mode=qpdf_o_preserve,
    bool normalize_content=false,
    bool linearize=false,
    bool qdf=false,
    py::object progress=py::none())
{
    QPDFWriter w(q);

    // Parameters
    if (static_id) {
        w.setStaticID(true);
    }
    w.setNewlineBeforeEndstream(preserve_pdfa);
    if (!min_version.empty()) {
        w.setMinimumPDFVersion(min_version, 0);
    }
    if (!force_version.empty()) {
        w.forcePDFVersion(force_version, 0);
    }

    w.setCompressStreams(compress_streams);
    w.setDecodeLevel(stream_decode_level);
    w.setObjectStreamMode(object_stream_mode);

    if (normalize_content && linearize) {
        throw py::value_error("cannot save with both normalize_content and linearize");
    }
    w.setContentNormalization(normalize_content);
    w.setLinearization(linearize);
    w.setQDFMode(qdf);

    if (fix_metadata_version) {
        update_xmp_pdfversion(q, w.getFinalVersion());
    }

    if (!progress.is_none()) {
        auto reporter = PointerHolder<QPDFWriter::ProgressReporter>(new PikeProgressReporter(progress));
        w.registerProgressReporter(reporter);
    }

    if (py::hasattr(filename_or_stream, "write") && py::hasattr(filename_or_stream, "seek")) {
        // Python code gave us an object with a stream interface
        py::object stream = filename_or_stream;
        check_stream_is_usable(stream);

        // TODO might be able to improve this by streaming rather than buffering
        // using subclass of Pipeline that routes calls to Python.
        w.setOutputMemory();

        // It would be kind to release the GIL here, but this is not possible if
        // another thread has an object and tries to mess with it. Correctness
        // is more important than performance.
        w.write();

        // But now that we've held the GIL forever, we can release it and take
        // it back again; at least in theory giving other threads a chance to
        // to do something.
        {
            py::gil_scoped_release release;
        }

        // getBuffer returns Buffer* and qpdf says we are responsible for
        // deleting it, so capture it in a unique_ptr
        std::unique_ptr<Buffer> output_buffer(w.getBuffer());

        // Create a memoryview of the buffer that libqpdf created
        // Awkward API alert:
        //     QPDFWriter::getBuffer -> Buffer*  (caller frees memory)
        // and  Buffer::getBuffer -> unsigned char*  (caller does not own memory)
        py::buffer_info output_buffer_info(
            output_buffer->getBuffer(),
            output_buffer->getSize());
        py::memoryview view_output_buffer(output_buffer_info);

        // Send it to the stream object (probably copying)
        stream.attr("write")(view_output_buffer);
    } else {
        py::object filename = filename_or_stream;
        std::string description = py::str(filename);
        // Delete the intended filename, in case it is the same as the input file.
        // This ensures that the input file will continue to exist in memory on Linux.
        portable_unlink(filename);
        FILE* file = portable_fopen(filename, "wb");
        w.setOutputFile(description.c_str(), file, true);
        w.write();
        file = nullptr; // QPDF will close it
    }
}


void init_qpdf(py::module &m)
{
    py::enum_<qpdf_object_stream_e>(m, "ObjectStreamMode")
        .value("disable", qpdf_object_stream_e::qpdf_o_disable)
        .value("preserve", qpdf_object_stream_e::qpdf_o_preserve)
        .value("generate", qpdf_object_stream_e::qpdf_o_generate);

    py::enum_<qpdf_stream_decode_level_e>(m, "StreamDecodeLevel")
        .value("none", qpdf_stream_decode_level_e::qpdf_dl_none)
        .value("generalized", qpdf_stream_decode_level_e::qpdf_dl_generalized)
        .value("specialized", qpdf_stream_decode_level_e::qpdf_dl_specialized)
        .value("all", qpdf_stream_decode_level_e::qpdf_dl_all);

    py::class_<QPDF, std::shared_ptr<QPDF>>(m, "Pdf", "In-memory representation of a PDF")
        .def_static("new",
            []() {
                auto q = std::make_shared<QPDF>();
                q->emptyPDF();
                q->setSuppressWarnings(true);
                return q;
            },
            "Create a new empty PDF from stratch."
        )
        .def_static("open", open_pdf,
            R"~~~(
            Open an existing file at *filename_or_stream*.

            If *filename_or_stream* is path-like, the file will be opened for reading.
            The file should not be modified by another process while it is open in
            pikepdf. The file will not be altered when opened in this way. Any changes
            to the file must be persisted by using ``.save()``.

            If *filename_or_stream* has ``.read()`` and ``.seek()`` methods, the file
            will be accessed as a readable binary stream. pikepdf will read the
            entire stream into a private buffer.

            ``.open()`` may be used in a ``with``-block, `.`close()`` will be called when
            the block exists.

            Examples:

                >>> with Pdf.open("test.pdf") as pdf:
                        ...

                >>> pdf = Pdf.open("test.pdf", password="rosebud")

            Args:
                filename_or_stream (os.PathLike): Filename of PDF to open
                password (str or bytes): User or owner password to open an
                    encrypted PDF. If a str is given it will be converted to
                    UTF-8.
                hex_password (bool): If True, interpret the password as a
                    hex-encoded version of the exact encryption key to use, without
                    performing the normal key computation. Useful in forensics.
                ignore_xref_streams (bool): If True, ignore cross-reference
                    streams. See qpdf documentation.
                suppress_warnings (bool): If True (default), warnings are not
                    printed to stderr. Use :meth:`pikepdf.Pdf.get_warnings()` to
                    retrieve warnings.
                attempt_recovery (bool): If True (default), attempt to recover
                    from PDF parsing errors.
                inherit_page_attributes (bool): If True (default), push attributes
                    set on a group of pages to individual pages

            Raises:
                pikepdf.PasswordError: If the password failed to open the
                    file.
                pikepdf.PdfError: If for other reasons we could not open
                    the file.
                TypeError: If the type of ``filename_or_stream`` is not
                    usable.
                FileNotFoundError: If the file was not found.
            )~~~",
            py::arg("filename_or_stream"),
            py::arg("password") = "",
            py::arg("hex_password") = false,
            py::arg("ignore_xref_streams") = false,
            py::arg("suppress_warnings") = true,
            py::arg("attempt_recovery") = true,
            py::arg("inherit_page_attributes") = true
        )
        .def("__repr__",
            [](QPDF& q) {
                return std::string("<pikepdf.Pdf description='") + q.getFilename() + std::string("'>");
            }
        )
        .def_property_readonly("filename", &QPDF::getFilename,
            "the source filename of an existing PDF, when available")
        .def_property_readonly("pdf_version", &QPDF::getPDFVersion,
            "the PDF standard version, such as '1.7'")
        .def_property_readonly("extension_level", &QPDF::getExtensionLevel)
        .def_property_readonly("Root", &QPDF::getRoot,
            "the /Root object of the PDF"
        )
        .def_property_readonly("root", &QPDF::getRoot,
            "alias for .Root, the /Root object of the PDF"
        )
        .def_property("docinfo",
            [](QPDF& q) {
                if (!q.getTrailer().hasKey("/Info")) {
                    auto info = q.makeIndirectObject(QPDFObjectHandle::newDictionary());
                    q.getTrailer().replaceKey("/Info", info);
                }
                return q.getTrailer().getKey("/Info");
            },
            [](QPDF& q, QPDFObjectHandle& replace) {
                if (!replace.isIndirect())
                    throw py::value_error("docinfo must be an indirect object - use Pdf.make_indirect");
                q.getTrailer().replaceKey("/Info", replace);
            },
            "access the document information dictionary"
        )
        .def_property_readonly("trailer", &QPDF::getTrailer,
            R"~~~(
            Provides access to the PDF trailer object.

            See section 7.5.5 of the PDF reference manual. Generally speaking,
            the trailer should not be modified with pikepdf, and modifying it
            may not work. Some of the values in the trailer are automatically
            changed when a file is saved.
            )~~~"
        )
        .def_property_readonly("pages",
            [](std::shared_ptr<QPDF> q) {
                return PageList(q);
            },
            py::keep_alive<0, 1>()
        )
        .def_property_readonly("_pages", &QPDF::getAllPages)
        .def_property_readonly("is_encrypted", &QPDF::isEncrypted)
        .def_property_readonly("is_linearized", &QPDF::isLinearized,
            R"~~~(
            Returns True if the PDF is linearized.

            Specifically returns True iff the file starts with a linearization
            parameter dictionary.  Does no additional validation.
            )~~~"
        )
        .def("check_linearization",
            [](QPDF& q, py::object stream) {
                py::scoped_estream_redirect redirector(
                    std::cerr,
                    stream
                );
                q.checkLinearization();
            },
            R"~~~(
            Reports information on the PDF's linearization

            Args:
                stream: A stream to write this information too; must
                    implement ``.write()`` and ``.flush()`` method. Defaults to
                    :data:`sys.stderr`.

            )~~~",
            py::arg_v("stream", py::module::import("sys").attr("stderr"), "sys.stderr")
        )
        .def("get_warnings", &QPDF::getWarnings)  // this is a def because it modifies state by clearing warnings
        .def("show_xref_table", &QPDF::showXRefTable,
            R"~~~(
            Pretty-print the Pdf's xref (cross-reference table)
            )~~~",
            py::call_guard<py::scoped_ostream_redirect>()
        )
        .def("_add_page",
            [](QPDF& q, QPDFObjectHandle& page, bool first=false) {
                q.addPage(page, first);
            },
            R"~~~(
            Attach a page to this PDF.

            The page can be either be a newly constructed PDF object or it can
            be obtained from another PDF.

            :param pikepdf.Object page: The page object to attach
            :param bool first: If True, prepend this before the first page; if False append after last page
            )~~~",
            py::arg("page"),
            py::arg("first")=false,
            py::keep_alive<1, 2>()
        )
        .def("_add_page_at", &QPDF::addPageAt, py::keep_alive<1, 2>())
        .def("_remove_page", &QPDF::removePage)
        .def("remove_unreferenced_resources",
            [](QPDF& q) {
                QPDFPageDocumentHelper helper(q);
                helper.removeUnreferencedResources();
            },
            R"~~~(
            Remove from /Resources of each page any object not referenced in page's contents

            PDF pages may share resource dictionaries with other pages. If
            pikepdf is used for page splitting, pages may reference resources
            in their /Resources dictionary that are not actually required.
            This purges all unnecessary resource entries.

            Suggested before saving.

            )~~~"
        )
        .def("save",
            save_pdf,
            R"~~~(
            Save all modifications to this :class:`pikepdf.Pdf`.

            Args:
                filename (str or stream): Where to write the output. If a file
                    exists in this location it will be overwritten.

                static_id (bool): Indicates that the ``/ID`` metadata, normally
                    calculated as a hash of certain PDF contents and metadata
                    including the current time, should instead be generated
                    deterministically. Normally for debugging.
                preserve_pdfa (bool): Ensures that the file is generated in a
                    manner compliant with PDF/A and other stricter variants.
                    This should be True, the default, in most cases.

                min_version (str): Sets the minimum version of PDF
                    specification that should be required. If left alone QPDF
                    will decide.
                force_version (str): Override the version recommend by QPDF,
                    potentially creating an invalid file that does not display
                    in old versions. See QPDF manual for details.
                fix_metadata_version (bool): If True (default) and the XMP metadata
                    contains the optional PDF version field, ensure the version in
                    metadata is correct. If the XMP metadata does not contain a PDF
                    version field, none will be added. To ensure that the field is
                    added, edit the metadata and insert a placeholder value in
                    ``pdf:PDFVersion``.

                object_stream_mode (pikepdf.ObjectStreamMode):
                    ``disable`` prevents the use of object streams.
                    ``preserve`` keeps object streams from the input file.
                    ``generate`` uses object streams wherever possible,
                    creating the smallest files but requiring PDF 1.5+.

                compress_streams (bool): Enables or disables the compression of
                    stream objects in the PDF. Metadata is never compressed.
                    By default this is set to ``True``, and should be except
                    for debugging.

                stream_decode_level (pikepdf.StreamDecodeLevel): Specifies how
                    to encode stream objects. See documentation for
                    ``StreamDecodeLevel``.

                normalize_content (bool): Enables parsing and reformatting the
                    content stream within PDFs. This may debugging PDFs easier.

                linearize (bool): Enables creating linear or "fast web view",
                    where the file's contents are organized sequentially so that
                    a viewer can begin rendering before it has the whole file.
                    As a drawback, it tends to make files larger.

                qdf (bool): Save output QDF mode.  QDF mode is a special output
                    mode in QPDF to allow editing of PDFs in a text editor. Use
                    the program ``fix-qdf`` to fix convert back to a standard
                    PDF.

                progress (callable): Specify a callback function that is called
                    as the PDF is written. The function will be called with an
                    integer between 0-100 as the sole parameter, the progress
                    percentage. This function may not access or modify the PDF
                    while it is being written, or data corruption will almost
                    certainly occur.

            You may call ``.save()`` multiple times with different parameters
            to generate different versions of a file, and you *may* continue
            to modify the file after saving it. ``.save()`` does not modify
            the ``Pdf`` object in memory, except possibly by updating the XMP
            metadata version with ``fix_metadata_version``.

            .. note::

                :meth:`pikepdf.Pdf.remove_unreferenced_resources` before saving
                may eliminate unnecessary resources from the output file, so
                calling this method before saving is recommended. This is not
                done automatically because ``.save()`` is intended to be
                idempotent.

            )~~~",
            py::arg("filename"),
            py::arg("static_id")=false,
            py::arg("preserve_pdfa")=true,
            py::arg("min_version")="",
            py::arg("force_version")="",
            py::arg("fix_metadata_version")=true,
            py::arg("compress_streams")=true,
            py::arg("stream_decode_level")=qpdf_stream_decode_level_e::qpdf_dl_generalized,
            py::arg("object_stream_mode")=qpdf_object_stream_e::qpdf_o_preserve,
            py::arg("normalize_content")=false,
            py::arg("linearize")=false,
            py::arg("qdf")=false,
            py::arg("progress")=py::none()
        )
        .def("_get_object_id", &QPDF::getObjectByID)
        .def("get_object",
            [](QPDF &q, std::pair<int, int> objgen) {
                return q.getObjectByID(objgen.first, objgen.second);
            },
            R"~~~(
            Look up an object by ID and generation number

            Returns:
                pikepdf.Object
            )~~~",
            py::return_value_policy::reference_internal
        )
        .def("get_object",
            [](QPDF &q, int objid, int gen) {
                return q.getObjectByID(objid, gen);
            },
            R"~~~(
            Look up an object by ID and generation number

            Returns:
                pikepdf.Object
            )~~~",
            py::return_value_policy::reference_internal
        )
        .def("make_indirect", &QPDF::makeIndirectObject,
            R"~~~(
            Attach an object to the Pdf as an indirect object

            Direct objects appear inline in the binary encoding of the PDF.
            Indirect objects appear inline as references (in English, "look
            up object 4 generation 0") and then read from another location in
            the file. The PDF specification requires that certain objects
            are indirect - consult the PDF specification to confirm.

            Generally a resource that is shared should be attached as an
            indirect object. :class:`pikepdf.Stream` objects are always
            indirect, and creating them will automatically attach it to the
            Pdf.

            See Also:
                :meth:`pikepdf.Object.is_indirect`

            Returns:
                pikepdf.Object
            )~~~"
        )
        .def("make_indirect",
            [](QPDF &q, py::object obj) -> QPDFObjectHandle {
                return q.makeIndirectObject(objecthandle_encode(obj));
            },
            R"~~~(
            Encode a Python object and attach to this Pdf as an indirect object

            Returns:
                pikepdf.Object
            )~~~"
        )
        .def("copy_foreign",
            [](QPDF &q, QPDFObjectHandle &h) -> QPDFObjectHandle {
                return q.copyForeignObject(h);
            },
            "Copy object from foreign PDF to this one.",
            py::return_value_policy::reference_internal,
            py::keep_alive<1, 2>()
        )
        .def("_replace_object",
            [](QPDF &q, int objid, int gen, QPDFObjectHandle &h) {
                q.replaceObject(objid, gen, h);
            }
        )
        .def("_process",
            [](QPDF &q, std::string description, py::bytes data) {
                std::string s = data;
                q.processMemoryFile(
                    description.c_str(),
                    s.data(),
                    s.size()
                );
            },
            R"~~~(
            Process a new in-memory PDF, replacing the existing PDF

            Used to implement Pdf.close().
            )~~~"
        )
        ; // class Pdf
}
