// SPDX-FileCopyrightText: 2022 James R. Barlow
// SPDX-License-Identifier: MPL-2.0

#include <cstdio>
#include <cstring>

#include <qpdf/Buffer.hh>
#include <qpdf/BufferInputSource.hh>
#include <qpdf/Constants.h>
#include <qpdf/DLL.h>
#include <qpdf/InputSource.hh>
#include <qpdf/QPDF.hh>
#include <qpdf/QPDFExc.hh>
#include <qpdf/QUtil.hh>
#include <qpdf/Types.h>

#include "pikepdf.h"
#include "utils.h"
#include <signal.h>

// We could almost subclass BufferInputSource here, except that it expects Buffer
// as an initialization parameter, we don't know what the buffer location is until
// the mmap is set up. Instead, this class is an InputSource that has a
// BufferInputSource, which in turn wraps the memory mapped area.
//
// Since we delegate most work to the BufferInputSource, we need to preserve the state
// of InputSource::last_offset by copying it whenever may change. If the design of
// InputSource changes to introduce other state variables, we need to replicate the
// BufferInputSource's state.

// GIL usage:
// The GIL must be held while this class is constructed, by the constructor's caller,
// since Python objects may be created/destroyed in the process of calling the
// constructor.
// When opening the PDF, we release the GIL before calling processInputSource
// and similar. With memory mapping this means we process the input source entirely
// with re-acquiring the GIL, because Python 1) knows we mapped the memory and
// hold a reference to it, 2) no Python objects reference because we have returned
// the PDF object yet.
// When Python is manipulating the PDF, generally the GIL is held, but we
// can release before doing a read, provided the other thread does not mess with
// our file. We can access mapped memory without checking whether the GIL is held.
class MmapInputSource : public InputSource {
public:
    MmapInputSource(
        const py::object &stream, const std::string &description, bool close_stream)
        : InputSource(), close_stream(close_stream)
    {
        py::gil_scoped_acquire acquire; // GIL must be held anyway, issue #295
        this->stream = stream;

        py::object fileno = this->stream.attr("fileno")();
        int fd = py::cast<int>(fileno);
        auto mmap_module = py::module_::import_("mmap");
        auto mmap_fn = mmap_module.attr("mmap");

        // Use Python's mmap API since it is more portable than platform versions.
        auto access_read = mmap_module.attr("ACCESS_READ");
        this->mmap = mmap_fn(fd, 0, py::arg("access") = access_read);
        if (PyObject_GetBuffer(this->mmap.ptr(), &this->pybuf, PyBUF_SIMPLE) != 0) {
            throw py::python_error();
        }
        this->pybuf_valid = true;

        auto qpdf_buffer = std::make_unique<Buffer>(
            static_cast<unsigned char *>(this->pybuf.buf), this->pybuf.len);
        this->bis = std::make_unique<BufferInputSource>(description,
            qpdf_buffer.release(),
            false // own_memory=false
        );
    }
    virtual ~MmapInputSource()
    {
        py::gil_scoped_acquire acquire;
        try {
            // Release the Py_buffer before we can close the memory mapping,
            // since we exported a pointer from it.
            this->bis.reset();
            if (this->pybuf_valid) {
                PyBuffer_Release(&this->pybuf);
                this->pybuf_valid = false;
            }
            if (!this->mmap.is_none()) {
                this->mmap.attr("close")();
            }

            if (this->close_stream && py::hasattr(this->stream, "close")) {
                this->stream.attr("close")();
            }
            // LCOV_EXCL_START
        } catch (py::python_error &e) {
            e.restore();
            PyErr_WriteUnraisable(nullptr);
        } catch (const std::runtime_error &e) {
            if (!str_startswith(e.what(), "StopIteration"))
                std::cerr << "Exception in " << __func__ << ": " << e.what();
        }
        // LCOV_EXCL_STOP
    }
    // LCOV_EXCL_START
    MmapInputSource(const MmapInputSource &) = delete;
    MmapInputSource &operator=(const MmapInputSource &) = delete;
    MmapInputSource(MmapInputSource &&) = delete;
    MmapInputSource &operator=(MmapInputSource &&) = delete;
    // LCOV_EXCL_STOP

    std::string const &getName() const override { return this->bis->getName(); }

    qpdf_offset_t tell() override
    {
        auto result = this->bis->tell();
        this->last_offset = this->bis->getLastOffset();
        return result;
    }

    void seek(qpdf_offset_t offset, int whence) override
    {
        this->bis->seek(offset, whence);
        this->last_offset = this->bis->getLastOffset();
    }

    // LCOV_EXCL_START
    void rewind() override
    {
        // qpdf never seems to use this but still requires
        this->bis->rewind();
        this->last_offset = this->bis->getLastOffset();
    }
    // LCOV_EXCL_STOP

    size_t read(char *buffer, size_t length) override
    {
        auto result = this->bis->read(buffer, length);
        this->last_offset = this->bis->getLastOffset();
        return result;
    }

    void unreadCh(char ch) override
    {
        this->bis->unreadCh(ch);
        this->last_offset = this->bis->getLastOffset();
    }

    qpdf_offset_t findAndSkipNextEOL() override
    {
        auto result = this->bis->findAndSkipNextEOL();
        this->last_offset = this->bis->getLastOffset();
        return result;
    }

private:
    py::object stream;
    bool close_stream;
    py::object mmap;
    Py_buffer pybuf;
    bool pybuf_valid = false;
    std::unique_ptr<BufferInputSource> bis;
};
