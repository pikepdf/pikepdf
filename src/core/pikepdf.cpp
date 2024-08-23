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
#include <pybind11/gil_safe_call_once.h>

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
        match_replace{"QPDFPageObjectHelper", "pikepdf.Page"},
        match_replace{"QPDF", "pikepdf.Pdf"},
    };

    for (auto [regex, replacement] : replacements) {
        msg = std::regex_replace(msg, regex, replacement);
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

    m.doc()            = "pikepdf provides a Pythonic interface for qpdf";
    m.attr("__name__") = "pikepdf._core";
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
    init_matrix(m);
    init_nametree(m);
    init_numbertree(m);
    init_page(m);
    init_parsers(m);
    init_rectangle(m);
    init_tokenfilter(m);

    auto m_test = m.def_submodule("_test", "pikepdf._core test functions");
    m_test
        .def(
            "fopen_nonexistent_file",
            []() -> void { (void)QUtil::safe_fopen("does_not_exist__42", "rb"); },
            "Used to test that C++ system error -> Python exception propagation works.")
        .def(
            "log_info",
            [](std::string s) { return get_pikepdf_logger()->info(s); },
            "Used to test routing of qpdf's logger to Python logging.");

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
            "_translate_qpdf_logic_error",
            [](std::string s) { return translate_qpdf_logic_error(s).first; },
            "Used to test interpretation of qpdf errors.")
        .def("set_decimal_precision",
            [](uint prec) {
                DECIMAL_PRECISION = prec;
                return DECIMAL_PRECISION;
            })
        .def("get_decimal_precision", []() { return DECIMAL_PRECISION; })
        .def(
            "get_access_default_mmap",
            []() { return MMAP_DEFAULT; },
            "Return True if default access is to use mmap.")
        .def(
            "set_access_default_mmap",
            [](bool mmap) {
                MMAP_DEFAULT = mmap;
                return MMAP_DEFAULT;
            },
            "If True, ``pikepdf.open(...access_mode=access_default)`` will use mmap.")
        .def("set_flate_compression_level",
            [](int level) {
                if (-1 <= level && level <= 9) {
                    Pl_Flate::setCompressionLevel(level);
                    return level;
                }
                throw py::value_error(
                    "Flate compression level must be between 0 and 9 (or -1)");
            })
        .def("_unparse_content_stream", unparse_content_stream);

    // -- Exceptions --
    // clang-format off
    PYBIND11_CONSTINIT static py::gil_safe_call_once_and_store<py::object> exc_main;
    exc_main.call_once_and_store_result(
        [&]() { return py::exception<QPDFExc>(m, "PdfError"); });
    PYBIND11_CONSTINIT static py::gil_safe_call_once_and_store<py::object> exc_password;
    exc_password.call_once_and_store_result(
        [&]() { return py::exception<QPDFExc>(m, "PasswordError"); });
    PYBIND11_CONSTINIT static py::gil_safe_call_once_and_store<py::object> exc_datadecoding;
    exc_datadecoding.call_once_and_store_result(
        [&]() { return py::exception<QPDFExc>(m, "DataDecodingError"); });
    PYBIND11_CONSTINIT static py::gil_safe_call_once_and_store<py::object> exc_usage;
    exc_usage.call_once_and_store_result(
        [&]() { return py::exception<QPDFUsage>(m, "JobUsageError"); });
    PYBIND11_CONSTINIT static py::gil_safe_call_once_and_store<py::object> exc_foreign;
    exc_foreign.call_once_and_store_result(
        [&]() { return py::exception<std::logic_error>(m, "ForeignObjectError"); });
    PYBIND11_CONSTINIT static py::gil_safe_call_once_and_store<py::object> exc_destroyedobject;
    exc_destroyedobject.call_once_and_store_result(
        [&]() { return py::exception<std::runtime_error>(m, "DeletedObjectError"); });
    // clang-format on
    py::register_exception_translator([](std::exception_ptr p) {
        try {
            if (p)
                std::rethrow_exception(p);
        } catch (const QPDFExc &e) {
            if (e.getErrorCode() == qpdf_e_password) {
                py::set_error(exc_password.get_stored(), e.what());
            } else {
                py::set_error(exc_main.get_stored(), e.what());
            }
        } catch (const QPDFSystemError &e) {
            if (e.getErrno() != 0) {
                TemporaryErrnoChange errno_holder(e.getErrno());
                PyErr_SetFromErrnoWithFilename(
                    PyExc_OSError, e.getDescription().c_str());
            } else {
                py::set_error(exc_main.get_stored(), e.what());
            }
        } catch (const QPDFUsage &e) {
            py::set_error(exc_usage.get_stored(), e.what());
        } catch (const std::logic_error &e) {
            auto trans = translate_qpdf_logic_error(e);
            if (trans.second == error_type_foreign)
                py::set_error(exc_foreign.get_stored(), trans.first.c_str());
            else if (trans.second == error_type_pdferror)
                py::set_error(exc_main.get_stored(), trans.first.c_str());
            else
                std::rethrow_exception(p);
        } catch (const std::runtime_error &e) {
            if (is_data_decoding_error(e))
                py::set_error(exc_datadecoding.get_stored(), e.what());
            else if (is_destroyed_object_error(e))
                py::set_error(exc_destroyedobject.get_stored(), e.what());
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
