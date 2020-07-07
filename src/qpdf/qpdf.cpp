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
#include <qpdf/Pl_Discard.hh>

#include <pybind11/stl.h>
#include <pybind11/iostream.h>
#include <pybind11/buffer_info.h>

#include "qpdf_pagelist.h"
#include "qpdf_inputsource.h"
#include "mmap_inputsource.h"
#include "pipeline.h"
#include "utils.h"
#include "gsl.h"


extern bool MMAP_DEFAULT;

enum access_mode_e { access_default, access_stream, access_mmap, access_mmap_only };


void check_stream_is_usable(py::object stream)
{
    auto TextIOBase = py::module::import("io").attr("TextIOBase");

    if (py::isinstance(stream, TextIOBase)) {
        throw py::type_error("stream must be binary (no transcoding) and seekable");
    }
}

void qpdf_basic_settings(QPDF& q)
{
    q.setSuppressWarnings(true);
    q.setImmediateCopyFrom(true);
}

std::shared_ptr<QPDF>
open_pdf(
    py::object filename_or_stream,
    std::string password,
    bool hex_password=false,
    bool ignore_xref_streams=false,
    bool suppress_warnings=true,
    bool attempt_recovery=true,
    bool inherit_page_attributes=true,
    access_mode_e access_mode=access_mode_e::access_default)
{
    auto q = std::make_shared<QPDF>();

    qpdf_basic_settings(*q);
    q->setSuppressWarnings(suppress_warnings);
    q->setPasswordIsHexKey(hex_password);
    q->setIgnoreXRefStreams(ignore_xref_streams);
    q->setAttemptRecovery(attempt_recovery);

    py::object stream;
    bool closing_stream;
    std::string description;

    if (py::hasattr(filename_or_stream, "read") && py::hasattr(filename_or_stream, "seek")) {
        // Python code gave us an object with a stream interface
        stream = filename_or_stream;
        check_stream_is_usable(stream);
        closing_stream = false;
        description = py::repr(stream);
    } else {
        if (py::isinstance<py::int_>(filename_or_stream))
            throw py::type_error("expected str, bytes or os.PathLike object");
        auto filename = fspath(filename_or_stream);
        auto io_open = py::module::import("io").attr("open");
        stream = io_open(filename, "rb");
        closing_stream = true;
        description = py::str(filename);
    }

    bool success = false;
    if (access_mode == access_default)
        access_mode = MMAP_DEFAULT ? access_mmap : access_stream;

    if (access_mode == access_mmap || access_mode == access_mmap_only) {
        try {
            py::gil_scoped_release release;
            auto mmap_input_source = std::make_unique<MmapInputSource>(
                stream, description, closing_stream
            );
            auto input_source = PointerHolder<InputSource>(mmap_input_source.release());
            q->processInputSource(input_source, password.c_str());
            success = true;
        } catch (const py::error_already_set &e) {
            if (access_mode == access_mmap) {
                // Prepare to fallback to stream access
                stream.attr("seek")(0);
                access_mode = access_stream;
            } else {
                throw;
            }
        }
    }

    if (!success && access_mode == access_stream) {
        py::gil_scoped_release release;
        auto stream_input_source = std::make_unique<PythonStreamInputSource>(
            stream, description, closing_stream
        );
        auto input_source = PointerHolder<InputSource>(stream_input_source.release());
        q->processInputSource(input_source, password.c_str());
        success = true;
    }

    if (!success)
        throw py::value_error("Failed to open the file");

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


void setup_encryption(
    QPDFWriter &w,
    py::object encryption,
    std::string &owner,
    std::string &user
)
{
    bool aes = true;
    bool metadata = true;
    std::map<std::string, bool> allow;
    int encryption_level = 6;

    if (encryption.contains("R")) {
        if (!py::isinstance<py::int_>(encryption["R"]))
            throw py::type_error("Encryption level 'R' must be an integer");
        encryption_level = py::int_(encryption["R"]);
    }
    if (encryption_level < 2 || encryption_level > 6)
        throw py::value_error("Invalid encryption level: must be 2, 3, 4 or 6");

    if (encryption_level == 5) {
        auto warn = py::module::import("warnings").attr("warn");
        warn("Encryption R=5 is deprecated");
    }

    if (encryption.contains("owner")) {
        if (encryption_level <= 4) {
            auto success = QUtil::utf8_to_pdf_doc(encryption["owner"].cast<std::string>(), owner);
            if (!success)
                throw py::value_error("Encryption level is R3/R4 and password is not encodable as PDFDocEncoding");
        } else {
            owner = encryption["owner"].cast<std::string>();
        }
    }
    if (encryption.contains("user")) {
        if (encryption_level <= 4) {
            auto success = QUtil::utf8_to_pdf_doc(encryption["user"].cast<std::string>(), user);
            if (!success)
                throw py::value_error("Encryption level is R3/R4 and password is not encodable as PDFDocEncoding");
        } else {
            user = encryption["user"].cast<std::string>();
        }
    }
    if (encryption.contains("allow")) {
        auto pyallow = encryption["allow"];
        allow["accessibility"] = pyallow.attr("accessibility").cast<bool>();
        allow["extract"] = pyallow.attr("extract").cast<bool>();
        allow["modify_assembly"] = pyallow.attr("modify_assembly").cast<bool>();
        allow["modify_annotation"] = pyallow.attr("modify_annotation").cast<bool>();
        allow["modify_form"] = pyallow.attr("modify_form").cast<bool>();
        allow["modify_other"] = pyallow.attr("modify_other").cast<bool>();
        allow["print_lowres"] = pyallow.attr("print_lowres").cast<bool>();
        allow["print_highres"] = pyallow.attr("print_highres").cast<bool>();
    }
    if (encryption.contains("aes")) {
        if (py::isinstance<py::bool_>(encryption["aes"]))
            aes = py::bool_(encryption["aes"]);
        else
            throw py::type_error("aes must be bool");
    } else {
        aes = (encryption_level >= 4);
    }
    if (encryption.contains("metadata")) {
        if (py::isinstance<py::bool_>(encryption["metadata"]))
            metadata = py::bool_(encryption["metadata"]);
        else
            throw py::type_error("metadata must be bool");
    } else {
        metadata = (encryption_level >= 4);
    }

    if (metadata && encryption_level < 4) {
        throw py::value_error("Cannot encrypt metadata when R < 4");
    }
    if (aes && encryption_level < 4) {
        throw py::value_error("Cannot encrypt with AES when R < 4");
    }
    if (encryption_level == 6 && !aes) {
        throw py::value_error("When R = 6, AES encryption must be enabled");
    }
    if (metadata && !aes) {
        throw py::value_error("Cannot encrypt metadata unless AES encryption is enabled");
    }

    qpdf_r3_print_e print;
    if (allow["print_highres"])
        print = qpdf_r3p_full;
    else if (allow["print_lowres"])
        print = qpdf_r3p_low;
    else
        print = qpdf_r3p_none;

    if (encryption_level == 6) {
        w.setR6EncryptionParameters(
            user.c_str(), owner.c_str(),
            allow["accessibility"],
            allow["extract"],
            allow["modify_assembly"],
            allow["modify_annotation"],
            allow["modify_form"],
            allow["modify_other"],
            print,
            metadata
        );
    } else if (encryption_level == 5) {
        // TODO WARNING
        w.setR5EncryptionParameters(
            user.c_str(), owner.c_str(),
            allow["accessibility"],
            allow["extract"],
            allow["modify_assembly"],
            allow["modify_annotation"],
            allow["modify_form"],
            allow["modify_other"],
            print,
            metadata
        );
    } else if (encryption_level == 4) {
        w.setR4EncryptionParameters(
            user.c_str(), owner.c_str(),
            allow["accessibility"],
            allow["extract"],
            allow["modify_assembly"],
            allow["modify_annotation"],
            allow["modify_form"],
            allow["modify_other"],
            print,
            metadata,
            aes
        );
    } else if (encryption_level == 3) {
        w.setR3EncryptionParameters(
            user.c_str(), owner.c_str(),
            allow["accessibility"],
            allow["extract"],
            allow["modify_assembly"],
            allow["modify_annotation"],
            allow["modify_form"],
            allow["modify_other"],
            print
        );
    } else if (encryption_level == 2) {
        w.setR2EncryptionParameters(
            user.c_str(), owner.c_str(),
            (print != qpdf_r3p_none),
            allow["modify_assembly"],
            allow["extract"],
            allow["modify_annotation"]
        );
    }
}


typedef std::pair<std::string, int> pdf_version_extension;

pdf_version_extension get_version_extension(py::object ver_ext)
{
    std::string version = "";
    int extension = 0;
    try {
        version = ver_ext.cast<std::string>();
        extension = 0;
    } catch (const py::cast_error&) {
        try {
            auto version_ext = ver_ext.cast<pdf_version_extension>();
            version = version_ext.first;
            extension = version_ext.second;
        } catch (const py::cast_error&) {
            throw py::type_error("PDF version must be a tuple: (str, int)");
        }
    }
    return pdf_version_extension(version, extension);
}

void save_pdf(
    QPDF& q,
    py::object filename_or_stream,
    bool static_id=false,
    bool preserve_pdfa=true,
    py::object min_version=py::none(),
    py::object force_version=py::none(),
    bool fix_metadata_version=true,
    bool compress_streams=true,
    py::object stream_decode_level=py::none(),
    qpdf_object_stream_e object_stream_mode=qpdf_o_preserve,
    bool normalize_content=false,
    bool linearize=false,
    bool qdf=false,
    py::object progress=py::none(),
    py::object encryption=py::none())
{
    std::string owner;
    std::string user;
    std::string description;
    QPDFWriter w(q);

    if (static_id) {
        w.setStaticID(true);
    }
    w.setNewlineBeforeEndstream(preserve_pdfa);

    if (!min_version.is_none()) {
        auto version_ext = get_version_extension(min_version);
        w.setMinimumPDFVersion(version_ext.first, version_ext.second);
    }
    w.setCompressStreams(compress_streams);
    if (!stream_decode_level.is_none()) {
        // Unconditionally calling setDecodeLevel has side effects, disabling
        // preserve encryption in particular
        w.setDecodeLevel(stream_decode_level.cast<qpdf_stream_decode_level_e>());
    }
    w.setObjectStreamMode(object_stream_mode);

    py::object stream;
    bool should_close_stream = false;
    auto close_stream = gsl::finally([&stream, &should_close_stream] {
        if (should_close_stream && !stream.is_none())
            stream.attr("close")();
    });

    if (py::hasattr(filename_or_stream, "write") && py::hasattr(filename_or_stream, "seek")) {
        // Python code gave us an object with a stream interface
        stream = filename_or_stream;
        check_stream_is_usable(stream);
        description = py::repr(stream);
    } else {
        if (py::isinstance<py::int_>(filename_or_stream))
            throw py::type_error("expected str, bytes or os.PathLike object");
        py::object filename = fspath(filename_or_stream);
        py::object ospath = py::module::import("os").attr("path");
        py::object samefile = ospath.attr("samefile");
        try {
            if (samefile(filename, q.getFilename()).cast<bool>()) {
                throw py::value_error("Cannot overwrite input file");
            }
        } catch (const py::error_already_set &e) {
            // We expect FileNotFoundError is filename refers to a file that does
            // not exist, or if q.getFilename indicates a memory file. Suppress
            // that, and rethrow all others.
            if (!e.matches(PyExc_FileNotFoundError))
                throw;
        }
        stream = py::module::import("io").attr("open")(filename, "wb");
        should_close_stream = true;
        description = py::str(filename);
    }

    // We must set up the output pipeline before we configure encryption
    Pl_PythonOutput output_pipe(description.c_str(), stream);
    w.setOutputPipeline(&output_pipe);

    if (encryption.is(py::bool_(true)) && !q.isEncrypted()) {
        throw py::value_error("can't perserve encryption parameters on a file with no encryption");
    }

    if (
        (encryption.is(py::bool_(true)) || py::isinstance<py::dict>(encryption))
            && (normalize_content || !stream_decode_level.is_none())
    ) {
        throw py::value_error("cannot save with encryption and normalize_content or stream_decode_level");
    }

    if (encryption.is(py::bool_(true))) {
        w.setPreserveEncryption(true); // Keep existing encryption
    } else if (encryption.is_none() || encryption.is(py::bool_(false))) {
        w.setPreserveEncryption(false); // Remove encryption
    } else {
        setup_encryption(w, encryption, owner, user);
    }

    if (normalize_content && linearize) {
        throw py::value_error("cannot save with both normalize_content and linearize");
    }
    w.setContentNormalization(normalize_content);
    w.setLinearization(linearize);
    w.setQDFMode(qdf);

    if (!force_version.is_none()) {
        auto version_ext = get_version_extension(force_version);
        w.forcePDFVersion(version_ext.first, version_ext.second);
    }
    if (fix_metadata_version) {
        update_xmp_pdfversion(q, w.getFinalVersion());
    }

    if (!progress.is_none()) {
        auto reporter = PointerHolder<QPDFWriter::ProgressReporter>(new PikeProgressReporter(progress));
        w.registerProgressReporter(reporter);
    }

    w.write();
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

    py::enum_<QPDF::encryption_method_e>(m, "EncryptionMethod")
        .value("none", QPDF::encryption_method_e::e_none)
        .value("unknown", QPDF::encryption_method_e::e_unknown)
        .value("rc4", QPDF::encryption_method_e::e_rc4)
        .value("aes", QPDF::encryption_method_e::e_aes)
        .value("aesv3", QPDF::encryption_method_e::e_aesv3);

    py::enum_<access_mode_e>(m, "AccessMode")
        .value("default", access_mode_e::access_default)
        .value("stream", access_mode_e::access_stream)
        .value("mmap", access_mode_e::access_mmap)
        .value("mmap_only", access_mode_e::access_mmap_only);

    py::class_<QPDF, std::shared_ptr<QPDF>>(m, "Pdf", "In-memory representation of a PDF")
        .def_static("new",
            []() {
                auto q = std::make_shared<QPDF>();
                q->emptyPDF();
                qpdf_basic_settings(*q);
                return q;
            },
            "Create a new empty PDF from stratch."
        )
        .def_static("open", open_pdf,
            R"~~~(
            Open an existing file at *filename_or_stream*.

            If *filename_or_stream* is path-like, the file will be opened for reading.
            The file should not be modified by another process while it is open in
            pikepdf, or undefined behavior may occur. This is because the file may be
            lazily loaded. Despite this restriction, pikepdf does not try to use any OS
            services to obtain an exclusive lock on the file. Some applications may
            want to attempt this or copy the file to a temporary location before
            editing.

            When this is function is called with a stream-like object, you must ensure
            that the data it returns cannot be modified, or undefined behavior will
            occur.

            Any changes to the file must be persisted by using ``.save()``.

            If *filename_or_stream* has ``.read()`` and ``.seek()`` methods, the file
            will be accessed as a readable binary stream. pikepdf will read the
            entire stream into a private buffer.

            ``.open()`` may be used in a ``with``-block; ``.close()`` will be called when
            the block exits, if applicable.

            Whenever pikepdf opens a file, it will close it. If you open the file
            for pikepdf or give it a stream-like object to read from, you must
            release that object when appropriate.

            Examples:

                >>> with Pdf.open("test.pdf") as pdf:
                        ...

                >>> pdf = Pdf.open("test.pdf", password="rosebud")

            Args:
                filename_or_stream (os.PathLike): Filename of PDF to open
                password (str or bytes): User or owner password to open an
                    encrypted PDF. If the type of this parameter is ``str``
                    it will be encoded as UTF-8. If the type is ``bytes`` it will
                    be saved verbatim. Passwords are always padded or
                    truncated to 32 bytes internally. Use ASCII passwords for
                    maximum compatibility.
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
                access_mode (pikepdf.AccessMode): If ``.default``, pikepdf will
                    decide how to access the file. Currently, it will always
                    selected stream access. To attempt memory mapping and fallback
                    to stream if memory mapping failed, use ``.mmap``.  Use
                    ``.mmap_only`` to require memory mapping or fail
                    (this is expected to only be useful for testing). Applications
                    should be prepared to handle the SIGBUS signal on POSIX in
                    the event that the file is successfully mapped but later goes
                    away.
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
            py::arg("inherit_page_attributes") = true,
            py::arg("access_mode") = access_mode_e::access_default
        )
        .def("__repr__",
            [](QPDF& q) {
                return std::string("<pikepdf.Pdf description='") + q.getFilename() + std::string("'>");
            }
        )
        .def_property_readonly("filename", &QPDF::getFilename,
            "The source filename of an existing PDF, when available.")
        .def_property_readonly("pdf_version", &QPDF::getPDFVersion,
            "The version of the PDF specification used for this file, such as '1.7'.")
        .def_property_readonly("extension_level", &QPDF::getExtensionLevel)
        .def_property_readonly("Root", &QPDF::getRoot,
            "The /Root object of the PDF."
        )
        .def_property_readonly("root", &QPDF::getRoot,
            "Alias for .Root, the /Root object of the PDF."
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
            R"~~~(
            Access the (deprecated) document information dictionary.

            The document information dictionary is a brief metadata record
            that can store some information about the origin of a PDF. It is
            deprecated and removed in the PDF 2.0 specification. Use the
            ``.open_metadata()`` API instead, which will edit the modern (and
            unfortunately, more complicated) XMP metadata object and synchronize
            changes to the document information dictionary.

            This property simplifies access to the actual document information
            dictionary and ensures that it is created correctly if it needs
            to be created. A new dictionary will be created if this property
            is accessed and dictionary does not exist. To delete the dictionary
            use ``del pdf.trailer.Info``.
            )~~~"
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
            R"~~~(
            Returns the list of pages.

            Return type:
                pikepdf._qpdf.PageList
            )~~~",
            py::return_value_policy::reference_internal
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
        .def("get_warnings", // this is a def because it modifies state by clearing warnings
            [](QPDF& q) {
                py::list warnings;
                for (auto w: q.getWarnings()) {
                    warnings.append(w.what());
                }
                return warnings;
            }
        )
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

            Args:
                page (pikepdf.Object): The page object to attach
                first (bool): If True, prepend this before the first page; if False append after last page
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
                    exists in this location it will be overwritten. The file
                    should not be the same as the input file, because data from
                    the input file may be lazily loaded; as such overwriting
                    in place will null-out objects.

                static_id (bool): Indicates that the ``/ID`` metadata, normally
                    calculated as a hash of certain PDF contents and metadata
                    including the current time, should instead be generated
                    deterministically. Normally for debugging.
                preserve_pdfa (bool): Ensures that the file is generated in a
                    manner compliant with PDF/A and other stricter variants.
                    This should be True, the default, in most cases.

                min_version (str or tuple): Sets the minimum version of PDF
                    specification that should be required. If left alone QPDF
                    will decide. If a tuple, the second element is an integer, the
                    extension level. If the version number is not a valid format,
                    QPDF will decide what to do.
                force_version (str or tuple): Override the version recommend by QPDF,
                    potentially creating an invalid file that does not display
                    in old versions. See QPDF manual for details. If a tuple, the
                    second element is an integer, the extension level.
                fix_metadata_version (bool): If ``True`` (default) and the XMP metadata
                    contains the optional PDF version field, ensure the version in
                    metadata is correct. If the XMP metadata does not contain a PDF
                    version field, none will be added. To ensure that the field is
                    added, edit the metadata and insert a placeholder value in
                    ``pdf:PDFVersion``. If XMP metadata does not exist, it will
                    not be created regardless of the value of this argument.

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

                encryption (pikepdf.models.Encryption or bool): If ``False``
                    or omitted, existing encryption will be removed. If ``True``
                    encryption settings are copied from the originating PDF.
                    Alternately, an ``Encryption`` object may be provided that
                    sets the parameters for new encryption.

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

            .. note::

                pikepdf can read PDFs will incremental updates, but always
                any coalesces incremental updates into a single non-incremental
                PDF file when saving.
            )~~~",
            py::arg("filename"),
            py::arg("static_id")=false,
            py::arg("preserve_pdfa")=true,
            py::arg("min_version")="",
            py::arg("force_version")="",
            py::arg("fix_metadata_version")=true,
            py::arg("compress_streams")=true,
            py::arg("stream_decode_level")=py::none(),
            py::arg("object_stream_mode")=qpdf_object_stream_e::qpdf_o_preserve,
            py::arg("normalize_content")=false,
            py::arg("linearize")=false,
            py::arg("qdf")=false,
            py::arg("progress")=py::none(),
            py::arg("encryption")=py::none()
        )
        .def("_get_object_id", &QPDF::getObjectByID)
        .def("get_object",
            [](QPDF &q, std::pair<int, int> objgen) {
                return q.getObjectByID(objgen.first, objgen.second);
            },
            R"~~~(
            Look up an object by ID and generation number

            Return type:
                pikepdf.Object
            )~~~",
            py::return_value_policy::reference_internal,
            py::arg("objgen")
        )
        .def("get_object",
            [](QPDF &q, int objid, int gen) {
                return q.getObjectByID(objid, gen);
            },
            R"~~~(
            Look up an object by ID and generation number

            Return type:
                pikepdf.Object
            )~~~",
            py::return_value_policy::reference_internal,
            py::arg("objid"),
            py::arg("gen")
        )
        .def_property_readonly("objects",
            [](QPDF &q) {
                return q.getAllObjects();
            },
            R"~~~(
            Return an iterable list of all objects in the PDF.

            After deleting content from a PDF such as pages, objects related
            to that page, such as images on the page, may still be present.

            Retun type:
                pikepdf._ObjectList
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

            Return type:
                pikepdf.Object
            )~~~",
            py::arg("h")
        )
        .def("make_indirect",
            [](QPDF &q, py::object obj) -> QPDFObjectHandle {
                return q.makeIndirectObject(objecthandle_encode(obj));
            },
            R"~~~(
            Encode a Python object and attach to this Pdf as an indirect object

            Return type:
                pikepdf.Object
            )~~~",
            py::arg("obj")
        )
        .def("copy_foreign",
            [](QPDF &q, QPDFObjectHandle &h) -> QPDFObjectHandle {
                return q.copyForeignObject(h);
            },
            "Copy object from foreign PDF to this one.",
            py::return_value_policy::reference_internal,
            py::keep_alive<1, 2>(),
            py::arg("h")
        )
        .def("_replace_object",
            [](QPDF &q, int objid, int gen, QPDFObjectHandle &h) {
                q.replaceObject(objid, gen, h);
            }
        )
        .def("_swap_objects",
            [](QPDF &q, std::pair<int, int> objgen1, std::pair<int, int> objgen2) {
                QPDFObjGen o1(objgen1.first, objgen1.second);
                QPDFObjGen o2(objgen2.first, objgen2.second);
                q.swapObjects(o1, o2);
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
        .def("_decode_all_streams_and_discard",
            [](QPDF &q) {
                QPDFWriter w(q);
                Pl_Discard discard;
                w.setOutputPipeline(&discard);
                w.setDecodeLevel(qpdf_dl_all);
                w.write();
            }
        )
        .def_property_readonly("_allow_accessibility",
            [](QPDF &q) {
                return q.allowAccessibility();
            }
        )
        .def_property_readonly("_allow_extract",
            [](QPDF &q) {
                return q.allowExtractAll();
            }
        )
        .def_property_readonly("_allow_print_lowres",
            [](QPDF &q) {
                return q.allowPrintLowRes();
            }
        )
        .def_property_readonly("_allow_print_highres",
            [](QPDF &q) {
                return q.allowPrintHighRes();
            }
        )
        .def_property_readonly("_allow_modify_assembly",
            [](QPDF &q) {
                return q.allowModifyAssembly();
            }
        )
        .def_property_readonly("_allow_modify_form",
            [](QPDF &q) {
                return q.allowModifyForm();
            }
        )
        .def_property_readonly("_allow_modify_annotation",
            [](QPDF &q) {
                return q.allowModifyAnnotation();
            }
        )
        .def_property_readonly("_allow_modify_other",
            [](QPDF &q) {
                return q.allowModifyOther();
            }
        )
        .def_property_readonly("_allow_modify_all",
            [](QPDF &q) {
                return q.allowModifyAll();
            }
        )
        .def_property_readonly("_encryption_data",
            [](QPDF &q) {
                int R = 0;
                int P = 0;
                int V = 0;
                QPDF::encryption_method_e stream_method = QPDF::e_unknown;
                QPDF::encryption_method_e string_method = QPDF::e_unknown;
                QPDF::encryption_method_e file_method = QPDF::e_unknown;
                if (!q.isEncrypted(R, P, V, stream_method, string_method, file_method))
                    return py::dict();

                auto user_passwd = q.getTrimmedUserPassword();
                auto encryption_key = q.getEncryptionKey();

                return py::dict(
                    py::arg("R") = R,
                    py::arg("P") = P,
                    py::arg("V") = V,
                    py::arg("stream") = stream_method,
                    py::arg("string") = string_method,
                    py::arg("file") = file_method,
                    py::arg("user_passwd") = py::bytes(user_passwd),
                    py::arg("encryption_key") = py::bytes(encryption_key)
                );
            }
        )
        ; // class Pdf
}
