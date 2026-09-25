// SPDX-FileCopyrightText: 2022 James R. Barlow
// SPDX-License-Identifier: MPL-2.0

#include "pikepdf.h"

#include <atomic>
#include <cerrno>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <regex>
#include <string>
#include <string_view>
#include <type_traits>
#include <utility>
#include <vector>

#include <nanobind/stl/string_view.h>

#include <qpdf/Pl_Flate.hh>
#include <qpdf/QPDFExc.hh>
#include <qpdf/QPDFLogger.hh>
#include <qpdf/QPDFSystemError.hh>
#include <qpdf/QPDFUsage.hh>
#include <qpdf/QUtil.hh>
#include <qpdf/qpdf-c.h>

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
static constinit std::atomic<PyObject *> exc_referencecycle{nullptr};

// decimal.Decimal, looked up once in NB_MODULE instead of importing the decimal
// module on every conversion of a Real. The reference is deliberately never
// released: the decimal module keeps the type alive anyway, and releasing it
// during interpreter shutdown would race module teardown.
static constinit std::atomic<PyObject *> decimal_type{nullptr};

// Thread-local stack of conversion mode overrides, pushed by the
// explicit_conversion() and implicit_conversion() context managers. The top of
// the stack takes precedence over both the per-Pdf mode and the global
// EXPLICIT_CONVERSION_MODE.
static thread_local std::vector<ConversionMode> thread_mode_stack;

PyObject *get_data_decoding_error_type()
{
    return exc_datadecoding.load(std::memory_order_acquire);
}

py::handle get_decimal_type()
{
    return decimal_type.load(std::memory_order_acquire);
}

uint get_decimal_precision()
{
    return DECIMAL_PRECISION.load();
}
bool get_mmap_default()
{
    return MMAP_DEFAULT.load();
}

// qpdf's global options and limits that pikepdf.settings exposes by name.
// inspection_mode and fuzz_mode are deliberately absent: neither can be turned
// off once enabled, and both change qpdf behavior in ways unsuited to a library.
static constexpr std::pair<std::string_view, qpdf_param_e> QPDF_GLOBAL_PARAMS[] = {
    {"limit_errors", qpdf_p_limit_errors},
    {"default_limits", qpdf_p_default_limits},
    {"dct_throw_on_corrupt_data", qpdf_p_dct_throw_on_corrupt_data},
    {"doc_max_warnings", qpdf_p_doc_max_warnings},
    {"parser_max_nesting", qpdf_p_parser_max_nesting},
    {"parser_max_errors", qpdf_p_parser_max_errors},
    {"parser_max_container_size", qpdf_p_parser_max_container_size},
    {"parser_max_container_size_damaged", qpdf_p_parser_max_container_size_damaged},
    {"max_stream_filters", qpdf_p_max_stream_filters},
    {"dct_max_memory", qpdf_p_dct_max_memory},
    {"dct_max_progressive_scans", qpdf_p_dct_max_progressive_scans},
    {"flate_max_memory", qpdf_p_flate_max_memory},
    {"png_max_memory", qpdf_p_png_max_memory},
    {"run_length_max_memory", qpdf_p_run_length_max_memory},
    {"tiff_max_memory", qpdf_p_tiff_max_memory},
};

static qpdf_param_e qpdf_global_param(std::string_view name)
{
    for (auto const &[param_name, param] : QPDF_GLOBAL_PARAMS) {
        if (param_name == name)
            return param;
    }
    throw py::value_error(
        ("unknown qpdf global parameter: " + std::string(name)).c_str());
}

static void check_qpdf_global_result(qpdf_result_e result, std::string_view name)
{
    if (result != qpdf_r_ok)
        throw py::value_error(
            ("qpdf rejected global parameter: " + std::string(name)).c_str());
}

bool get_explicit_conversion_mode(QpdfEntry const *owner) noexcept
{
    // Resolution order: thread-local override > per-Pdf mode > global setting.
    if (!thread_mode_stack.empty()) {
        return thread_mode_stack.back() == ConversionMode::explicit_;
    }
    if (owner) {
        auto mode = owner->conversion_mode.load(std::memory_order_relaxed);
        if (mode != ConversionMode::unset) {
            return mode == ConversionMode::explicit_;
        }
    }
    return EXPLICIT_CONVERSION_MODE.load();
}

bool get_explicit_conversion_mode() noexcept
{
    return get_explicit_conversion_mode(nullptr);
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
        // qpdf's ownership check fires when an object that belongs to another
        // Pdf is inserted. Point at both ways out: copy it, or build a new one.
        match_replace{"Use QPDF::copyForeignObject to add objects from another file\\.",
            "Use pikepdf.copy_foreign to add objects from another file, or "
            "construct a new object."},
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

[[noreturn]] void throw_foreign_object_error(std::string const &msg)
{
    PyErr_SetString(exc_foreign.load(std::memory_order_acquire), msg.c_str());
    throw py::python_error();
}

auto translate_qpdf_logic_error(const std::exception &e)
{
    return translate_qpdf_logic_error(std::string(e.what()));
}

bool is_data_decoding_error(const std::runtime_error &e)
{
    // JBIG2_DECODE_ERROR_PREFIX is pikepdf's own contribution to this list; see
    // pikepdf.h for why Pl_JBIG2 tags its errors with it.
    static const std::regex decoding_error_pattern(
        std::string("character out of range"
                    "|broken end-of-data sequence in base 85 data"
                    "|unexpected z during base 85 decode"
                    "|TIFFPredictor created with"
                    "|Pl_LZWDecoder:"
                    "|Pl_Flate:"
                    "|Pl_DCT:"
                    "|stream inflate:"
                    "|") +
            JBIG2_DECODE_ERROR_PREFIX,
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

bool is_reference_cycle_error(const std::logic_error &e)
{
    static const std::regex error_pattern(
        "cycle of direct objects", std::regex_constants::icase);

    return std::regex_search(e.what(), error_pattern);
}

NB_MODULE(_core, m)
{
    // Suppress nanobind's atexit leak report by default. At interpreter
    // shutdown, objects retained by module-scope Python state (e.g.
    // pytest.mark.parametrize arguments, lru_cache payloads, hypothesis
    // strategies evaluated at collection time) are reported as "leaks"
    // even though they are normal long-lived references. The noise
    // confuses users without indicating a bug. Developers and CI can opt
    // back in by setting PIKEPDF_NANOBIND_LEAK_WARNINGS=1 before import;
    // tests/test_import_leaks.py relies on this.
    if (const char *env = std::getenv("PIKEPDF_NANOBIND_LEAK_WARNINGS");
        env == nullptr || env[0] == '\0' || env[0] == '0') {
        py::set_leak_warnings(false);
    }

    decimal_type.store(
        py::object(py::module_::import_("decimal").attr("Decimal")).release().ptr(),
        std::memory_order_release);

    m.doc() = "pikepdf provides a Pythonic interface for qpdf";
    m.attr("__name__") = "pikepdf._core";
    m.def("qpdf_version", &QPDF::QPDFVersion);

    // -- Core objects --
    init_logger(m);
    init_qpdf(m);
    init_pagelist(m);
    init_object(m);
    init_job(m);

    // Matrix is a value type used as a default argument by some support objects
    // below (e.g. AcroForm.transform_annotations), so it must be registered
    // before them.
    init_matrix(m);

    // -- Support objects (alphabetize order) --
    init_acroform(m);
    init_annotation(m);
    init_embeddedfiles(m);
    init_namepath(m);
    init_nametree(m);
    init_numbertree(m);
    init_page(m);
    init_parsers(m);
    init_rectangle(m);
    init_tokenfilter(m);
    init_transcoding(m);

    // Facade types capture Object/ObjectType/Matrix/Rectangle, so run last.
    init_object_construct(m);

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
        .def("_translate_qpdf_logic_error",
            [](std::string s) { return translate_qpdf_logic_error(s).first; })
        .def("set_decimal_precision",
            [](uint prec) { return DECIMAL_PRECISION.exchange(prec); })
        .def("get_decimal_precision", []() { return DECIMAL_PRECISION.load(); })
        .def("get_access_default_mmap", []() { return MMAP_DEFAULT.load(); })
        .def("set_access_default_mmap",
            [](bool mmap) { return MMAP_DEFAULT.exchange(mmap); })
        .def("_get_explicit_conversion_mode",
            []() { return EXPLICIT_CONVERSION_MODE.load(); })
        .def("_get_effective_explicit_mode",
            []() { return get_explicit_conversion_mode(); })
        .def(
            "_get_effective_explicit_mode_for",
            [](QPDF &q) {
                return get_explicit_conversion_mode(
                    QpdfRegistry::instance().lookup_entry(&q));
            },
            py::arg("pdf"))
        .def("_set_explicit_conversion_mode",
            [](bool mode) { return EXPLICIT_CONVERSION_MODE.exchange(mode); })
        .def(
            "_push_thread_conversion_mode",
            [](bool explicit_) {
                auto token = thread_mode_stack.size();
                thread_mode_stack.push_back(
                    explicit_ ? ConversionMode::explicit_ : ConversionMode::implicit);
                return token;
            },
            py::arg("explicit"))
        .def(
            "_pop_thread_conversion_mode",
            [](size_t token) {
                // Truncate rather than pop, so that a context manager exited
                // out of order (or twice) cannot corrupt the stack: everything
                // pushed at or after this override is discarded, and popping
                // an override that is already gone does nothing.
                if (thread_mode_stack.size() > token)
                    thread_mode_stack.resize(token);
            },
            py::arg("token"))
        .def("set_flate_compression_level",
            [](int level) {
                if (-1 <= level && level <= 9) {
                    Pl_Flate::setCompressionLevel(level);
                    return level;
                }
                throw py::value_error(
                    "Flate compression level must be between 0 and 9 (or -1)");
            })
        .def(
            "_get_qpdf_global",
            [](std::string_view name) {
                uint32_t value = 0;
                check_qpdf_global_result(
                    qpdf_global_get_uint32(qpdf_global_param(name), &value), name);
                return value;
            },
            py::arg("name"))
        .def(
            "_set_qpdf_global",
            [](std::string_view name, uint32_t value) {
                auto param = qpdf_global_param(name);
                if (param == qpdf_p_limit_errors)
                    throw py::value_error("limit_errors is read-only");
                check_qpdf_global_result(qpdf_global_set_uint32(param, value), name);
            },
            py::arg("name"),
            py::arg("value"))
        .def("_unparse_content_stream", unparse_content_stream);

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

    // PikepdfError is the root of the hierarchy: every pikepdf-specific
    // exception derives from it, so `except PikepdfError` catches anything
    // pikepdf raises on its own behalf. It gets no atomic slot because the
    // translator never raises it directly - the module dict's strong
    // reference is all it needs. Created first so it can serve as a base
    // class for everything below.
    PyObject *exc_root =
        PyErr_NewException("pikepdf._core.PikepdfError", PyExc_Exception, nullptr);
    m.attr("PikepdfError") = py::handle(exc_root);

    publish(exc_main,
        m,
        "PdfError",
        PyErr_NewException("pikepdf._core.PdfError", exc_root, nullptr));
    // ReferenceCycleError is a subclass of PdfError, so existing
    // `except PdfError` handlers keep catching it. Published after exc_main so
    // PdfError exists to serve as the base class.
    publish(exc_referencecycle,
        m,
        "ReferenceCycleError",
        PyErr_NewException("pikepdf._core.ReferenceCycleError",
            exc_main.load(std::memory_order_acquire),
            nullptr));
    // PasswordError is a sibling of PdfError, not a subclass: a wrong password
    // is not a defect in the document. Downstream code (e.g. ocrmypdf) orders
    //     except PdfError: ...
    //     except PasswordError: ...
    // and relies on the first handler not swallowing the second.
    publish(exc_password,
        m,
        "PasswordError",
        PyErr_NewException("pikepdf._core.PasswordError", exc_root, nullptr));
    // A stream that will not decode is a defective document, so
    // DataDecodingError is a PdfError - the same call that raises it raises
    // PdfError for other kinds of damage.
    publish(exc_datadecoding,
        m,
        "DataDecodingError",
        PyErr_NewException("pikepdf._core.DataDecodingError",
            exc_main.load(std::memory_order_acquire),
            nullptr));
    publish(exc_usage,
        m,
        "JobUsageError",
        PyErr_NewException("pikepdf._core.JobUsageError", exc_root, nullptr));
    publish(exc_foreign,
        m,
        "ForeignObjectError",
        PyErr_NewException("pikepdf._core.ForeignObjectError", exc_root, nullptr));
    publish(exc_destroyedobject,
        m,
        "DeletedObjectError",
        PyErr_NewException("pikepdf._core.DeletedObjectError", exc_root, nullptr));

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
            if (is_reference_cycle_error(e)) {
                // qpdf points at its C++ API (QPDF::makeIndirectObject); rewrite
                // the guidance to the pikepdf equivalent so it's actionable from
                // Python.
                std::string msg = std::regex_replace(std::string(e.what()),
                    std::regex("QPDF::makeIndirectObject"),
                    "Pdf.make_indirect()");
                PyErr_SetString(
                    exc_referencecycle.load(std::memory_order_acquire), msg.c_str());
            } else {
                auto trans = translate_qpdf_logic_error(e);
                if (trans.second == error_type_foreign)
                    PyErr_SetString(exc_foreign.load(std::memory_order_acquire),
                        trans.first.c_str());
                else if (trans.second == error_type_pdferror)
                    PyErr_SetString(
                        exc_main.load(std::memory_order_acquire), trans.first.c_str());
                else
                    std::rethrow_exception(p);
            }
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

#ifdef Py_GIL_DISABLED
    m.attr("__threading__") = "freethreading";
#else
    m.attr("__threading__") = "gil";
#endif
}
