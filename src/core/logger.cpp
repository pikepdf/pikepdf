// SPDX-FileCopyrightText: 2022 James R. Barlow
// SPDX-License-Identifier: MPL-2.0

#include "pikepdf.h"
#include <qpdf/QPDFLogger.hh>

static auto pikepdf_logger = QPDFLogger::create();

// Pipeline to relay QPDF log messages to Python logging module
// This is a sink - cannot pass to other pipeline objects
class Pl_PythonLogger : public Pipeline {
public:
    Pl_PythonLogger(const char *identifier, py::object logger, const char *level)
        : Pipeline(identifier, nullptr), level(level)
    {
        py::gil_scoped_acquire gil;
        this->logger = logger;
    }

    virtual ~Pl_PythonLogger()                          = default;
    Pl_PythonLogger(const Pl_PythonLogger &)            = delete;
    Pl_PythonLogger &operator=(const Pl_PythonLogger &) = delete;
    Pl_PythonLogger(Pl_PythonLogger &&)                 = delete;
    Pl_PythonLogger &operator=(Pl_PythonLogger &&)      = delete;

    void write(const unsigned char *buf, size_t len) override;
    void finish() override;

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

void Pl_PythonLogger::finish()
{
    py::gil_scoped_acquire gil;
    this->logger.attr("flush")();
}

std::shared_ptr<QPDFLogger> get_pikepdf_logger()
{
    // All QPDFs can use the same logger
    return pikepdf_logger;
}

void init_logger(py::module_ &m)
{
    auto py_logger = py::module_::import("logging").attr("getLogger")("pikepdf._core");

    std::shared_ptr<Pipeline> pl_log_info = std::make_shared<Pl_PythonLogger>(
        "QPDF to Python logging pipeline", py_logger, "info");
    std::shared_ptr<Pipeline> pl_log_warn = std::make_shared<Pl_PythonLogger>(
        "QPDF to Python logging pipeline", py_logger, "warning");
    std::shared_ptr<Pipeline> pl_log_error = std::make_shared<Pl_PythonLogger>(
        "QPDF to Python logging pipeline", py_logger, "error");

    pikepdf_logger->setInfo(pl_log_info);
    pikepdf_logger->setWarn(pl_log_warn);
    pikepdf_logger->setError(pl_log_error);
    pikepdf_logger->info("pikepdf C++ to Python logger bridge initialized");
}