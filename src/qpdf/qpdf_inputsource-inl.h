// SPDX-FileCopyrightText: 2022 James R. Barlow
// SPDX-License-Identifier: MPL-2.0

#include <cstdio>
#include <cstring>

#include <qpdf/Constants.h>
#include <qpdf/Types.h>
#include <qpdf/DLL.h>
#include <qpdf/QPDFExc.hh>
#include <qpdf/QPDF.hh>
#include <qpdf/InputSource.hh>
#include <qpdf/QUtil.hh>

#include <pybind11/pybind11.h>
#include <pybind11/stl.h>

#include "pikepdf.h"
#include "utils.h"

// GIL usage:
// The GIL must be held while this class is constructed, by the constructor's caller,
// since Python objects may be created/destroyed in the process of calling the
// constructor.
// When opening the PDF, we release the GIL before calling processInputSource
// and similar, so we have to acquire it before calling back into Python, which we do
// (oof) on every read or seek. The benefit is it allows us to use native Python
// streams. Previous versions had a special code path for C based I/O.
// When Python is manipulating the PDF, generally the GIL is held, but we
// can release before doing a read, provided the other thread does not mess with
// our file.
class PythonStreamInputSource : public InputSource {
public:
    PythonStreamInputSource(const py::object &stream, std::string name, bool close)
        : name(name), close(close)
    {
        py::gil_scoped_acquire gil; // GIL must be held anyway, issue #295
        this->stream = stream;
        if (!this->stream.attr("readable")().cast<bool>())
            throw py::value_error("not readable");
        if (!this->stream.attr("seekable")().cast<bool>())
            throw py::value_error("not seekable");
    }
    virtual ~PythonStreamInputSource()
    {
        try {
            if (this->close) {
                py::gil_scoped_acquire gil;
                if (py::hasattr(this->stream, "close"))
                    this->stream.attr("close")();
            }
        } catch (const std::runtime_error &e) {
            if (!str_startswith(e.what(), "StopIteration"))
                std::cerr << "Exception in " << __func__ << ": " << e.what();
        }
    }
    PythonStreamInputSource(const PythonStreamInputSource &)            = delete;
    PythonStreamInputSource &operator=(const PythonStreamInputSource &) = delete;
    PythonStreamInputSource(PythonStreamInputSource &&)                 = default;
    PythonStreamInputSource &operator=(PythonStreamInputSource &&)      = delete;

    std::string const &getName() const override { return this->name; }

    qpdf_offset_t tell() override
    {
        py::gil_scoped_acquire gil;
        return py::cast<qpdf_offset_t>(this->stream.attr("tell")());
    }

    void seek(qpdf_offset_t offset, int whence) override
    {
        py::gil_scoped_acquire gil;
        this->stream.attr("seek")(offset, whence);
    }

    // LCOV_EXCL_START
    void rewind() override
    {
        // qpdf never seems to use this but still requires
        this->seek(0, SEEK_SET);
    }
    // LCOV_EXCL_STOP

    size_t read(char *buffer, size_t length) override
    {
        py::gil_scoped_acquire gil;

#if defined(PYPY_VERSION)
        // PyPy does not permit readinto(memoryview), so read to a buffer and
        // memcpy that buffer. Error message is:
        // "TypeError: a read-write bytes-like object is required, not memoryview"
        this->last_offset = this->tell();
        py::bytes result  = this->stream.attr("read")(length);
        py::buffer pybuf(result);
        py::buffer_info info = pybuf.request();
        size_t bytes_read    = info.size * info.itemsize;

        memcpy(buffer, info.ptr, std::min(length, bytes_read));
#else
        auto view_buffer_info = py::memoryview::from_memory(buffer, length);
        this->last_offset     = this->tell();
        py::object result     = this->stream.attr("readinto")(view_buffer_info);
        if (result.is_none())
            return 0;
        size_t bytes_read = py::cast<size_t>(result);
#endif
        if (bytes_read == 0) {
            if (length > 0) {
                // EOF
                this->seek(0, SEEK_END);
                this->last_offset = this->tell();
            }
        }
        return bytes_read;
    }

    void unreadCh(char ch) override { this->seek(-1, SEEK_CUR); }

    qpdf_offset_t findAndSkipNextEOL() override
    {
        py::gil_scoped_acquire gil; // Must acquire so another thread cannot seek

        qpdf_offset_t result   = 0;
        bool done              = false;
        bool eol_straddles_buf = false;
        std::string buf(4096, '\0');
        std::string line_endings = "\r\n";

        while (!done) {
            qpdf_offset_t cur_offset = this->tell();
            size_t len = this->read(const_cast<char *>(buf.data()), buf.size());
            if (len == 0) {
                done   = true;
                result = this->tell();
            } else {
                size_t found;
                if (!eol_straddles_buf) {
                    found = buf.find_first_of(line_endings);
                    if (found == std::string::npos)
                        continue;
                } else {
                    found = 0;
                }

                size_t found_end = buf.find_first_not_of(line_endings, found);
                if (found_end == std::string::npos) {
                    eol_straddles_buf = true;
                    continue;
                }
                result = cur_offset + found_end;
                this->seek(result, SEEK_SET);
                done = true;
            }
        }
        return result;
    }

private:
    py::object stream;
    std::string name;
    bool close;
};
