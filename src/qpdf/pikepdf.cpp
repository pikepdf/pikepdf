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

#include "pikepdf.h"

#include <qpdf/QPDFExc.hh>
#include <qpdf/QPDFSystemError.hh>
#include <qpdf/QUtil.hh>

#include <pybind11/stl.h>
#include <pybind11/iostream.h>
#include <pybind11/buffer_info.h>

#include "qpdf_pagelist.h"
#include "utils.h"

uint DECIMAL_PRECISION = 15;
bool MMAP_DEFAULT = false;

class TemporaryErrnoChange {
public:
    TemporaryErrnoChange(int val) {
        stored = errno;
        errno = val;
    }
    ~TemporaryErrnoChange() {
        errno = stored;
    }
private:
    int stored;
};


PYBIND11_MODULE(_qpdf, m) {
    //py::options options;
    //options.disable_function_signatures();

    m.doc() = "pikepdf provides a Pythonic interface for QPDF";

    m.def("qpdf_version", &QPDF::QPDFVersion, "Get libqpdf version");

    init_qpdf(m);
    init_pagelist(m);
    init_object(m);
    init_annotation(m);
    init_page(m);

    m.def("utf8_to_pdf_doc",
        [](py::str utf8, char unknown) {
            std::string pdfdoc;
            bool success = QUtil::utf8_to_pdf_doc(std::string(utf8), pdfdoc, unknown);
            return py::make_tuple(success, py::bytes(pdfdoc));
        }
    );
    m.def("pdf_doc_to_utf8",
        [](py::bytes pdfdoc) -> py::str {
            return py::str(QUtil::pdf_doc_to_utf8(pdfdoc));
        }
    );

    m.def("_test_file_not_found",
        []() -> void {
            auto file = QUtil::safe_fopen("does_not_exist__42", "rb");
            if (file)
                fclose(file);
        },
        "Used to test that C++ system error -> Python exception propagation works."
    );

    m.def("set_decimal_precision",
        [](uint prec) {
            DECIMAL_PRECISION = prec;
            return DECIMAL_PRECISION;
        },
        "Set the number of decimal digits to use when converting floats."
    );
    m.def("get_decimal_precision",
        []() {
            return DECIMAL_PRECISION;
        },
        "Get the number of decimal digits to use when converting floats."
    );
    m.def("set_access_default_mmap",
        [](bool mmap) {
            MMAP_DEFAULT = mmap;
            return mmap;
        },
        "If set to true, ``pikepdf.open(...access_mode=access_default)`` will use mmap."
    );

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
        } catch (const QPDFSystemError &e) {
            if (e.getErrno() != 0) {
                TemporaryErrnoChange errno_holder(e.getErrno());
                PyErr_SetFromErrnoWithFilename(PyExc_OSError, e.getDescription().c_str());
            } else {
                exc_main(e.what());
            }
        }
    });


#if defined(VERSION_INFO) && defined(_MSC_VER)
#define msvc_inner_stringify(s) #s
#define msvc_stringify(s) msvc_inner_stringify(s)
    m.attr("__version__") = msvc_stringify(VERSION_INFO);
#undef msvc_stringify
#undef msvc_inner_stringify
#elif defined(VERSION_INFO)
    m.attr("__version__") = VERSION_INFO;
#else
    m.attr("__version__") = "dev";
#endif
}
