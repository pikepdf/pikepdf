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
    py::object encryption
)
{
    std::string owner;
    std::string user;

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
    py::object encryption=py::none(),
    bool samefile_check=true)
{
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
        if (should_close_stream && !stream.is_none() && py::hasattr(stream, "close"))
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
        py::object output_filename = fspath(filename_or_stream);
        if (samefile_check) {
            auto input_filename = q.getFilename();

            py::object ospath = py::module::import("os").attr("path");
            py::object samefile = ospath.attr("samefile");
            try {
                if (samefile(output_filename, input_filename).cast<bool>()) {
                    throw py::value_error(
                        "Cannot overwrite input file. Open the file with "
                        "pikepdf.open(..., allow_overwriting_input=True) to "
                        "allow overwriting the input file."
                    );
                }
            } catch (const py::error_already_set &e) {
                // We expect FileNotFoundError if filename refers to a file that does
                // not exist, or if q.getFilename indicates a memory file. Suppress
                // that, and rethrow all others.
                if (!e.matches(PyExc_FileNotFoundError))
                    throw;
            }
        }
        stream = py::module::import("io").attr("open")(output_filename, "wb");
        should_close_stream = true;
        description = py::str(output_filename);
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
        setup_encryption(w, encryption);
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

    py::class_<QPDF, std::shared_ptr<QPDF>>(m, "Pdf", "In-memory representation of a PDF", py::dynamic_attr())
        .def_static("new",
            []() {
                auto q = std::make_shared<QPDF>();
                q->emptyPDF();
                qpdf_basic_settings(*q);
                return q;
            },
            "Create a new empty PDF from stratch."
        )
        .def_static("_open", open_pdf, "",
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
        .def("_save", save_pdf, "",
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
            py::arg("encryption")=py::none(),
            py::arg("samefile_check")=true
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
