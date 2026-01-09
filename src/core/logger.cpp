// SPDX-FileCopyrightText: 2022 James R. Barlow
// SPDX-License-Identifier: MPL-2.0

#include "pikepdf.h"
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

    // LCOV_EXCL_START - destructor never called due to no_op_deleter
    virtual ~Pl_PythonLogger() = default;
    Pl_PythonLogger(const Pl_PythonLogger &) = delete;
    Pl_PythonLogger &operator=(const Pl_PythonLogger &) = delete;
    Pl_PythonLogger(Pl_PythonLogger &&) = delete;
    Pl_PythonLogger &operator=(Pl_PythonLogger &&) = delete;
    // LCOV_EXCL_STOP

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

// LCOV_EXCL_START
static void no_op_deleter(void *ptr) noexcept
{
    // Intentionally left empty. The object is never deleted by the shared_ptr.
    // The memory will be reclaimed when the program terminates.
    // As a result, we deliberately leak memory associated with Pl_PythonLogger
    // objects to avoid shutdown sequencing issues between Python and C++
    // destructors.
    // https://github.com/pikepdf/pikepdf/issues/686
    (void)ptr;
}
// LCOV_EXCL_STOP

void init_logger(py::module_ &m)
{
    auto py_logger = py::module_::import("logging").attr("getLogger")("pikepdf._core");

    std::shared_ptr<Pipeline> pl_log_info = std::shared_ptr<Pl_PythonLogger>(
        new Pl_PythonLogger("qpdf to Python logging pipeline", py_logger, "info"),
        no_op_deleter);
    std::shared_ptr<Pipeline> pl_log_warn = std::shared_ptr<Pl_PythonLogger>(
        new Pl_PythonLogger("qpdf to Python logging pipeline", py_logger, "warning"),
        no_op_deleter);
    std::shared_ptr<Pipeline> pl_log_error = std::shared_ptr<Pl_PythonLogger>(
        new Pl_PythonLogger("qpdf to Python logging pipeline", py_logger, "error"),
        no_op_deleter);

    auto pikepdf_logger = get_pikepdf_logger();
    pikepdf_logger->setInfo(pl_log_info);
    pikepdf_logger->setWarn(pl_log_warn);
    pikepdf_logger->setError(pl_log_error);
    pikepdf_logger->info("pikepdf C++ to Python logger bridge initialized");
}