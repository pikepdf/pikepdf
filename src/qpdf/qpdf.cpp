/*
 * This Source Code Form is subject to the terms of the Mozilla Public
 * License, v. 2.0. If a copy of the MPL was not distributed with this
 * file, You can obtain one at http://mozilla.org/MPL/2.0/.
 *
 * Copyright (C) 2017, James R. Barlow (https://github.com/jbarlow83/)
 */

#include <sstream>
#include <type_traits>

#include "pikepdf.h"

#include <qpdf/QPDFExc.hh>
#include <qpdf/QPDFObjGen.hh>
#include <qpdf/QPDFXRefEntry.hh>
#include <qpdf/Buffer.hh>
#include <qpdf/QPDFWriter.hh>

#include <pybind11/stl.h>
#include <pybind11/iostream.h>
#include <pybind11/buffer_info.h>

#include "qpdf_pagelist.h"

extern "C" const char* qpdf_get_qpdf_version();

template <typename T>
void kwargs_to_method(py::kwargs kwargs, const char* key, std::shared_ptr<QPDF> &q, void (QPDF::*callback)(T))
{
    try {
        if (kwargs.contains(key)) {
            auto v = kwargs[key].cast<T>();
            ((*q).*callback)(v); // <-- Cute
        }
    } catch (py::cast_error) {
        throw py::type_error(std::string(key) + ": unsupported argument type");
    }
}

/* Convert a Python object to a filesystem encoded path
 * Use Python's os.fspath() which accepts os.PathLike (str, bytes, pathlib.Path)
 * and returns bytes encoded in the filesystem encoding.
 * Cast to a string without transcoding.
 */
std::string fsencode_filename(py::object py_filename)
{
    auto fspath = py::module::import("pikepdf._cpphelpers").attr("fspath");
    std::string filename;

    try {
        auto py_encoded_filename = fspath(py_filename);
        filename = py_encoded_filename.cast<std::string>();
    } catch (py::cast_error &e) {
        throw py::type_error("expected pathlike object");
    }

    return filename;
}

void check_stream_is_usable(py::object stream)
{
    auto TextIOBase = py::module::import("io").attr("TextIOBase");

    if (py::isinstance(stream, TextIOBase)) {
        throw py::type_error("stream must be binary (no transcoding) and seekable");
    }
}

std::shared_ptr<QPDF>
open_pdf(py::object file, py::kwargs kwargs)
{
    auto q = std::make_shared<QPDF>();

    std::string password;

    q->setSuppressWarnings(true);
    if (kwargs) {
        if (kwargs.contains("password")) {
            auto v = kwargs["password"].cast<std::string>();
            password = v;
        }
        kwargs_to_method(kwargs, "hex_password", q, &QPDF::setPasswordIsHexKey);
        kwargs_to_method(kwargs, "ignore_xref_streams", q, &QPDF::setIgnoreXRefStreams);
        kwargs_to_method(kwargs, "suppress_warnings", q, &QPDF::setSuppressWarnings);
        kwargs_to_method(kwargs, "attempt_recovery", q, &QPDF::setAttemptRecovery);
    }

    if (py::hasattr(file, "read") && py::hasattr(file, "seek")) {
        // Python code gave us an object with a stream interface
        py::object stream = file;

        check_stream_is_usable(stream);

        py::object read = stream.attr("read");
        py::bytes data = read();
        char *buffer;
        ssize_t length;

        PYBIND11_BYTES_AS_STRING_AND_SIZE(data.ptr(), &buffer, &length);

        // libqpdf will create a copy of this memory and attach it
        // to 'q'
        // This could be improved by subclassing InputSource into C++
        // and creating a version that obtains its data from its Python object,
        // but that is much more complex.
        // It is believed to be safe to release the GIL here -- we are working
        // on a read-only view of an object that only we know about.
        py::gil_scoped_release release;
        q->processMemoryFile("memory", buffer, length, password.c_str());
    } else {
        std::string filename = fsencode_filename(file);
        // We can release GIL because Python knows nothing about q at this
        // point; this could also take a moment for large files
        py::gil_scoped_release release;
        q->processFile(filename.c_str(), password.c_str());
    }

    bool push_page_attrs = true;
    if (kwargs && kwargs.contains("inherit_page_attributes")) {
        push_page_attrs = kwargs["inherit_page_attributes"].cast<bool>();
    }
    if (push_page_attrs) {
        // This could be expensive for a large file, plausibly (not tested),
        // so release the GIL again.
        py::gil_scoped_release release;
        q->pushInheritedAttributesToPage();
    }

    return q;
}


void save_pdf(
    std::shared_ptr<QPDF> q,
    py::object filename_or_stream,
    bool static_id=false,
    bool preserve_pdfa=true,
    std::string min_version="",
    std::string force_version="",
    bool compress_streams=true,
    qpdf_object_stream_e object_stream_mode=qpdf_o_preserve,
    qpdf_stream_data_e stream_data_mode=qpdf_s_preserve,
    bool normalize_content=false,
    bool linearize=false)
{
    QPDFWriter w(*q);

    // Parameters
    if (static_id) {
        w.setStaticID(true);
        w.setStreamDataMode(qpdf_s_uncompress);
    }
    w.setNewlineBeforeEndstream(preserve_pdfa);
    if (!min_version.empty()) {
        w.setMinimumPDFVersion(min_version, 0);
    }
    if (!force_version.empty()) {
        w.forcePDFVersion(force_version, 0);
    }
    w.setCompressStreams(compress_streams);
    w.setObjectStreamMode(object_stream_mode);
    w.setStreamDataMode(stream_data_mode);

    if (normalize_content && linearize) {
        throw py::value_error("cannot save with both normalize_content and linearize");
    }
    w.setContentNormalization(normalize_content);
    w.setLinearization(linearize);

    if (py::hasattr(filename_or_stream, "write") && py::hasattr(filename_or_stream, "seek")) {
        // Python code gave us an object with a stream interface
        py::object stream = filename_or_stream;
        check_stream_is_usable(stream);

        // TODO might be able to improve this by streaming rather than buffering
        // using subclass of Pipeline that routes calls to Python.
        w.setOutputMemory();

        // It would be kind to release the GIL here, but this is not possible
        // if another thread has an object and tries to mess with it.
        // Correctness is more important than performance.
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
        w.setOutputFilename(fsencode_filename(filename).c_str());
        w.write();
    }
}


PYBIND11_MODULE(_qpdf, m) {
    //py::options options;
    //options.disable_function_signatures();

    m.doc() = "pikepdf provides a Pythonic interface for QPDF";

    m.def("qpdf_version", &qpdf_get_qpdf_version, "Get libqpdf version");

    static py::exception<QPDFExc> exc_main(m, "PdfError");
    static py::exception<QPDFExc> exc_password(m, "PasswordError");
    py::register_exception_translator([](std::exception_ptr p) {
        try {
            if (p) std::rethrow_exception(p);
        } catch (const QPDFExc &e) {
            if (e.getErrorCode() == qpdf_e_password) {
                exc_password(e.what());
            } else {
                exc_main(e.what());
            }
        }
    });

    py::enum_<qpdf_object_stream_e>(m, "ObjectStreamMode")
        .value("disable", qpdf_object_stream_e::qpdf_o_disable)
        .value("preserve", qpdf_object_stream_e::qpdf_o_preserve)
        .value("generate", qpdf_object_stream_e::qpdf_o_generate);

    py::enum_<qpdf_stream_data_e>(m, "StreamDataMode")
        .value("uncompress", qpdf_stream_data_e::qpdf_s_uncompress)
        .value("preserve", qpdf_stream_data_e::qpdf_s_preserve)
        .value("compress", qpdf_stream_data_e::qpdf_s_compress);

    init_pagelist(m);

    py::class_<QPDF, std::shared_ptr<QPDF>>(m, "Pdf", "In-memory representation of a PDF")
        .def_static("new",
            []() {
                auto q = std::make_shared<QPDF>();
                q->emptyPDF();
                q->setSuppressWarnings(true);
                return q;
            },
            "create a new empty PDF from stratch"
        )
        .def_static("open", open_pdf,
            R"~~~(
            Open an existing file at `filename_or_stream` according to `options`, all
            of which are optional.

            If `filename_or_stream` is path-like, the file will be opened.

            If `filename_or_stream` has `.read()` and `.seek()` methods, the file
            will be accessed as a readable binary stream. pikepdf will read the
            entire stream into a private buffer.

            :param filename_or_stream: Filename of PDF to open
            :type filename_or_stream: os.PathLike or file stream
            :param password: User or owner password to open an encrypted PDF
            :type password: str or bytes
            :param hex_password: If True, interpret the password as a
                hex-encoded version of the exact encryption key to use, without
                performing the normal key computation. Useful in forensics.
            :param ignore_xref_streams: If True, ignore cross-reference
                streams. See qpdf documentation.
            :param suppress_warnings: If True (default), warnings are not
                printed to stderr. Use `get_warnings()` to retrieve warnings.
            :param attempt_recovery: If True (default), attempt to recover
                from PDF parsing errors.
            :param inherit_page_attributes: If True (default), push attributes
                set on a group of pages to individual pages
            :throws pikepdf.PasswordError: If the password failed to open the
                file.
            :throws pikepdf.PdfError: If for other reasons we could not open
                the file.
            :throws TypeError: If the type of `filename_or_stream` is not
                usable.
            )~~~"
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
        .def_property("metadata",
            [](QPDF& q) {
                if (!q.getTrailer().hasKey("/Info")) {
                    auto info = q.makeIndirectObject(QPDFObjectHandle::newDictionary());
                    q.getTrailer().replaceKey("/Info", info);
                }
                return q.getTrailer().getKey("/Info");
            },
            [](QPDF& q, QPDFObjectHandle& replace) {
                if (!replace.isIndirect())
                    throw py::value_error("metadata must be an indirect object - use Pdf.make_indirect");
                q.getTrailer().replaceKey("/Info", replace);
            },
            "access the document information dictionary"
        )
        .def_property_readonly("trailer", &QPDF::getTrailer,
            "the PDF trailer")
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

            :param stream: a stream to write this information too; must
                implement .write() and .flush() method. Defaults to
                ``sys.stderr``.

            )~~~",
            py::arg("stream")=py::module::import("sys").attr("stderr")
        )
        .def("get_warnings", &QPDF::getWarnings)  // this is a def because it modifies state by clearing warnings
        .def("show_xref_table", &QPDF::showXRefTable)
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
        .def("save",
            save_pdf,
            R"~~~(
            Save all modifications to this PDF

            *filename* is the filename or writable file stream to write to.

            *static_id* indicates that the ``/ID`` metadata, normally
            calculated as a hash of certain PDF contents and metadata including
            the current time, should instead be generated deterministically.
            Normally for debugging.

            *preserve_pdfa* ensures that the file is generated in a manner
            compliant with PDF/A and other PDF variants. This should be True,
            the default, in most cases.

            *min_version* sets the minimum version of PDF specification that
            should be required. If left alone QPDF will decide. *force_version*
            allows creating a lower version deliberately.

            *object_stream_mode* is drawn from this table:

            +-------------------+------------------------------------------+
            | Constant          | Description                              |
            +-------------------+------------------------------------------+
            | :const:`disable`  | prevents the use of object streams       |
            +-------------------+------------------------------------------+
            | :const:`preserve` | keeps object streams from the input file |
            +-------------------+------------------------------------------+
            | :const:`generate` | uses object streams everywhere possible  |
            +-------------------+------------------------------------------+

            ``generate`` will tend to create the smallest files, but requires
            PDF version 1.5 or higher.

            *stream_data_mode* is drawn from this table:

            +---------------------+----------------------------------------------+
            | Constant            | Description                                  |
            +---------------------+----------------------------------------------+
            | :const:`uncompress` | decompresses all data                        |
            +---------------------+----------------------------------------------+
            | :const:`preserve`   | keeps existing compressed objects compressed |
            +---------------------+----------------------------------------------+
            | :const:`compress`   | attempts to compress all objects             |
            +---------------------+----------------------------------------------+

            *normalize_content* enables parsing and reformatting the content
            stream within PDFs. This may debugging PDFs easier.

            *linearize* enables creating linear or "fast web view", where the
            file's contents are organized sequentially so that a viewer can
            begin rendering before it has the whole file. As a drawback, it
            tends to make files larger.

            You may call ``.save()`` multiple times with different parameters
            to generate different versions of a file, and you *may* continue
            to modify the file after saving it.

            )~~~",
            py::arg("filename"),
            py::arg("static_id")=false,
            py::arg("preserve_pdfa")=true,
            py::arg("min_version")="",
            py::arg("force_version")="",
            py::arg("compress_streams")=true,
            py::arg("object_stream_mode")=qpdf_o_preserve,
            py::arg("stream_data_mode")=qpdf_s_preserve,
            py::arg("normalize_content")=false,
            py::arg("linearize")=false
        )
        .def("_get_object_id", &QPDF::getObjectByID)
        .def("get_object",
            [](QPDF &q, std::pair<int, int> objgen) {
                return q.getObjectByID(objgen.first, objgen.second);
            },
            R"~~~(
            Look up an object by ID and generation number

            :returns pikepdf.Object:
            )~~~",
            py::return_value_policy::reference_internal
        )
        .def("get_object",
            [](QPDF &q, int objid, int gen) {
                return q.getObjectByID(objid, gen);
            },
            R"~~~(
            Look up an object by ID and generation number

            :returns pikepdf.Object:
            )~~~",
            py::return_value_policy::reference_internal
        )
        .def("make_indirect", &QPDF::makeIndirectObject)
        .def("make_indirect",
            [](QPDF &q, py::object obj) -> QPDFObjectHandle {
                return q.makeIndirectObject(objecthandle_encode(obj));
            }
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
        .def("_repr_mimebundle_",
            [](std::shared_ptr<QPDF> q, py::kwargs kwargs) { // For MSVC++
                auto repr_mimebundle = py::module::import("pikepdf._cpphelpers").attr("pdf_repr_mimebundle");
                return repr_mimebundle(q, **kwargs);
            }
        )
        ; // class Pdf

    init_object(m);

#ifdef VERSION_INFO
    m.attr("__version__") = VERSION_INFO;
#else
    m.attr("__version__") = "dev";
#endif
}
