// SPDX-FileCopyrightText: 2022 James R. Barlow
// SPDX-License-Identifier: MPL-2.0

#include "pikepdf.h"

#include <cstdio>
#include <cstring>

#include <qpdf/Constants.h>
#include <qpdf/Types.h>
#include <qpdf/DLL.h>
#include <qpdf/QPDFExc.hh>
#include <qpdf/Buffer.hh>
#include <qpdf/QPDF.hh>
#include <qpdf/QPDFStreamFilter.hh>
#include <qpdf/QUtil.hh>
#include <qpdf/Pipeline.hh>

class Pl_JBIG2 : public Pipeline {
public:
    Pl_JBIG2(const char *identifier,
        Pipeline *next,
        py::object decoder,
        const std::string &jbig2globals = "")
        : Pipeline(identifier, next), decoder(decoder), jbig2globals(jbig2globals)
    {
    }
    virtual ~Pl_JBIG2() = default;

    virtual void write(const unsigned char *data, size_t len) override
    {
        this->ss.write(reinterpret_cast<const char *>(data), len);
    }

    std::string decode_jbig2(const std::string &data)
    {
        py::gil_scoped_acquire gil;
        py::bytes pydata = py::bytes(data);

        py::function extract_jbig2 = this->decoder.attr("decode_jbig2");

        py::bytes extracted;
        try {
            extracted = extract_jbig2(pydata, this->jbig2globals);
        } catch (py::error_already_set &e) {
            // In QPDF over here...
            // https://github.com/qpdf/qpdf/blob/dd3b2cedd3164692925df1ef7414eb452343372f/libqpdf/QPDF.cc#L2955-2984
            // all exceptions that happen during Pipeline::finish() will be trapped
            // and converted into a generic error about the object being not decodable.
            // As a consequence we get a Python exception through C++, so we discard it
            // as unraisable so that at least the user gets a chance to see it.
            e.discard_as_unraisable("jbig2dec error");
            throw std::runtime_error("qpdf will consume this exception");
        }

        return std::string(extracted);
    }

    virtual void finish() override
    {
        std::string data = this->ss.str();
        if (data.empty()) {
            if (this->getNext(true))
                this->getNext()->finish();
            return;
        }

        auto extracted = this->decode_jbig2(data);

        this->getNext()->write(extracted.data(), extracted.length());

        if (this->getNext(true)) {
            this->getNext()->finish();
        }
        this->ss.clear();
    }

private:
    py::object decoder;
    py::bytes jbig2globals;
    std::stringstream ss;
};

class JBIG2StreamFilter : public QPDFStreamFilter {
public:
    JBIG2StreamFilter()
    {
        py::gil_scoped_acquire gil;
        this->decoder = py::module_::import("pikepdf.jbig2").attr("get_decoder")();
    }
    virtual ~JBIG2StreamFilter() = default;

    virtual bool setDecodeParms(QPDFObjectHandle decode_parms) override
    {
        if (decode_parms.isNull())
            return true;

        auto jbig2globals_obj = decode_parms.getKey("/JBIG2Globals");
        if (jbig2globals_obj.isNull())
            return true;

        auto buf = jbig2globals_obj.getStreamData();
        this->jbig2globals =
            std::string(reinterpret_cast<char *>(buf->getBuffer()), buf->getSize());
        return true;
    }

    void assertDecoderAvailable()
    {
        py::gil_scoped_acquire gil;
        this->decoder.attr("check_available")();
    }

    virtual Pipeline *getDecodePipeline(Pipeline *next) override
    {
        this->assertDecoderAvailable();
        this->pipeline = std::make_shared<Pl_JBIG2>(
            "JBIG2 decode", next, this->decoder, this->jbig2globals);
        return this->pipeline.get();
    }

    static std::shared_ptr<JBIG2StreamFilter> factory()
    {
        return std::make_shared<JBIG2StreamFilter>();
    }

    virtual bool isSpecializedCompression() override { return true; }
    virtual bool isLossyCompression() override { return false; }

private:
    py::object decoder;
    std::string jbig2globals;
    std::shared_ptr<Pipeline> pipeline;
};