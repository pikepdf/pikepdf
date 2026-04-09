// SPDX-FileCopyrightText: 2022 James R. Barlow
// SPDX-License-Identifier: MPL-2.0

#include "pikepdf.h"
#include <qpdf/Pl_Discard.hh>
#include <qpdf/QPDFLogger.hh>

// Pipeline to relay qpdf log messages to Python logging module
// This is a sink - cannot pass to other pipeline objects
class Pl_PythonLogger : public Pipeline {
public:
    Pl_PythonLogger(const char *identifier, py::object logger, const char *level)
        : Pipeline(identifier, nullptr), level(level)
    {
        py::gil_scoped_acquire gil;
        this->logger = logger;
    }

    virtual ~Pl_PythonLogger() = default;
    Pl_PythonLogger(const Pl_PythonLogger &) = delete;
    Pl_PythonLogger &operator=(const Pl_PythonLogger &) = delete;
    Pl_PythonLogger(Pl_PythonLogger &&) = delete;
    Pl_PythonLogger &operator=(Pl_PythonLogger &&) = delete;

    void write(const unsigned char *buf, size_t len) override;
    // LCOV_EXCL_START - qpdf logger doesn't call finish() on pipelines
    void finish() override;
    // LCOV_EXCL_STOP

private:
    py::object logger;
    const char *level;
};

void Pl_PythonLogger::write(const unsigned char *buf, size_t len)
{
    py::gil_scoped_acquire gil;
    auto msg = py::str(reinterpret_cast<const char *>(buf), len);
    this->logger.attr(this->level)(msg);
}

// LCOV_EXCL_START - qpdf logger doesn't call finish() on pipelines
void Pl_PythonLogger::finish()
{
    py::gil_scoped_acquire gil;
    this->logger.attr("flush")();
}
// LCOV_EXCL_STOP

std::shared_ptr<QPDFLogger> get_pikepdf_logger()
{
    // All QPDFs can use the same logger
    return QPDFLogger::defaultLogger();
}

void init_logger(py::module_ &m)
{
    auto py_logger = py::module_::import_("logging").attr("getLogger")("pikepdf._core");

    auto pl_log_info = std::make_shared<Pl_PythonLogger>(
        "qpdf to Python logging pipeline", py_logger, "info");
    auto pl_log_warn = std::make_shared<Pl_PythonLogger>(
        "qpdf to Python logging pipeline", py_logger, "warning");
    auto pl_log_error = std::make_shared<Pl_PythonLogger>(
        "qpdf to Python logging pipeline", py_logger, "error");

    auto pikepdf_logger = get_pikepdf_logger();
    pikepdf_logger->setInfo(pl_log_info);
    pikepdf_logger->setWarn(pl_log_warn);
    pikepdf_logger->setError(pl_log_error);
    pikepdf_logger->info("pikepdf C++ to Python logger bridge initialized");

    // Before Python finalization, replace the Python-aware logger pipelines
    // with Pl_Discard so the Pl_PythonLogger instances (and their py::object
    // members) are destroyed while the interpreter is still alive.
    // This resolves https://github.com/pikepdf/pikepdf/issues/686 properly
    // instead of leaking via no_op_deleter.
    py::module_::import_("atexit").attr("register")(py::cpp_function([]() {
        auto logger = QPDFLogger::defaultLogger();
        auto discard = logger->discard();
        logger->setInfo(discard);
        logger->setWarn(discard);
        logger->setError(discard);
    }));
}