/*
 * This Source Code Form is subject to the terms of the Mozilla Public
 * License, v. 2.0. If a copy of the MPL was not distributed with this
 * file, You can obtain one at http://mozilla.org/MPL/2.0/.
 *
 * Copyright (C) 2017, James R. Barlow (https://github.com/jbarlow83/)
 */


#include <cstdio>
#include <cstring>

#include <qpdf/Constants.h>
#include <qpdf/Types.h>
#include <qpdf/DLL.h>
#include <qpdf/QPDFExc.hh>
#include <qpdf/PointerHolder.hh>
#include <qpdf/Buffer.hh>
#include <qpdf/QPDF.hh>
#include <qpdf/InputSource.hh>
#include <qpdf/QUtil.hh>
#include <qpdf/Buffer.hh>
#include <qpdf/BufferInputSource.hh>

#include <pybind11/pybind11.h>
#include <pybind11/stl.h>

#ifndef QINTC_HH
// QPDF >= 9.0 added this. We need it, and we still compile against 8.4.2,
// so slip it in if it's not already there. When we drop 8.4.2 compat, we can
// drop this inclusion and the file itself.
#include "QIntC.hh"
#endif

#include "pikepdf.h"
#include "utils.h"

// We could almost subclass BufferInputSource, and we even blind copy much of its
// code. The current reason to not do this is the performance improvement in
// findAndSkipNextEOL(), which is 8x faster on some files than QPDF. We cannot
// partially subclass or keep a BufferInputSource due to the need to manage
// BufferInputSource::Members::cur_offset and InputSource::last_offset, the
// former being a private variable. If QPDF accepts our changes to findAndSkipNextEOL
// this could subclass BufferInputSource.

// GIL usage:
// When opening the PDF, we release the GIL before calling processInputSource
// and similar, so we have to acquire it before calling back into Python.
// When Python is manipulating the PDF, generally the GIL is held, but we
// can release before doing a read, provided the other thread does not mess with
// our file.
class MmapInputSource : public InputSource
{
public:
    MmapInputSource(py::object stream, const std::string& description, bool close_stream) :
            InputSource(), stream(stream), description(description), close_stream(close_stream), offset(0)
    {
        py::gil_scoped_acquire acquire;
        py::int_ fileno = stream.attr("fileno")();
        int fd = fileno;
        auto mmap_module = py::module::import("mmap");
        auto mmap_fn = mmap_module.attr("mmap");

        // Use Python's mmap API since it is more portable than platform versions.
        auto access_read = mmap_module.attr("ACCESS_READ");
        this->mmap = mmap_fn(fd, 0, py::arg("access")=access_read);
        py::buffer view(this->mmap);

        // .request(false) -> request read-only mapping
        // Use a unique_ptr here so we can control the timing of our buffer_info's
        // deconstruction.
        this->buffer_info = std::make_unique<py::buffer_info>(view.request(false));
    }
    virtual ~MmapInputSource()
    {
        try {
            py::gil_scoped_acquire acquire;

            // buffer_info.reset() will trigger PyBuffer_Release(), which we must
            // do before we can close the memory mapping, since we exported a pointer
            // from it.
            this->buffer_info.reset();
            if (!this->mmap.is_none()) {
                this->mmap.attr("close")();
            }

            if (this->close_stream && py::hasattr(this->stream, "close")) {
                this->stream.attr("close")();
            }
        } catch (const std::runtime_error &e) {
            if (!str_startswith(e.what(), "StopIteration"))
                std::cerr << "Exception in " << __func__ << ": " << e.what();
        }
    }
    MmapInputSource(const MmapInputSource&) = delete;
    MmapInputSource& operator= (const MmapInputSource&) = delete;
    MmapInputSource(MmapInputSource&&) = delete;
    MmapInputSource& operator= (MmapInputSource&&) = delete;

    std::string const& getName() const override
    {
        return this->description;
    }

    qpdf_offset_t tell() override
    {
        return this->offset;
    }

    void seek(qpdf_offset_t offset, int whence) override
    {
        switch(whence)
        {
            case SEEK_SET:
                this->offset = offset;
                break;
            case SEEK_END:
                this->offset = this->buffer_info->size + offset;
                break;
            case SEEK_CUR:
                this->offset += offset;
                break;
            default:
	            throw std::logic_error(
	                "INTERNAL ERROR: invalid argument to MmapInputSource::seek"
                );
	            break;
        }
        if (this->offset < 0)
        {
            throw std::runtime_error(
                this->description + ": seek before beginning of buffer");
        }
    }

    void rewind() override
    {
        this->seek(0, SEEK_SET);
    }

    size_t read(char* buffer, size_t length) override
    {
        if (this->offset < 0)
        {
            throw std::logic_error("INTERNAL ERROR: MmapInputSource offset < 0");
        }
        qpdf_offset_t end_pos = this->buffer_info->size;
        if (this->offset >= end_pos)
        {
            this->last_offset = end_pos;
            return 0;
        }

        this->last_offset = this->offset;
        size_t len = std::min(QIntC::to_size(end_pos - this->offset), length);
        const char *src = static_cast<const char*>(this->buffer_info->ptr) + this->offset;
        {
            // We can't tell if we released the GIL (initialization) or are
            // holding it now, so check before release.
            if (PyGILState_Check() == 1) {
                py::gil_scoped_release gil;
                memcpy(buffer, src, len);
            } else {
                memcpy(buffer, src, len);
            }
        }
        this->offset += QIntC::to_offset(len);
        return len;
    }

    void unreadCh(char ch) override
    {
        if (this->offset > 0) {
            --this->offset;
        }
    }

    qpdf_offset_t findAndSkipNextEOL() override
    {
        if (this->offset < 0)
        {
            throw std::logic_error("INTERNAL ERROR: MmapInputSource offset < 0");
        }
        qpdf_offset_t end_pos = this->buffer_info->size;
        if (this->offset >= end_pos)
        {
            this->last_offset = end_pos;
            this->offset = end_pos;
            return end_pos;
        }
        qpdf_offset_t result = 0;
        unsigned char const* buffer = static_cast<unsigned char const*>(this->buffer_info->ptr);

        unsigned char const* end = buffer + end_pos;
        unsigned char const* p = buffer + this->offset;

        while (p < end) {
            if (*p == '\r' || *p == '\n')
                break;
            ++p;
        }
        if (p != end) {
            result = p - buffer;
            this->offset = result + 1;
            ++p;
            while ((this->offset < end_pos) &&
                ((*p == '\r') || (*p == '\n')))
            {
                ++p;
                ++this->offset;
            }
        }
        else
        {
            this->offset = end_pos;
            result = end_pos;
        }
        return result;
    }

private:
    py::object stream;
    std::string description;
    bool close_stream;
    py::object mmap;
    std::unique_ptr<py::buffer_info> buffer_info;
    qpdf_offset_t offset;
};
