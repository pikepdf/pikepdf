// SPDX-FileCopyrightText: 2022 James R. Barlow
// SPDX-License-Identifier: MPL-2.0

#include "pikepdf.h"

#include <cstdio>
#include <cstring>

#include <qpdf/Buffer.hh>
#include <qpdf/Constants.h>
#include <qpdf/DLL.h>
#include <qpdf/Pipeline.hh>
#include <qpdf/QPDF.hh>
#include <qpdf/QPDFExc.hh>
#include <qpdf/QPDFStreamFilter.hh>
#include <qpdf/QUtil.hh>
#include <qpdf/Types.h>

py::object get_decoder(py::gil_scoped_acquire &gil)
{
    return py::module_::import_("pikepdf.jbig2").attr("get_decoder")();
}

class Pl_JBIG2 : public Pipeline {
public:
    Pl_JBIG2(
        const char *identifier, Pipeline *next, const std::string &jbig2globals = "")
        : Pipeline(identifier, next), jbig2globals_(jbig2globals)
    {
    }
    virtual ~Pl_JBIG2() = default;

    virtual void write(const unsigned char *data, size_t len) override
    {
        buf_.append(reinterpret_cast<const char *>(data), len);
    }

    std::string decode_jbig2(const std::string &data)
    {
        py::gil_scoped_acquire gil;
        py::bytes pydata = py::bytes(data.data(), data.size());

        auto decoder = get_decoder(gil);
        py::object extract_jbig2 = decoder.attr("decode_jbig2");

        py::object extracted_obj;
        try {
            extracted_obj = extract_jbig2(
                pydata, py::bytes(jbig2globals_.data(), jbig2globals_.size()));
        } catch (py::python_error &e) {
            // We are called from Pipeline::finish(). If the stream data came
            // from a file, qpdf traps everything thrown here, downgrades it to
            // a warning and reports "unfilterable stream"; if the data was set
            // from memory, whatever we throw reaches the caller. Either way a
            // Python exception cannot cross qpdf's C++ frames intact, so a
            // decode failure is re-thrown tagged with the sentinel prefix that
            // is_data_decoding_error() recognizes, and the exception translator
            // turns it back into pikepdf.DataDecodingError. See pikepdf.h.
            //
            // Only DataDecodingError is smuggled out this way. Anything else --
            // DependencyError from a custom decoder, KeyboardInterrupt, a bug in
            // the decoder -- keeps its own type and traceback, because relabeling
            // it would blame corrupt JBIG2 data for an unrelated failure. Those
            // exceptions propagate as py::python_error, which nanobind restores
            // if qpdf does not trap it first.
            //
            // A caller that is prepared to re-raise the original exception
            // once qpdf has returned takes a copy first; see
            // PipelineErrorCapture in pikepdf.h.
            PipelineErrorCapture::record(e);
            if (!e.matches(py::handle(get_data_decoding_error_type())))
                throw;
            // Use str(exception), not e.what(): the latter is a formatted
            // traceback, which would end up embedded in the message the user
            // sees.
            throw std::runtime_error(std::string(JBIG2_DECODE_ERROR_PREFIX) + " " +
                                     py::str(e.value()).c_str());
        }

        return to_string(extracted_obj);
    }

    virtual void finish() override
    {
        if (buf_.empty()) {
            if (getNext(true))
                getNext()->finish();
            return;
        }

        // Hand off the accumulated input and drop our copy of it. qpdf builds a
        // fresh Pl_JBIG2 for every decode, so this is not needed for
        // correctness today, but it keeps a large compressed image from being
        // retained for as long as the owning stream filter lives.
        std::string data = std::move(buf_);
        buf_.clear();

        auto extracted = decode_jbig2(data);

        getNext()->write(extracted.data(), extracted.length());

        if (getNext(true)) {
            getNext()->finish();
        }
    }

private:
    // Do not hold any Python objects in this class to avoid GIL issues.
    std::string jbig2globals_;
    std::string buf_;
};

class JBIG2StreamFilter : public QPDFStreamFilter {
public:
    virtual bool setDecodeParms(QPDFObjectHandle decode_parms) override
    {
        if (decode_parms.isNull())
            return true;

        // Keep the globals and read them only in getDecodePipeline(). qpdf
        // calls this method whenever it checks whether a stream can be
        // decoded, at any decode level, so reading the globals here would
        // decompress them for streams that are not being JBIG2-decoded. It
        // would also recurse without end when the globals are JBIG2-encoded
        // and lead back to this stream: reading them would check them, which
        // would read their globals, and so on.
        jbig2globals_obj_ = decode_parms.getKey("/JBIG2Globals");
        return true;
    }

    void assertDecoderAvailable()
    {
        py::gil_scoped_acquire gil;
        auto decoder = get_decoder(gil);
        decoder.attr("check_available")();
    }

    virtual Pipeline *getDecodePipeline(Pipeline *next) override
    {
        assertDecoderAvailable();
        // getStreamData() decodes at the generalized level, which excludes
        // JBIG2, so globals that are themselves JBIG2-encoded are reported as
        // unfilterable here rather than decoded, which also ends any cycle.
        std::string jbig2globals;
        if (jbig2globals_obj_.isInitialized() && !jbig2globals_obj_.isNull()) {
            auto buf = jbig2globals_obj_.getStreamData();
            jbig2globals =
                std::string(reinterpret_cast<char *>(buf->getBuffer()), buf->getSize());
        }
        pipeline_ = std::make_shared<Pl_JBIG2>("JBIG2 decode", next, jbig2globals);
        return pipeline_.get();
    }

    static std::shared_ptr<JBIG2StreamFilter> factory()
    {
        return std::make_shared<JBIG2StreamFilter>();
    }

    virtual bool isSpecializedCompression() override { return true; }
    virtual bool isLossyCompression() override { return false; }

private:
    // Do not hold any Python objects in this class to avoid GIL issues.
    QPDFObjectHandle jbig2globals_obj_;
    std::shared_ptr<Pipeline> pipeline_;
};