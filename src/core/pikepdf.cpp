// SPDX-FileCopyrightText: 2022 James R. Barlow
// SPDX-License-Identifier: MPL-2.0

#include <atomic>
#include <cerrno>
#include <cstdio>
#include <cstring>
#include <regex>
#include <sstream>
#include <type_traits>
#include <utility>
#include <vector>

#include "pikepdf.h"

#include <qpdf/Pl_Flate.hh>
#include <qpdf/QPDFExc.hh>
#include <qpdf/QPDFLogger.hh>
#include <qpdf/QPDFSystemError.hh>
#include <qpdf/QPDFUsage.hh>
#include <qpdf/QUtil.hh>
#include <qpdf/global.hh>

#include "namepath.h"
#include "parsers.h"
#include "qpdf_pagelist.h"
#include "utils.h"

static constinit std::atomic<uint> DECIMAL_PRECISION = 15;
static constinit std::atomic<bool> MMAP_DEFAULT = false;
static constinit std::atomic<bool> EXPLICIT_CONVERSION_MODE = false;

// Exception class pointers, populated once in NB_MODULE and then read-only.
// Borrowed references - the owning strong reference lives in the module dict
// via m.attr(...) = py::handle(ptr), so the PyObject remains valid for the
// module's lifetime (i.e. as long as the exception translator can run).
// std::atomic provides the memory-visibility guarantee across threads that
// the C++ memory model requires; CPython's import machinery already serializes
// NB_MODULE, so a single release-store is enough to publish the value.
static constinit std::atomic<PyObject *> exc_main{nullptr};
static constinit std::atomic<PyObject *> exc_password{nullptr};
static constinit std::atomic<PyObject *> exc_datadecoding{nullptr};
static constinit std::atomic<PyObject *> exc_usage{nullptr};
static constinit std::atomic<PyObject *> exc_foreign{nullptr};
static constinit std::atomic<PyObject *> exc_destroyedobject{nullptr};

// Thread-local counter for explicit_conversion() context manager nesting.
// When > 0, the current thread is inside one or more context managers and
// explicit mode takes precedence over the global EXPLICIT_CONVERSION_MODE.
static thread_local int thread_explicit_depth = 0;

uint get_decimal_precision()
{
    return DECIMAL_PRECISION.load();
}
bool get_mmap_default()
{
    return MMAP_DEFAULT.load();
}
bool get_explicit_conversion_mode()
{
    // Thread-local context manager takes precedence over global setting
    if (thread_explicit_depth > 0) {
        return true;
    }
    return EXPLICIT_CONVERSION_MODE.load();
}

class TemporaryErrnoChange {
public:
    TemporaryErrnoChange(int val)
    {
        stored = errno;
        errno = val;
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

bool is_object_type_assertion_error(const std::runtime_error &e)
{
    static const std::regex error_pattern(
        "operation for \\w+ attempted on object of type (?!destroyed)\\w+",
        std::regex_constants::icase);

    return std::regex_search(e.what(), error_pattern);
}

NB_MODULE(_core, m)
{
    m.doc() = "pikepdf provides a Pythonic interface for qpdf";
    m.attr("__name__") = "pikepdf._core";
    m.def("qpdf_version", &QPDF::QPDFVersion, "Get libqpdf version");

    // -- Core objects --
    init_logger(m);
    init_qpdf(m);
    init_pagelist(m);
    init_object(m);
    init_job(m);

    // -- Support objects (alphabetize order) --
    init_acroform(m);
    init_annotation(m);
    init_embeddedfiles(m);
    init_matrix(m);
    init_namepath(m);
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
         [](py::str utf8, py::bytes unknown) {
             std::string pdfdoc;
             const char *unk_ptr = static_cast<const char *>(unknown.data());
             char unk = (unknown.size() > 0) ? unk_ptr[0] : '?';
             bool success =
                 QUtil::utf8_to_pdf_doc(py::cast<std::string>(utf8), pdfdoc, unk);
             return py::make_tuple(success, py::bytes(pdfdoc.data(), pdfdoc.size()));
         })
        .def("pdf_doc_to_utf8",
            [](py::bytes pdfdoc) -> py::str {
                auto pdfdoc_str = to_string(pdfdoc);
                auto utf8 = QUtil::pdf_doc_to_utf8(pdfdoc_str);
                return py::steal<py::str>(
                    PyUnicode_FromStringAndSize(utf8.data(), utf8.size()));
            })
        .def(
            "_translate_qpdf_logic_error",
            [](std::string s) { return translate_qpdf_logic_error(s).first; },
            "Used to test interpretation of qpdf errors.")
        .def("set_decimal_precision",
            [](uint prec) { return DECIMAL_PRECISION.exchange(prec); })
        .def("get_decimal_precision", []() { return DECIMAL_PRECISION.load(); })
        .def(
            "get_access_default_mmap",
            []() { return MMAP_DEFAULT.load(); },
            "Return True if default access is to use mmap.")
        .def(
            "set_access_default_mmap",
            [](bool mmap) { return MMAP_DEFAULT.exchange(mmap); },
            "If True, ``pikepdf.open(...access_mode=access_default)`` will use mmap.")
        .def(
            "_get_explicit_conversion_mode",
            []() { return EXPLICIT_CONVERSION_MODE.load(); },
            "Return True if explicit conversion mode is enabled (global baseline).")
        .def(
            "_get_effective_explicit_mode",
            []() { return get_explicit_conversion_mode(); },
            "Return True if explicit mode is active (includes thread-local override).")
        .def(
            "_set_explicit_conversion_mode",
            [](bool mode) { return EXPLICIT_CONVERSION_MODE.exchange(mode); },
            "Set explicit conversion mode (global baseline). Returns previous value.")
        .def(
            "_enter_thread_explicit_mode",
            []() { ++thread_explicit_depth; },
            "Enter thread-local explicit conversion mode (for context manager).")
        .def(
            "_exit_thread_explicit_mode",
            []() {
                if (thread_explicit_depth > 0) {
                    --thread_explicit_depth;
                }
            },
            "Exit thread-local explicit conversion mode (for context manager).")
        .def("set_flate_compression_level",
            [](int level) {
                if (-1 <= level && level <= 9) {
                    Pl_Flate::setCompressionLevel(level);
                    return level;
                }
                throw py::value_error(
                    "Flate compression level must be between 0 and 9 (or -1)");
            })
        .def("_unparse_content_stream", unparse_content_stream)
        .def(
            "set_inspection_mode",
            [](bool mode) {
                if (!mode && qpdf::global::options::inspection_mode()) {
                    throw std::runtime_error("inspection mode is enabled and cannot be disabled");
                }
                qpdf::global::options::inspection_mode(mode);
            },
            "Enable qpdf inspection mode (global, irreversible).")
        .def(
            "get_inspection_mode",
            []() { return qpdf::global::options::inspection_mode(); },
            "Return True if qpdf inspection mode is enabled.");

    // -- Exceptions --
    // Create exception types using the Python C API. We need multiple Python
    // exception classes mapping to the same C++ type (QPDFExc), which
    // nanobind's nb::exception<T> cannot express directly.
    //
    // The module attr holds the owning strong reference. We also publish a
    // borrowed pointer into the file-scope std::atomic so the exception
    // translator can dispatch without re-importing pikepdf._core on every
    // exception (which was creating reference-count churn and, together with
    // other migration-era regressions, visible leak-report entries at
    // interpreter shutdown).
    auto publish = [](std::atomic<PyObject *> &slot,
                       py::module_ &m,
                       const char *attr,
                       PyObject *cls) {
        // NB_MODULE is serialized by CPython's import machinery, so a single
        // release-store is sufficient to publish the value to any thread
        // that later observes the module via the import system.
        slot.store(cls, std::memory_order_release);
        m.attr(attr) = py::handle(cls);
    };

    publish(exc_main,
        m,
        "PdfError",
        PyErr_NewException("pikepdf._core.PdfError", PyExc_Exception, nullptr));
    publish(exc_password,
        m,
        "PasswordError",
        PyErr_NewException("pikepdf._core.PasswordError",
            exc_main.load(std::memory_order_relaxed),
            nullptr));
    publish(exc_datadecoding,
        m,
        "DataDecodingError",
        PyErr_NewException("pikepdf._core.DataDecodingError",
            exc_main.load(std::memory_order_relaxed),
            nullptr));
    publish(exc_usage,
        m,
        "JobUsageError",
        PyErr_NewException("pikepdf._core.JobUsageError", PyExc_Exception, nullptr));
    publish(exc_foreign,
        m,
        "ForeignObjectError",
        PyErr_NewException(
            "pikepdf._core.ForeignObjectError", PyExc_Exception, nullptr));
    publish(exc_destroyedobject,
        m,
        "DeletedObjectError",
        PyErr_NewException(
            "pikepdf._core.DeletedObjectError", PyExc_Exception, nullptr));

    py::register_exception_translator([](const std::exception_ptr &p, void *payload) {
        (void)payload;
        try {
            if (p)
                std::rethrow_exception(p);
        } catch (const QPDFExc &e) {
            if (e.getErrorCode() == qpdf_e_password) {
                PyErr_SetString(exc_password.load(std::memory_order_acquire), e.what());
            } else {
                PyErr_SetString(exc_main.load(std::memory_order_acquire), e.what());
            }
        } catch (const QPDFSystemError &e) {
            if (e.getErrno() != 0) {
                TemporaryErrnoChange errno_holder(e.getErrno());
                PyErr_SetFromErrnoWithFilename(
                    PyExc_OSError, e.getDescription().c_str());
            } else {
                PyErr_SetString(exc_main.load(std::memory_order_acquire), e.what());
            }
        } catch (const QPDFUsage &e) {
            PyErr_SetString(exc_usage.load(std::memory_order_acquire), e.what());
        } catch (const std::logic_error &e) {
            auto trans = translate_qpdf_logic_error(e);
            if (trans.second == error_type_foreign)
                PyErr_SetString(
                    exc_foreign.load(std::memory_order_acquire), trans.first.c_str());
            else if (trans.second == error_type_pdferror)
                PyErr_SetString(
                    exc_main.load(std::memory_order_acquire), trans.first.c_str());
            else
                std::rethrow_exception(p);
        } catch (const std::runtime_error &e) {
            if (is_data_decoding_error(e))
                PyErr_SetString(
                    exc_datadecoding.load(std::memory_order_acquire), e.what());
            else if (is_destroyed_object_error(e))
                PyErr_SetString(
                    exc_destroyedobject.load(std::memory_order_acquire), e.what());
            else if (is_object_type_assertion_error(e))
                PyErr_SetString(exc_main.load(std::memory_order_acquire), e.what());
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

#ifdef Py_GIL_DISABLED
    m.attr("__threading__") = "freethreading";
    fprintf(stderr, "Warning: pikepdf freethreading support is unstable\n");
#else
    m.attr("__threading__") = "gil";
#endif
}
