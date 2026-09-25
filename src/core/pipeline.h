// SPDX-FileCopyrightText: 2022 James R. Barlow
// SPDX-License-Identifier: MPL-2.0

#pragma once

#include "pikepdf.h"

#include <cstdio>
#include <cstring>
#include <vector>

#include <qpdf/Buffer.hh>
#include <qpdf/Constants.h>
#include <qpdf/DLL.h>
#include <qpdf/Pipeline.hh>
#include <qpdf/QPDF.hh>
#include <qpdf/QPDFExc.hh>
#include <qpdf/QUtil.hh>
#include <qpdf/Types.h>

class Pl_PythonOutput : public Pipeline {
public:
    Pl_PythonOutput(const char *identifier, py::object stream)
        : Pipeline(identifier, nullptr), stream(stream)
    {
    }

    virtual ~Pl_PythonOutput() = default;
    Pl_PythonOutput(const Pl_PythonOutput &) = delete;
    Pl_PythonOutput &operator=(const Pl_PythonOutput &) = delete;
    Pl_PythonOutput(Pl_PythonOutput &&) = delete;
    Pl_PythonOutput &operator=(Pl_PythonOutput &&) = delete;

    void write(const unsigned char *buf, size_t len) override;
    void finish() override;

private:
    py::object stream;
};

// Writes to a file descriptor without calling into Python, so it neither needs
// nor touches the GIL. qpdf emits many small writes, so output is buffered here
// the way a Python BufferedWriter would have buffered it.
class Pl_FdOutput : public Pipeline {
public:
    Pl_FdOutput(const char *identifier, int fd) : Pipeline(identifier, nullptr), fd(fd)
    {
        buffer.reserve(buffer_size);
    }

    virtual ~Pl_FdOutput() = default;
    Pl_FdOutput(const Pl_FdOutput &) = delete;
    Pl_FdOutput &operator=(const Pl_FdOutput &) = delete;
    Pl_FdOutput(Pl_FdOutput &&) = delete;
    Pl_FdOutput &operator=(Pl_FdOutput &&) = delete;

    void write(const unsigned char *buf, size_t len) override;
    void finish() override;

private:
    static constexpr size_t buffer_size = 64 * 1024;

    void write_fully(const unsigned char *buf, size_t len);
    void flush_buffer();

    int fd;
    std::vector<unsigned char> buffer;
};
