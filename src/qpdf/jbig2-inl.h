/*
 * This Source Code Form is subject to the terms of the Mozilla Public
 * License, v. 2.0. If a copy of the MPL was not distributed with this
 * file, You can obtain one at http://mozilla.org/MPL/2.0/.
 *
 * Copyright (C) 2022, James R. Barlow (https://github.com/jbarlow83/)
 */

#include "pikepdf.h"

#include <cstdio>
#include <cstring>

#include <qpdf/Constants.h>
#include <qpdf/Types.h>
#include <qpdf/DLL.h>
#include <qpdf/QPDFExc.hh>
#include <qpdf/PointerHolder.hh>
#include <qpdf/Buffer.hh>
#include <qpdf/QPDF.hh>
#include <qpdf/QPDFStreamFilter.hh>
#include <qpdf/QUtil.hh>
#include <qpdf/Pipeline.hh>

unsigned char *pipeline_caster(const char *s)
{
    // QPDF indicates Pipeline::write(unsigned char*) is effectively const
    // but not actually const for historical reasons, so we can discard the const.
    // unsigned char* to char* should be safe.
    return const_cast<unsigned char *>(reinterpret_cast<const unsigned char *>(s));
}

void check_jbig2dec_available()
{
    auto jbig2dec_available =
        py::module_::import("pikepdf.jbig2").attr("jbig2dec_available");
    if (!static_cast<py::bool_>(jbig2dec_available())) {
        auto cls_dependency_error =
            py::module_::import("pikepdf.models.image").attr("DependencyError");
        PyErr_SetString(cls_dependency_error.ptr(),
            "jbig2dec - not installed or installed version is too old "
            "(older than version 0.15)");
        throw py::error_already_set();
    }
}

class Pl_JBIG2 : public Pipeline {
public:
    Pl_JBIG2(
        const char *identifier, Pipeline *next, const std::string &jbig2globals = "")
        : Pipeline(identifier, next), jbig2globals(jbig2globals)
    {
    }
    virtual ~Pl_JBIG2() = default;

    virtual void write(unsigned char *data, size_t len) override
    {
        this->ss.write(reinterpret_cast<const char *>(data), len);
    }
    virtual void finish() override
    {
        std::string data = this->ss.str();
        if (data.empty()) {
            if (this->getNext(true))
                this->getNext()->finish();
            return;
        }

        py::bytes pydata = py::bytes(data);
        py::function extract_jbig2 =
            py::module_::import("pikepdf.jbig2").attr("extract_jbig2_bytes");

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

        std::string extracted_cpp = std::string(extracted);

        this->getNext()->write(
            pipeline_caster(extracted_cpp.data()), extracted_cpp.length());

        if (this->getNext(true)) {
            this->getNext()->finish();
        }
        this->ss.clear();
    }

private:
    py::bytes jbig2globals;
    std::stringstream ss;
};

class JBIG2StreamFilter : public QPDFStreamFilter {
public:
    JBIG2StreamFilter()          = default;
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
    virtual Pipeline *getDecodePipeline(Pipeline *next) override
    {
        check_jbig2dec_available();
        this->pipeline =
            std::make_shared<Pl_JBIG2>("JBIG2 decode", next, this->jbig2globals);
        return this->pipeline.get();
    }

    static std::shared_ptr<JBIG2StreamFilter> factory()
    {
        return std::make_shared<JBIG2StreamFilter>();
    }

    virtual bool isSpecializedCompression() override { return true; }
    virtual bool isLossyCompression() override { return false; }

private:
    std::string jbig2globals;
    std::shared_ptr<Pipeline> pipeline;
};