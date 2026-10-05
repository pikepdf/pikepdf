// SPDX-FileCopyrightText: 2022 James R. Barlow
// SPDX-License-Identifier: MPL-2.0

#include "pikepdf.h"
#include "utils.h"

#include <algorithm>
#include <cerrno>
#include <climits>
#include <cstdio>
#include <cstring>

#ifdef _WIN32
#    include <io.h>
#else
#    include <sys/stat.h>
#    include <unistd.h>
#endif

#include <qpdf/Constants.h>
#include <qpdf/DLL.h>
#include <qpdf/InputSource.hh>
#include <qpdf/QPDF.hh>
#include <qpdf/QPDFExc.hh>
#include <qpdf/QUtil.hh>
#include <qpdf/Types.h>

// Close a stream that an input source owns, from the input source's destructor.
inline void close_owned_stream(py::object &stream)
{
    py::gil_scoped_acquire gil;
    // A Pdf may be deallocated while a Python exception is still propagating,
    // e.g. when it is dropped from a partially built list literal during
    // unwind (issue #732). Save and clear that in-flight error before calling
    // back into Python: otherwise close() observes it (CPython raises
    // "returned a result with an exception set") and the resulting exception
    // escaping this destructor calls std::terminate. error_scope is declared
    // at function scope so it restores the original error *after* the handlers
    // below run, letting it resume propagating normally.
    py::error_scope save_in_flight_error;
    try {
        if (py::hasattr(stream, "close"))
            stream.attr("close")();
    } catch (py::python_error &e) {
        e.restore();
        PyErr_WriteUnraisable(nullptr);
    } catch (const std::runtime_error &e) {
        if (!str_startswith(e.what(), "StopIteration"))
            std::cerr << "Exception in " << __func__ << ": " << e.what();
    } catch (...) {
        // A destructor must never let an exception escape.
    }
}

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
        if (!py::cast<bool>(this->stream.attr("readable")()))
            throw py::value_error("not readable");
        if (!py::cast<bool>(this->stream.attr("seekable")()))
            throw py::value_error("not seekable");
    }
    virtual ~PythonStreamInputSource()
    {
        if (!this->close)
            return;
        close_owned_stream(this->stream);
    }
    PythonStreamInputSource(const PythonStreamInputSource &) = delete;
    PythonStreamInputSource &operator=(const PythonStreamInputSource &) = delete;
    PythonStreamInputSource(PythonStreamInputSource &&) = default;
    PythonStreamInputSource &operator=(PythonStreamInputSource &&) = delete;

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

        auto view = py::steal<py::object>(
            py::handle(PyMemoryView_FromMemory(buffer, length, PyBUF_WRITE)));
        this->last_offset = this->tell();
        py::object result = this->stream.attr("readinto")(view);
        if (result.is_none())
            throw py::value_error(
                "Stream readinto() returned None; non-blocking streams are not "
                "supported");
        size_t bytes_read = py::cast<size_t>(result);
        // qpdf trusts bytes_read bytes of buffer as valid, and the stream has
        // likely consumed whatever it reported, so an over-report is an error
        // rather than something to clamp (see also Pl_PythonOutput::write).
        if (bytes_read > length)
            throw py::value_error("Read more bytes than requested");
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

        qpdf_offset_t result = 0;
        bool eol_straddles_buf = false;
        char rawbuf[4096];
        std::string line_endings = "\r\n";

        while (true) {
            qpdf_offset_t cur_offset = this->tell();
            size_t len = this->read(rawbuf, sizeof(rawbuf));
            if (len == 0) {
                result = this->tell();
                break;
            }
            std::string_view buf(rawbuf, len);
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
            break;
        }
        return result;
    }

private:
    py::object stream;
    std::string name;
    bool close;
};

// Reads a file descriptor without calling into Python, so it neither needs nor
// touches the GIL. Used only when pikepdf itself opened the file: the Python
// stream is kept so that it owns the descriptor and closes it, but is not
// otherwise used.
//
// The position is tracked here and reads are positioned, so the descriptor's
// own file position is never relied on. qpdf makes many small reads, often
// preceded by a seek, so reads go through a buffer, and seeking within the
// buffered range costs nothing.
class FdInputSource : public InputSource {
public:
    FdInputSource(const py::object &stream, int fd, std::string name)
        : stream(stream), fd(fd), name(name), buffer(new char[buffer_size])
    {
    }
    virtual ~FdInputSource() { close_owned_stream(this->stream); }
    FdInputSource(const FdInputSource &) = delete;
    FdInputSource &operator=(const FdInputSource &) = delete;
    FdInputSource(FdInputSource &&) = delete;
    FdInputSource &operator=(FdInputSource &&) = delete;

    std::string const &getName() const override { return this->name; }

    qpdf_offset_t tell() override { return this->pos; }

    void seek(qpdf_offset_t offset, int whence) override
    {
        qpdf_offset_t base = 0;
        switch (whence) {
        case SEEK_SET:
            break;
        case SEEK_CUR:
            base = this->pos;
            break;
        case SEEK_END:
            base = this->file_size();
            break;
        default:
            // LCOV_EXCL_START
            throw std::logic_error("FdInputSource: invalid whence");
            // LCOV_EXCL_STOP
        }
        if (base + offset < 0) {
            errno = EINVAL;
            QUtil::throw_system_error(this->name);
        }
        this->pos = base + offset;
    }

    // LCOV_EXCL_START
    void rewind() override
    {
        // qpdf never seems to use this but still requires
        this->seek(0, SEEK_SET);
    }
    // LCOV_EXCL_STOP

    size_t read(char *out, size_t length) override
    {
        this->last_offset = this->pos;
        size_t so_far = this->copy_from_buffer(out, length);
        if (so_far < length) {
            auto remaining = length - so_far;
            if (remaining >= buffer_size) {
                so_far += this->read_at(out + so_far, remaining, this->pos);
                this->pos = this->last_offset + static_cast<qpdf_offset_t>(so_far);
            } else {
                this->buf_start = this->pos;
                this->buf_len = 0; // In case the read throws
                this->buf_len =
                    this->read_at(this->buffer.get(), buffer_size, this->pos);
                so_far += this->copy_from_buffer(out + so_far, remaining);
            }
        }
        if (so_far == 0 && length > 0) {
            // EOF
            this->pos = this->file_size();
            this->last_offset = this->pos;
        }
        return so_far;
    }

    void unreadCh(char ch) override { this->seek(-1, SEEK_CUR); }

    qpdf_offset_t findAndSkipNextEOL() override
    {
        bool in_eol = false;
        while (true) {
            if (!this->buffered(this->pos)) {
                char ch;
                if (this->read(&ch, 1) == 0)
                    return this->pos;
                this->pos--;
            }
            const char *start = this->buffer.get() + (this->pos - this->buf_start);
            const char *end = this->buffer.get() + this->buf_len;
            auto is_eol = [](char ch) { return ch == '\r' || ch == '\n'; };
            const char *p = start;
            if (!in_eol) {
                p = std::find_if(p, end, is_eol);
                in_eol = (p != end);
            }
            if (in_eol) {
                p = std::find_if_not(p, end, is_eol);
                if (p != end) {
                    this->pos += p - start;
                    return this->pos;
                }
            }
            this->pos += end - start;
        }
    }

private:
    static constexpr size_t buffer_size = 16 * 1024;

    bool buffered(qpdf_offset_t offset) const
    {
        return offset >= this->buf_start &&
               offset < this->buf_start + static_cast<qpdf_offset_t>(this->buf_len);
    }

    // Copy what the buffer holds at the current position, and advance past it.
    size_t copy_from_buffer(char *out, size_t length)
    {
        if (!this->buffered(this->pos))
            return 0;
        auto buf_offset = static_cast<size_t>(this->pos - this->buf_start);
        auto n = std::min(length, this->buf_len - buf_offset);
        std::memcpy(out, this->buffer.get() + buf_offset, n);
        this->pos += static_cast<qpdf_offset_t>(n);
        return n;
    }

    // Read until length bytes are read or the end of file is reached.
    size_t read_at(char *out, size_t length, qpdf_offset_t offset)
    {
        size_t so_far = 0;
        while (so_far < length) {
#ifdef _WIN32
            auto chunk =
                static_cast<unsigned int>(std::min<size_t>(length - so_far, INT_MAX));
            if (::_lseeki64(this->fd, offset, SEEK_SET) < 0)
                QUtil::throw_system_error(this->name);
            auto count = ::_read(this->fd, out + so_far, chunk);
#else
            auto chunk = std::min<size_t>(length - so_far, SSIZE_MAX);
            auto count = ::pread(this->fd, out + so_far, chunk, offset);
#endif
            if (count < 0) {
                if (errno == EINTR)
                    continue;
                QUtil::throw_system_error(this->name);
            }
            if (count == 0)
                break;
            so_far += static_cast<size_t>(count);
            offset += count;
        }
        return so_far;
    }

    qpdf_offset_t file_size()
    {
#ifdef _WIN32
        auto size = ::_filelengthi64(this->fd);
        if (size < 0)
            QUtil::throw_system_error(this->name);
        return size;
#else
        struct stat st;
        if (::fstat(this->fd, &st) != 0)
            QUtil::throw_system_error(this->name);
        return st.st_size;
#endif
    }

    py::object stream;
    int fd;
    std::string name;
    std::unique_ptr<char[]> buffer;
    qpdf_offset_t buf_start = 0;
    size_t buf_len = 0;
    qpdf_offset_t pos = 0;
};
