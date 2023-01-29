// SPDX-FileCopyrightText: 2022 James R. Barlow
// SPDX-License-Identifier: MPL-2.0

#include <sstream>
#include <type_traits>
#include <cerrno>
#include <cstring>
#include <cstdio>
#include <regex>
#include <vector>
#include <utility>

#include "pikepdf.h"

#include <qpdf/QPDFExc.hh>
#include <qpdf/QPDFSystemError.hh>
#include <qpdf/QPDFUsage.hh>
#include <qpdf/QUtil.hh>
#include <qpdf/QPDFLogger.hh>
#include <qpdf/Pl_Flate.hh>

#include <pybind11/stl.h>
#include <pybind11/iostream.h>
#include <pybind11/buffer_info.h>

#include "qpdf_pagelist.h"
#include "utils.h"
#include "parsers.h"

uint DECIMAL_PRECISION = 15;
bool MMAP_DEFAULT      = false;

class TemporaryErrnoChange {
public:
    TemporaryErrnoChange(int val)
    {
        stored = errno;
        errno  = val;
    }
    ~TemporaryErrnoChange() { errno = stored; }

private:
    int stored;
};

enum pikepdf_error_type {
    error_type_pdferror,
    error_type_foreign,
    error_type_cpp,
};

auto rewrite_qpdf_logic_error_msg(std::string msg)
{
    using match_replace = std::pair<std::regex, std::string>;

    const static std::vector<match_replace> replacements = {
        match_replace{"QPDF::copyForeign(?:Object)?", "pikepdf.copy_foreign"},
        match_replace{"QPDFObjectHandle", "pikepdf.Object"},
        match_replace{"QPDF", "pikepdf.Pdf"},
    };

    for (auto mr : replacements) {
        msg = std::regex_replace(msg, mr.first, mr.second);
    }
    return msg;
}

auto translate_qpdf_logic_error(std::string msg)
{
    pikepdf_error_type errtype;
    msg = rewrite_qpdf_logic_error_msg(msg);

    if (std::regex_search(msg, std::regex("pikepdf.copy_foreign")))
        errtype = error_type_foreign;
    else if (std::regex_search(msg, std::regex("pikepdf.")))
        errtype = error_type_pdferror;
    else
        errtype = error_type_cpp;
    return std::pair<std::string, pikepdf_error_type>(msg, errtype);
}

auto translate_qpdf_logic_error(const std::exception &e)
{
    return translate_qpdf_logic_error(std::string(e.what()));
}

bool is_data_decoding_error(const std::runtime_error &e)
{
    static const std::regex decoding_error_pattern(
        "character out of range"
        "|broken end-of-data sequence in base 85 data"
        "|unexpected z during base 85 decode"
        "|TIFFPredictor created with"
        "|Pl_LZWDecoder:"
        "|Pl_Flate:"
        "|Pl_DCT:"
        "|stream inflate:",
        std::regex_constants::icase);

    return std::regex_search(e.what(), decoding_error_pattern);
}

bool is_destroyed_object_error(const std::runtime_error &e)
{
    static const std::regex error_pattern(
        "operation for \\w+ attempted on object of type destroyed",
        std::regex_constants::icase);

    return std::regex_search(e.what(), error_pattern);
}

PYBIND11_MODULE(_core, m)
{
    // py::options options;
    // options.disable_function_signatures();

    m.doc() = "pikepdf provides a Pythonic interface for QPDF";

    m.def("qpdf_version", &QPDF::QPDFVersion, "Get libqpdf version");

    // -- Core objects --
    init_logger(m);
    init_qpdf(m);
    init_pagelist(m);
    init_object(m);
    init_job(m);

    // -- Support objects (alphabetize order) --
    init_annotation(m);
    init_embeddedfiles(m);
    init_nametree(m);
    init_numbertree(m);
    init_page(m);
    init_parsers(m);
    init_rectangle(m);
    init_tokenfilter(m);

    // -- Module level functions --
    m.def("utf8_to_pdf_doc",
         [](py::str utf8, char unknown) {
             std::string pdfdoc;
             bool success = QUtil::utf8_to_pdf_doc(std::string(utf8), pdfdoc, unknown);
             return py::make_tuple(success, py::bytes(pdfdoc));
         })
        .def("pdf_doc_to_utf8",
            [](py::bytes pdfdoc) -> py::str {
                return py::str(QUtil::pdf_doc_to_utf8(pdfdoc));
            })
        .def(
            "_test_file_not_found",
            []() -> void { (void)QUtil::safe_fopen("does_not_exist__42", "rb"); },
            "Used to test that C++ system error -> Python exception propagation works.")
        .def(
            "_translate_qpdf_logic_error",
            [](std::string s) { return translate_qpdf_logic_error(s).first; },
            "Used to test interpretation of QPDF errors.")
        .def(
            "_log_info",
            [](std::string s) { return get_pikepdf_logger()->info(s); },
            "Used to test routing of QPDF's logger to Python logging.")
        .def(
            "set_decimal_precision",
            [](uint prec) {
                DECIMAL_PRECISION = prec;
                return DECIMAL_PRECISION;
            },
            "Set the number of decimal digits to use when converting floats.")
        .def(
            "get_decimal_precision",
            []() { return DECIMAL_PRECISION; },
            "Get the number of decimal digits to use when converting floats.")
        .def(
            "get_access_default_mmap",
            []() { return MMAP_DEFAULT; },
            "Return True if default access is to use mmap.")
        .def(
            "set_access_default_mmap",
            [](bool mmap) { MMAP_DEFAULT = mmap; },
            "If True, ``pikepdf.open(...access_mode=access_default)`` will use mmap.")
        .def(
            "set_flate_compression_level",
            [](int level) {
                if (-1 <= level && level <= 9)
                    Pl_Flate::setCompressionLevel(level);
                else
                    throw py::value_error(
                        "Flate compression level must be between 0 and 9 (or -1)");
            },
            R"~~~(
            Set the compression level whenever the Flate compression algorithm is used.

            Args:
                level: -1 (default), 0 (no compression), 1 to 9 (increasing compression)
            )~~~")
        .def("_unparse_content_stream", unparse_content_stream);

    // -- Exceptions --
    static py::exception<QPDFExc> exc_main(m, "PdfError");
    static py::exception<QPDFExc> exc_password(m, "PasswordError");
    static py::exception<QPDFExc> exc_datadecoding(m, "DataDecodingError");
    static py::exception<QPDFUsage> exc_usage(m, "JobUsageError");
    static py::exception<std::logic_error> exc_foreign(m, "ForeignObjectError");
    static py::exception<std::runtime_error> exc_destroyedobject(
        m, "DeletedObjectError");
    py::register_exception_translator([](std::exception_ptr p) {
        try {
            if (p)
                std::rethrow_exception(p);
        } catch (const QPDFExc &e) {
            if (e.getErrorCode() == qpdf_e_password) {
                exc_password(e.what());
            } else {
                exc_main(e.what());
            }
        } catch (const QPDFSystemError &e) {
            if (e.getErrno() != 0) {
                TemporaryErrnoChange errno_holder(e.getErrno());
                PyErr_SetFromErrnoWithFilename(
                    PyExc_OSError, e.getDescription().c_str());
            } else {
                exc_main(e.what());
            }
        } catch (const QPDFUsage &e) {
            exc_usage(e.what());
        } catch (const std::logic_error &e) {
            auto trans = translate_qpdf_logic_error(e);
            if (trans.second == error_type_foreign)
                exc_foreign(trans.first.c_str());
            else if (trans.second == error_type_pdferror)
                exc_main(trans.first.c_str());
            else
                std::rethrow_exception(p);
        } catch (const std::runtime_error &e) {
            if (is_data_decoding_error(e))
                exc_datadecoding(e.what());
            else if (is_destroyed_object_error(e))
                exc_destroyedobject(e.what());
            else
                std::rethrow_exception(p);
        }
    });

    // clang-format off
#if defined(VERSION_INFO) && defined(_MSC_VER)
#    define msvc_inner_stringify(s) #s
#    define msvc_stringify(s) msvc_inner_stringify(s)
    m.attr("__version__") = msvc_stringify(VERSION_INFO);
#    undef msvc_stringify
#    undef msvc_inner_stringify
#elif defined(VERSION_INFO)
    m.attr("__version__") = VERSION_INFO;
#else
    m.attr("__version__") = "dev";
#endif
    // clang-format on
}
