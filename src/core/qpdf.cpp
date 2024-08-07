// SPDX-FileCopyrightText: 2022 James R. Barlow
// SPDX-License-Identifier: MPL-2.0

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
#include <qpdf/QPDFAcroFormDocumentHelper.hh>
#include <qpdf/QPDFEmbeddedFileDocumentHelper.hh>
#include <qpdf/QPDFLogger.hh>

#include <pybind11/stl.h>
#include <pybind11/iostream.h>
#include <pybind11/buffer_info.h>

#include "qpdf_pagelist.h"
#include "qpdf_inputsource-inl.h"
#include "mmap_inputsource-inl.h"
#include "jbig2-inl.h"
#include "pipeline.h"
#include "utils.h"

extern bool MMAP_DEFAULT;

enum access_mode_e { access_default, access_stream, access_mmap, access_mmap_only };

void qpdf_basic_settings(QPDF &q) // LCOV_EXCL_LINE
{
    q.setSuppressWarnings(true);
    q.setImmediateCopyFrom(true);
    q.setLogger(get_pikepdf_logger());
}

std::shared_ptr<QPDF> open_pdf(py::object stream,
    std::string password,
    bool hex_password            = false,
    bool ignore_xref_streams     = false,
    bool suppress_warnings       = true,
    bool attempt_recovery        = true,
    bool inherit_page_attributes = true,
    access_mode_e access_mode    = access_mode_e::access_default,
    std::string description      = "",
    bool closing_stream          = false)
{
    auto q = std::make_shared<QPDF>();

    qpdf_basic_settings(*q);
    q->setSuppressWarnings(suppress_warnings);
    q->setPasswordIsHexKey(hex_password);
    q->setIgnoreXRefStreams(ignore_xref_streams);
    q->setAttemptRecovery(attempt_recovery);

    bool success = false;
    if (access_mode == access_default)
        access_mode = MMAP_DEFAULT ? access_mmap : access_stream;

    if (access_mode == access_mmap || access_mode == access_mmap_only) {
        try {
            auto mmap_input_source =
                std::make_unique<MmapInputSource>(stream, description, closing_stream);
            auto input_source =
                std::shared_ptr<InputSource>(mmap_input_source.release());
            py::gil_scoped_release release;
            q->processInputSource(input_source, password.c_str());
            success = true;
        } catch (const py::error_already_set &) {
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
        auto stream_input_source = std::make_unique<PythonStreamInputSource>(
            stream, description, closing_stream);
        auto input_source = std::shared_ptr<InputSource>(stream_input_source.release());
        py::gil_scoped_release release;
        q->processInputSource(input_source, password.c_str());
        success = true;
    }

    if (!success) {
        // LCOV_EXCL_START
        throw std::logic_error(
            "open_pdf: should have succeeded or thrown a Python exception");
        // LCOV_EXCL_STOP
    }

    if (inherit_page_attributes) {
        // This could be expensive for a large file, plausibly (not tested),
        // so release the GIL again.
        py::gil_scoped_release release;
        q->pushInheritedAttributesToPage();
    }

    if (!password.empty() && !q->isEncrypted()) {
        python_warning(
            "A password was provided, but no password was needed to open this PDF.");
    }

    return q;
}

class PikeProgressReporter : public QPDFWriter::ProgressReporter {
public:
    PikeProgressReporter(py::function callback) { this->callback = callback; }

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
    auto impl =
        py::module_::import("pikepdf._cpphelpers").attr("update_xmp_pdfversion");
    auto pypdf = py::cast(q);
    impl(pypdf, version);
}

std::string encryption_password(
    py::dict encryption, const int encryption_level, const char *keyname)
{
    std::string result;
    if (encryption.contains(keyname)) {
        if (encryption[keyname].is_none())
            throw py::value_error(std::string("Encryption ") + keyname +
                                  " may not be None; use empty string?");
        if (encryption_level <= 4) {
            auto success =
                QUtil::utf8_to_pdf_doc(encryption[keyname].cast<std::string>(), result);
            if (!success)
                throw py::value_error("Encryption level is R3/R4 and password is not "
                                      "encodable as PDFDocEncoding");
        } else {
            result = encryption[keyname].cast<std::string>();
        }
    }
    return result;
}

void setup_encryption(QPDFWriter &w, py::object encryption_obj)
{
    std::string owner;
    std::string user;

    py::dict encryption;

    bool aes      = true;
    bool metadata = true;
    std::map<std::string, bool> allow;
    int encryption_level = 6;

    if (py::isinstance<py::tuple>(encryption_obj)) {
        encryption = encryption_obj.attr("_asdict")();
    } else {
        encryption = encryption_obj;
    }

    if (encryption.contains("R")) {
        if (!py::isinstance<py::int_>(encryption["R"]))
            throw py::type_error("Encryption level 'R' must be an integer");
        encryption_level = py::int_(encryption["R"]);
    }
    if (encryption_level < 2 || encryption_level > 6)
        throw py::value_error("Invalid encryption level: must be 2, 3, 4 or 6");

    if (encryption_level == 5) {
        python_warning("Encryption R=5 is deprecated");
    }

    owner = encryption_password(encryption, encryption_level, "owner");
    user  = encryption_password(encryption, encryption_level, "user");

    if (encryption.contains("allow")) {
        auto pyallow               = encryption["allow"];
        allow["accessibility"]     = pyallow.attr("accessibility").cast<bool>();
        allow["extract"]           = pyallow.attr("extract").cast<bool>();
        allow["modify_assembly"]   = pyallow.attr("modify_assembly").cast<bool>();
        allow["modify_annotation"] = pyallow.attr("modify_annotation").cast<bool>();
        allow["modify_form"]       = pyallow.attr("modify_form").cast<bool>();
        allow["modify_other"]      = pyallow.attr("modify_other").cast<bool>();
        allow["print_lowres"]      = pyallow.attr("print_lowres").cast<bool>();
        allow["print_highres"]     = pyallow.attr("print_highres").cast<bool>();
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
        throw py::value_error(
            "Cannot encrypt metadata unless AES encryption is enabled");
    }

    qpdf_r3_print_e print;
    if (allow["print_highres"])
        print = qpdf_r3p_full;
    else if (allow["print_lowres"])
        print = qpdf_r3p_low;
    else
        print = qpdf_r3p_none;

    if (encryption_level == 6) {
        w.setR6EncryptionParameters(user.c_str(),
            owner.c_str(),
            allow["accessibility"],
            allow["extract"],
            allow["modify_assembly"],
            allow["modify_annotation"],
            allow["modify_form"],
            allow["modify_other"],
            print,
            metadata);
    } else if (encryption_level == 5) {
        w.setR5EncryptionParameters(user.c_str(),
            owner.c_str(),
            allow["accessibility"],
            allow["extract"],
            allow["modify_assembly"],
            allow["modify_annotation"],
            allow["modify_form"],
            allow["modify_other"],
            print,
            metadata);
    } else if (encryption_level == 4) {
        w.setR4EncryptionParametersInsecure(user.c_str(),
            owner.c_str(),
            allow["accessibility"],
            allow["extract"],
            allow["modify_assembly"],
            allow["modify_annotation"],
            allow["modify_form"],
            allow["modify_other"],
            print,
            metadata,
            aes);
    } else if (encryption_level == 3) {
        w.setR3EncryptionParametersInsecure(user.c_str(),
            owner.c_str(),
            allow["accessibility"],
            allow["extract"],
            allow["modify_assembly"],
            allow["modify_annotation"],
            allow["modify_form"],
            allow["modify_other"],
            print);
    } else if (encryption_level == 2) {
        w.setR2EncryptionParametersInsecure(user.c_str(),
            owner.c_str(),
            (print != qpdf_r3p_none),
            allow["modify_assembly"],
            allow["extract"],
            allow["modify_annotation"]);
    }
}

typedef std::pair<std::string, int> pdf_version_extension;

pdf_version_extension get_version_extension(py::object ver_ext)
{
    std::string version = "";
    int extension       = 0;
    try {
        version   = ver_ext.cast<std::string>();
        extension = 0;
    } catch (const py::cast_error &) {
        try {
            auto version_ext = ver_ext.cast<pdf_version_extension>();
            version          = version_ext.first;
            extension        = version_ext.second;
        } catch (const py::cast_error &) {
            throw py::type_error("PDF version must be a tuple: (str, int)");
        }
    }
    return pdf_version_extension(version, extension);
}

void save_pdf(QPDF &q,
    py::object stream,
    bool static_id                          = false,
    bool preserve_pdfa                      = true,
    py::object min_version                  = py::none(),
    py::object force_version                = py::none(),
    bool fix_metadata_version               = true,
    bool compress_streams                   = true,
    py::object stream_decode_level          = py::none(),
    qpdf_object_stream_e object_stream_mode = qpdf_o_preserve,
    bool normalize_content                  = false,
    bool linearize                          = false,
    bool qdf                                = false,
    py::object progress                     = py::none(),
    py::object encryption                   = py::none(),
    bool samefile_check                     = true,
    bool recompress_flate                   = false,
    bool deterministic_id                   = false)
{
    QPDFWriter w(q);

    if (static_id) {
        w.setStaticID(true);
    }
    if (deterministic_id) {
        w.setDeterministicID(true);
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
    w.setRecompressFlate(recompress_flate);

    std::string description = py::repr(stream);

    // We must set up the output pipeline before we configure encryption
    Pl_PythonOutput output_pipe(description.c_str(), stream);
    w.setOutputPipeline(&output_pipe);

    // Possibilities:
    // encryption=True -> preserve existing
    // encryption=False -> remove encryption
    // encryption=None -> remove encryption
    // encryption=<dict or NamedTuple> apply new encryption settings

    bool removing_encryption =
        encryption.is_none() || encryption.equal(py::bool_(false));
    if (!removing_encryption) {
        if ((normalize_content || !stream_decode_level.is_none())) {
            throw py::value_error("cannot save with encryption and normalize_content "
                                  "or stream_decode_level");
        }
    }
    bool preserving_encryption = encryption.equal(py::bool_(true));

    if (preserving_encryption) {
        if (!q.isEncrypted()) {
            throw py::value_error("can't preserve encryption parameters on "
                                  "a file with no encryption");
        }
        w.setPreserveEncryption(true); // Keep existing encryption
    } else if (removing_encryption) {
        // Note: encryption.equal(py::bool_(false)) != !preserving_encryption
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
        auto reporter = std::shared_ptr<QPDFWriter::ProgressReporter>(
            new PikeProgressReporter(progress));
        w.registerProgressReporter(reporter);
    }

    w.write();
}

void init_qpdf(py::module_ &m)
{
    QPDF::registerStreamFilter("/JBIG2Decode", &JBIG2StreamFilter::factory);

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

    py::class_<QPDF, std::shared_ptr<QPDF>>(
        m, "Pdf", "In-memory representation of a PDF", py::dynamic_attr())
        .def_static("new",
            []() {
                auto q = std::make_shared<QPDF>();
                q->emptyPDF();
                qpdf_basic_settings(*q);
                return q;
            })
        .def_static("_open",
            open_pdf,
            py::arg("stream"),
            py::kw_only(),
            py::arg("password")                = "",
            py::arg("hex_password")            = false,
            py::arg("ignore_xref_streams")     = false,
            py::arg("suppress_warnings")       = true,
            py::arg("attempt_recovery")        = true,
            py::arg("inherit_page_attributes") = true,
            py::arg("access_mode")             = access_mode_e::access_default,
            py::arg("description")             = "",
            py::arg("closing_stream")          = false)
        .def("__repr__",
            [](QPDF &q) {
                return std::string("<pikepdf.Pdf description='") + q.getFilename() +
                       std::string("'>");
            })
        .def_property_readonly("filename", &QPDF::getFilename)
        .def_property_readonly("pdf_version", &QPDF::getPDFVersion)
        .def_property_readonly("extension_level", &QPDF::getExtensionLevel)
        .def_property_readonly("Root", &QPDF::getRoot)
        .def_property_readonly("trailer",
            &QPDF::getTrailer // LCOV_EXCL_LINE
            )
        .def_property_readonly(
            "pages",
            [](std::shared_ptr<QPDF> q) { return PageList(q); },
            py::return_value_policy::reference_internal)
        .def_property_readonly("_pages", &QPDF::getAllPages)
        .def_property_readonly("is_encrypted", &QPDF::isEncrypted)
        .def_property_readonly("is_linearized", &QPDF::isLinearized)
        .def(
            "check_linearization",
            [](QPDF &q, py::object stream) {
                py::scoped_estream_redirect redirector(std::cerr, stream);
                return q.checkLinearization();
            },
            py::arg_v(
                "stream", py::module_::import("sys").attr("stderr"), "sys.stderr"))
        .def("get_warnings", // this is a def because it modifies state by clearing
                             // warnings
            [](QPDF &q) {
                py::list warnings;
                for (auto w : q.getWarnings()) {
                    warnings.append(w.what());
                }
                return warnings;
            })
        .def("show_xref_table",
            &QPDF::showXRefTable,
            py::call_guard<py::scoped_ostream_redirect>())
        .def(
            "_add_page",
            [](QPDF &q, QPDFObjectHandle &page, bool first = false) {
                q.addPage(page, first);
            },
            py::arg("page"),
            py::arg("first") = false)
        .def("_remove_page", &QPDF::removePage)
        .def("remove_unreferenced_resources",
            [](QPDF &q) {
                QPDFPageDocumentHelper helper(q);
                helper.removeUnreferencedResources();
            })
        .def("_save",
            save_pdf,
            py::arg("stream"),
            py::kw_only(),
            py::arg("static_id")            = false,
            py::arg("preserve_pdfa")        = true,
            py::arg("min_version")          = "",
            py::arg("force_version")        = "",
            py::arg("fix_metadata_version") = true,
            py::arg("compress_streams")     = true,
            py::arg("stream_decode_level")  = py::none(),
            py::arg("object_stream_mode")   = qpdf_object_stream_e::qpdf_o_preserve,
            py::arg("normalize_content")    = false,
            py::arg("linearize")            = false,
            py::arg("qdf")                  = false,
            py::arg("progress")             = py::none(),
            py::arg("encryption")           = py::none(),
            py::arg("samefile_check")       = true,
            py::arg("recompress_flate")     = false,
            py::arg("deterministic_id")     = false)
        .def("_get_object_id", &QPDF::getObjectByID)
        .def(
            "get_object",
            [](QPDF &q, std::pair<int, int> objgen) {
                return q.getObjectByID(objgen.first, objgen.second);
            },
            py::arg("objgen"))
        .def(
            "get_object",
            [](QPDF &q, int objid, int gen) { return q.getObjectByID(objid, gen); },
            py::arg("objid"),
            py::arg("gen"))
        .def_property_readonly(
            "objects",
            [](QPDF &q) { return q.getAllObjects(); },
            py::return_value_policy::reference_internal)
        .def("make_indirect", &QPDF::makeIndirectObject, py::arg("h"))
        .def(
            "make_indirect",
            [](QPDF &q, py::object obj) -> QPDFObjectHandle {
                return q.makeIndirectObject(objecthandle_encode(obj));
            },
            py::arg("obj"))
        .def(
            "copy_foreign",
            [](QPDF &q, QPDFObjectHandle &h) -> QPDFObjectHandle {
                return q.copyForeignObject(h);
            },
            py::arg("h"))
        .def("copy_foreign",
            [](QPDF &q, QPDFPageObjectHelper &poh) -> QPDFPageObjectHelper {
                throw py::notimpl_error("Use pikepdf.Pdf.pages interface to copy "
                                        "pages from one PDF to another.");
            })
        .def("_replace_object",
            [](QPDF &q, std::pair<int, int> objgen, QPDFObjectHandle &h) {
                q.replaceObject(objgen.first, objgen.second, h);
            })
        .def("_swap_objects",
            [](QPDF &q, std::pair<int, int> objgen1, std::pair<int, int> objgen2) {
                QPDFObjGen o1(objgen1.first, objgen1.second);
                QPDFObjGen o2(objgen2.first, objgen2.second);
                q.swapObjects(o1, o2);
            })
        .def(
            "_close",
            [](QPDF &q) { q.closeInputSource(); },
            "Used to implement Pdf.close().")
        .def("_decode_all_streams_and_discard",
            [](QPDF &q) {
                QPDFWriter w(q);
                Pl_Discard discard;
                w.setOutputPipeline(&discard);
                w.setDecodeLevel(qpdf_dl_all);
                try {
                    w.write();
                } catch (py::error_already_set &e) {
                    auto cls_dependency_error =
                        py::module_::import("pikepdf._exceptions")
                            .attr("DependencyError");
                    if (e.matches(cls_dependency_error)) {
                        python_warning(
                            "pikepdf is missing some specialized decoders "
                            "(probably JBIG2) so not all stream contents can be "
                            "tested.");
                        w.setDecodeLevel(qpdf_dl_generalized);
                        w.write();
                    } else {
                        throw;
                    }
                }
            })
        .def_property_readonly(
            "_allow_accessibility", [](QPDF &q) { return q.allowAccessibility(); })
        .def_property_readonly(
            "_allow_extract", [](QPDF &q) { return q.allowExtractAll(); })
        .def_property_readonly(
            "_allow_print_lowres", [](QPDF &q) { return q.allowPrintLowRes(); })
        .def_property_readonly(
            "_allow_print_highres", [](QPDF &q) { return q.allowPrintHighRes(); })
        .def_property_readonly(
            "_allow_modify_assembly", [](QPDF &q) { return q.allowModifyAssembly(); })
        .def_property_readonly(
            "_allow_modify_form", [](QPDF &q) { return q.allowModifyForm(); })
        .def_property_readonly("_allow_modify_annotation",
            [](QPDF &q) { return q.allowModifyAnnotation(); })
        .def_property_readonly(
            "_allow_modify_other", [](QPDF &q) { return q.allowModifyOther(); })
        .def_property_readonly(
            "_allow_modify_all", [](QPDF &q) { return q.allowModifyAll(); })
        .def_property_readonly("_encryption_data",
            [](QPDF &q) {
                int R                                   = 0;
                int P                                   = 0;
                int V                                   = 0;
                QPDF::encryption_method_e stream_method = QPDF::e_unknown;
                QPDF::encryption_method_e string_method = QPDF::e_unknown;
                QPDF::encryption_method_e file_method   = QPDF::e_unknown;
                if (!q.isEncrypted(R, P, V, stream_method, string_method, file_method))
                    return py::dict();

                auto user_passwd    = q.getTrimmedUserPassword();
                auto encryption_key = q.getEncryptionKey();

                return py::dict(py::arg("R")  = R,
                    py::arg("P")              = P,
                    py::arg("V")              = V,
                    py::arg("stream")         = stream_method,
                    py::arg("string")         = string_method,
                    py::arg("file")           = file_method,
                    py::arg("user_passwd")    = py::bytes(user_passwd),
                    py::arg("encryption_key") = py::bytes(encryption_key));
            })
        .def_property_readonly("user_password_matched", &QPDF::userPasswordMatched)
        .def_property_readonly("owner_password_matched", &QPDF::ownerPasswordMatched)
        .def("generate_appearance_streams",
            [](QPDF &q) {
                QPDFAcroFormDocumentHelper afdh(q);
                afdh.generateAppearancesIfNeeded();
            })
        .def(
            "flatten_annotations",
            [](QPDF &q, std::string mode) {
                QPDFPageDocumentHelper dh(q);
                auto required  = 0;
                auto forbidden = an_invisible | an_hidden;

                if (mode == "screen") {
                    forbidden |= an_no_view;
                } else if (mode == "print") {
                    required |= an_print;
                } else if (mode == "" || mode == "all") {
                    // No op
                } else {
                    throw py::value_error(
                        "Mode must be one of 'all', 'screen', 'print'.");
                }

                dh.flattenAnnotations(required, forbidden);
            },
            py::arg("mode") = "all") // class Pdf
        .def_property_readonly(
            "attachments", [](QPDF &q) { return QPDFEmbeddedFileDocumentHelper(q); });
}
