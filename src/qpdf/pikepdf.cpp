/*
 * This Source Code Form is subject to the terms of the Mozilla Public
 * License, v. 2.0. If a copy of the MPL was not distributed with this
 * file, You can obtain one at http://mozilla.org/MPL/2.0/.
 *
 * Copyright (C) 2019, James R. Barlow (https://github.com/jbarlow83/)
 */

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
#include <qpdf/QUtil.hh>
#include <qpdf/Pl_Flate.hh>

#include <pybind11/stl.h>
#include <pybind11/iostream.h>
#include <pybind11/buffer_info.h>

#include "qpdf_pagelist.h"
#include "utils.h"

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

auto translate_qpdf_error(std::string msg)
{
    using match_replace = std::pair<std::regex, std::string>;
    pikepdf_error_type errtype;
    const static std::vector<match_replace> replacements = {
        match_replace{"QPDF::copyForeign(?:Object)?", "pikepdf.copy_foreign"},
        match_replace{"QPDFObjectHandle", "pikepdf.Object"},
        match_replace{"QPDF", "pikepdf.Pdf"},
    };

    for (auto mr : replacements) {
        msg = std::regex_replace(msg, mr.first, mr.second);
    }
    if (std::regex_search(msg, std::regex("pikepdf.copy_foreign")))
        errtype = error_type_foreign;
    else if (std::regex_search(msg, std::regex("pikepdf.")))
        errtype = error_type_pdferror;
    else
        errtype = error_type_cpp;
    return std::pair<std::string, pikepdf_error_type>(msg, errtype);
}

auto translate_qpdf_error(const std::exception &e)
{
    return translate_qpdf_error(std::string(e.what()));
}

PYBIND11_MODULE(_qpdf, m)
{
    // py::options options;
    // options.disable_function_signatures();

    m.doc() = "pikepdf provides a Pythonic interface for QPDF";

    m.def("qpdf_version", &QPDF::QPDFVersion, "Get libqpdf version");

    // -- Core objects --
    init_qpdf(m);
    init_pagelist(m);
    init_object(m);

    // -- Support objects (alphabetize order) --
    init_annotation(m);
    init_page(m);
    init_rectangle(m);

    // -- Module level functions --
    m.def("utf8_to_pdf_doc", [](py::str utf8, char unknown) {
        std::string pdfdoc;
        bool success = QUtil::utf8_to_pdf_doc(std::string(utf8), pdfdoc, unknown);
        return py::make_tuple(success, py::bytes(pdfdoc));
    });
    m.def("pdf_doc_to_utf8", [](py::bytes pdfdoc) -> py::str {
        return py::str(QUtil::pdf_doc_to_utf8(pdfdoc));
    });

    m.def(
        "_test_file_not_found",
        []() -> void { (void)QUtil::safe_fopen("does_not_exist__42", "rb"); },
        "Used to test that C++ system error -> Python exception propagation works.");

    m.def(
        "_translate_qpdf", [](std::string s) { return translate_qpdf_error(s).first; });

    m.def(
        "set_decimal_precision",
        [](uint prec) {
            DECIMAL_PRECISION = prec;
            return DECIMAL_PRECISION;
        },
        "Set the number of decimal digits to use when converting floats.");
    m.def(
        "get_decimal_precision",
        []() { return DECIMAL_PRECISION; },
        "Get the number of decimal digits to use when converting floats.");
    m.def(
        "set_access_default_mmap",
        [](bool mmap) {
            MMAP_DEFAULT = mmap;
            return mmap;
        },
        "If set to true, ``pikepdf.open(...access_mode=access_default)`` will use "
        "mmap.");
    m.def(
        "set_flate_compression_level",
        [](int level) {
            if (0 <= level && level <= 9)
                Pl_Flate::setCompressionLevel(level);
            else
                throw py::value_error(
                    "Flate compression level must be between 0 and 9");
        },
        "Set the compression level whenever the Flate compression algorithm is used.");

    // -- Exceptions --
    static py::exception<QPDFExc> exc_main(m, "PdfError");
    static py::exception<QPDFExc> exc_password(m, "PasswordError");
    static py::exception<std::logic_error> exc_foreign(m, "ForeignObjectError");
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
                    PyExc_OSError, fix_pypy36_const_char(e.getDescription().c_str()));
            } else {
                exc_main(e.what());
            }
        } catch (const std::logic_error &e) {
            auto trans = translate_qpdf_error(e);
            if (trans.second == error_type_foreign)
                exc_foreign(trans.first.c_str());
            else if (trans.second == error_type_pdferror)
                exc_main(trans.first.c_str());
            else
                std::rethrow_exception(p);
        }
    });

#if defined(VERSION_INFO) && defined(_MSC_VER)
#    define msvc_inner_stringify(s) #    s
#    define msvc_stringify(s) msvc_inner_stringify(s)
    m.attr("__version__") = msvc_stringify(VERSION_INFO);
#    undef msvc_stringify
#    undef msvc_inner_stringify
#elif defined(VERSION_INFO)
    m.attr("__version__") = VERSION_INFO;
#else
    m.attr("__version__") = "dev";
#endif
}
