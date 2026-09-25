// SPDX-FileCopyrightText: 2022 James R. Barlow
// SPDX-License-Identifier: MPL-2.0

#include "pipeline.h"
#include "pikepdf.h"
#include "utils.h"

#include <qpdf/Constants.h>
#include <qpdf/DLL.h>
#include <qpdf/Pipeline.hh>
#include <qpdf/QPDF.hh>
#include <qpdf/QPDFExc.hh>
#include <qpdf/QUtil.hh>
#include <qpdf/Types.h>

#include <algorithm>
#include <cerrno>
#include <climits>

#ifdef _WIN32
#    include <io.h>
#else
#    include <unistd.h>
#endif

void Pl_PythonOutput::write(const unsigned char *buf, size_t len)
{
    py::gil_scoped_acquire gil;
    py::ssize_t so_far = 0;
    while (len > 0) {
        auto view_buffer = py::steal<py::object>(py::handle(PyMemoryView_FromMemory(
            const_cast<char *>(reinterpret_cast<const char *>(buf)), len, PyBUF_READ)));
        py::object result = this->stream.attr("write")(view_buffer);
        try {
            so_far = py::cast<py::ssize_t>(result);
        } catch (const py::cast_error &) {
            throw py::type_error("Unexpected return type of write()");
        }
        if (so_far <= 0) {
            QUtil::throw_system_error(this->identifier);
        } else {
            auto diff = len - so_far;
            if (diff > len)
                throw py::value_error("Wrote more bytes than requested");
            buf += so_far;
            len -= so_far;
        }
    }
}

void Pl_PythonOutput::finish()
{
    py::gil_scoped_acquire gil;
    this->stream.attr("flush")();
}

void Pl_FdOutput::write(const unsigned char *buf, size_t len)
{
    if (buffer.size() + len > buffer_size) {
        flush_buffer();
        if (len >= buffer_size) {
            write_fully(buf, len);
            return;
        }
    }
    buffer.insert(buffer.end(), buf, buf + len);
}

void Pl_FdOutput::finish()
{
    flush_buffer();
}

void Pl_FdOutput::flush_buffer()
{
    if (buffer.empty())
        return;
    write_fully(buffer.data(), buffer.size());
    buffer.clear();
}

void Pl_FdOutput::write_fully(const unsigned char *buf, size_t len)
{
    while (len > 0) {
#ifdef _WIN32
        auto chunk = static_cast<unsigned int>(std::min<size_t>(len, INT_MAX));
        auto written = ::_write(this->fd, buf, chunk);
#else
        auto chunk = std::min<size_t>(len, SSIZE_MAX);
        auto written = ::write(this->fd, buf, chunk);
#endif
        if (written < 0) {
            if (errno == EINTR)
                continue;
            QUtil::throw_system_error(this->identifier);
        }
        if (written == 0) {
            errno = EIO;
            QUtil::throw_system_error(this->identifier);
        }
        buf += written;
        len -= static_cast<size_t>(written);
    }
}
