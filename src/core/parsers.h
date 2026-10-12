// SPDX-FileCopyrightText: 2022 James R. Barlow
// SPDX-License-Identifier: MPL-2.0

#pragma once

#include "locked_bindings.h"
#include "pikepdf.h"

#include <nanobind/trampoline.h>

#include <string>

#include <qpdf/QPDFTokenizer.hh>

// Used to implement pikepdf.StreamParser, which can be subclassed to implement
// custom parsing.
class PyParserCallbacks : public QPDFObjectHandle::ParserCallbacks {
public:
    NB_TRAMPOLINE(QPDFObjectHandle::ParserCallbacks, 2);
    virtual ~PyParserCallbacks() = default;

    void handleObject(QPDFObjectHandle obj, size_t offset, size_t length) override;
    void handleEOF() override;
};

class ContentStreamInstruction {
public:
    ContentStreamInstruction(ObjectList operands, QPDFObjectHandle operator_);
    virtual ~ContentStreamInstruction() = default;

    ObjectList operands;
    QPDFObjectHandle operator_;

    // The Pdf whose lock guards the operands and the operator, or nullptr.
    // The objects of a parsed instruction are direct objects that qpdf
    // associates with the Pdf of the content stream. One built in Python may
    // hold objects of any Pdf, or of several; the first found is reported.
    QPDF *owner() const;
};

template <>
struct LockOwner<ContentStreamInstruction> {
    static constexpr bool declared = true;
    static constexpr bool locks = true;
    static QPDF *of(ContentStreamInstruction const &csi) { return csi.owner(); }
};

class ContentStreamInlineImage {
public:
    ContentStreamInlineImage(ObjectList image_metadata,
        QPDFObjectHandle image_data,
        QPDFObjectHandle resources = QPDFObjectHandle())
        : image_metadata(image_metadata), image_data(image_data), resources(resources)
    {
    }
    virtual ~ContentStreamInlineImage() = default;

    ObjectList image_metadata;
    QPDFObjectHandle image_data;
    // The /Resources dictionary in scope, used to resolve named colour spaces
    // referenced by the inline image. Null when no resources are available.
    QPDFObjectHandle resources;

    py::list get_operands() const;
    QPDFObjectHandle get_operator() const;

    py::object get_inline_image() const;

    // The Pdf whose lock guards the image and its resources, or nullptr.
    // The resources are an object of the Pdf itself, and may be indirect.
    QPDF *owner() const;
};

template <>
struct LockOwner<ContentStreamInlineImage> {
    static constexpr bool declared = true;
    static constexpr bool locks = true;
    static QPDF *of(ContentStreamInlineImage const &csii) { return csii.owner(); }
};

// A token filter holds no Pdf state: qpdf calls it with the tokens of
// whichever stream is being filtered. This covers the base class that qpdf
// defines and the classes derived from it in tokenfilter.cpp.
template <typename T>
struct LockOwner<T,
    std::enable_if_t<std::is_base_of_v<QPDFObjectHandle::TokenFilter, T>>> : NoLock {};

// Groups the objects of a content stream into instructions: operands followed
// by their operator, or an inline image (BI ... ID data EI). Subclasses decide
// what to do with each complete instruction.
class InstructionGrouper : public QPDFObjectHandle::ParserCallbacks {
public:
    explicit InstructionGrouper(QPDFObjectHandle resources = QPDFObjectHandle())
        : resources_(resources)
    {
    }
    void handleObject(QPDFObjectHandle obj) override;
    void handleEOF() override;

    std::string getWarning() const { return warning_; }

protected:
    // Whether to keep instructions with this operator; the operands of a
    // rejected operator are discarded along with it
    virtual bool accepts(std::string const &op) const { return true; }
    virtual void handle_instruction(ObjectList &operands,
        QPDFObjectHandle const &operator_,
        std::string const &op) = 0;
    virtual void handle_inline_image(ContentStreamInlineImage csii) = 0;

private:
    ObjectList tokens_;
    bool parsing_inline_image_ = false;
    ObjectList inline_metadata_;
    std::string warning_;
    // The /Resources in scope for this content stream, forwarded to inline
    // images so they can resolve named colour spaces. Null when unavailable.
    QPDFObjectHandle resources_;
};

// Used for parse_content_stream. Collects every instruction, optionally only
// those whose operators are in a whitelist.
class OperandGrouper : public InstructionGrouper {
public:
    OperandGrouper(
        const std::string &operators, QPDFObjectHandle resources = QPDFObjectHandle());

    py::list getInstructions() const;

protected:
    bool accepts(std::string const &op) const override;
    void handle_instruction(ObjectList &operands,
        QPDFObjectHandle const &operator_,
        std::string const &op) override;
    void handle_inline_image(ContentStreamInlineImage csii) override;

private:
    std::set<std::string> whitelist_;
    py::list instructions_;
};

// Append the PDF serialization of one instruction to out
void append_unparsed(std::string &out, ContentStreamInstruction &csi);
void append_unparsed(std::string &out, ContentStreamInlineImage &csii);

// unparse the list of instructions generated by an OperandGrouper
py::bytes unparse_content_stream(py::iterable contentstream);
