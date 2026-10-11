// SPDX-FileCopyrightText: 2022 James R. Barlow
// SPDX-License-Identifier: MPL-2.0

#include "pikepdf.h"
#include "utils.h"

#include <cstdio>
#include <cstring>
#include <signal.h>

#include <qpdf/Buffer.hh>
#include <qpdf/BufferInputSource.hh>
#include <qpdf/Constants.h>
#include <qpdf/DLL.h>
#include <qpdf/InputSource.hh>
#include <qpdf/QPDF.hh>
#include <qpdf/QPDFExc.hh>
#include <qpdf/QUtil.hh>
#include <qpdf/Types.h>

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
        : InputSource(), close_stream_(close_stream)
    {
        py::gil_scoped_acquire acquire; // GIL must be held anyway, issue #295
        stream_ = stream;

        py::object fileno = stream_.attr("fileno")();
        int fd = py::cast<int>(fileno);
        auto mmap_module = py::module_::import_("mmap");
        auto mmap_fn = mmap_module.attr("mmap");

        // Use Python's mmap API since it is more portable than platform versions.
        auto access_read = mmap_module.attr("ACCESS_READ");
        mmap_ = mmap_fn(fd, 0, py::arg("access") = access_read);
        if (PyObject_GetBuffer(mmap_.ptr(), &pybuf_, PyBUF_SIMPLE) != 0) {
            throw py::python_error();
        }
        pybuf_valid_ = true;

        auto qpdf_buffer = std::make_unique<Buffer>(
            static_cast<unsigned char *>(pybuf_.buf), pybuf_.len);
        bis_ = std::make_unique<BufferInputSource>(description,
            qpdf_buffer.release(),
            false // own_memory=false
        );
    }
    virtual ~MmapInputSource()
    {
        py::gil_scoped_acquire acquire;
        // A Pdf may be deallocated while a Python exception is still propagating
        // (issue #732). Save and clear that in-flight error before calling back
        // into Python below: otherwise close() observes it (CPython raises
        // "returned a result with an exception set"). error_scope is declared at
        // function scope so it restores the original error *after* the handlers
        // below run, letting it resume propagating normally.
        py::error_scope save_in_flight_error;
        try {
            // Release the Py_buffer before we can close the memory mapping,
            // since we exported a pointer from it.
            bis_.reset();
            if (pybuf_valid_) {
                PyBuffer_Release(&pybuf_);
                pybuf_valid_ = false;
            }
            if (!mmap_.is_none()) {
                mmap_.attr("close")();
            }

            if (close_stream_ && py::hasattr(stream_, "close")) {
                stream_.attr("close")();
            }
            // LCOV_EXCL_START
        } catch (py::python_error &e) {
            e.restore();
            PyErr_WriteUnraisable(nullptr);
        } catch (const std::runtime_error &e) {
            if (!str_startswith(e.what(), "StopIteration"))
                std::cerr << "Exception in " << __func__ << ": " << e.what();
        } catch (...) {
            // A destructor must never let an exception escape.
        }
        // LCOV_EXCL_STOP
    }
    // LCOV_EXCL_START
    MmapInputSource(const MmapInputSource &) = delete;
    MmapInputSource &operator=(const MmapInputSource &) = delete;
    MmapInputSource(MmapInputSource &&) = delete;
    MmapInputSource &operator=(MmapInputSource &&) = delete;
    // LCOV_EXCL_STOP

    std::string const &getName() const override { return bis_->getName(); }

    qpdf_offset_t tell() override
    {
        auto result = bis_->tell();
        last_offset = bis_->getLastOffset();
        return result;
    }

    void seek(qpdf_offset_t offset, int whence) override
    {
        bis_->seek(offset, whence);
        last_offset = bis_->getLastOffset();
    }

    // LCOV_EXCL_START
    void rewind() override
    {
        // qpdf never seems to use this but still requires
        bis_->rewind();
        last_offset = bis_->getLastOffset();
    }
    // LCOV_EXCL_STOP

    size_t read(char *buffer, size_t length) override
    {
        auto result = bis_->read(buffer, length);
        last_offset = bis_->getLastOffset();
        return result;
    }

    void unreadCh(char ch) override
    {
        bis_->unreadCh(ch);
        last_offset = bis_->getLastOffset();
    }

    qpdf_offset_t findAndSkipNextEOL() override
    {
        auto result = bis_->findAndSkipNextEOL();
        last_offset = bis_->getLastOffset();
        return result;
    }

private:
    py::object stream_;
    bool close_stream_;
    py::object mmap_;
    Py_buffer pybuf_;
    bool pybuf_valid_ = false;
    std::unique_ptr<BufferInputSource> bis_;
};
