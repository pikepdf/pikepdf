/*
 * This Source Code Form is subject to the terms of the Mozilla Public
 * License, v. 2.0. If a copy of the MPL was not distributed with this
 * file, You can obtain one at http://mozilla.org/MPL/2.0/.
 *
 * Copyright (C) 2017, James R. Barlow (https://github.com/jbarlow83/)
 */

#include <sstream>
#include <iostream>
#include <iomanip>
#include <cctype>

#include "pikepdf.h"

#include <qpdf/QPDFPageObjectHelper.hh>
#include <qpdf/Pipeline.hh>
#include <qpdf/Pl_Buffer.hh>


class TokenFilter : public QPDFObjectHandle::TokenFilter {
public:
    using QPDFObjectHandle::TokenFilter::TokenFilter;
    virtual ~TokenFilter() = default;
    using Token = QPDFTokenizer::Token;

    void handleToken(Token const& token) override {
        py::object result = this->handle_token(token);
        if (result.is_none())
            return;
        try {
            if (py::hasattr(result, "__iter__")) {
                for (auto item : result) {
                    const auto returned_token = item.cast<Token>();
                    this->writeToken(returned_token);
                }
            } else {
                const auto returned_token = result.cast<Token>();
                this->writeToken(returned_token);
            }
        } catch (const py::cast_error &e) {
            throw py::type_error("returned object that is not a token");
        }
    }

    void handleEOF() override {
        this->handle_eof();
    }

    virtual py::object handle_token(Token const& token) = 0;
    virtual void handle_eof() {}
};


class TokenFilterTrampoline : public TokenFilter {
public:
    using TokenFilter::TokenFilter;
    using Token = QPDFTokenizer::Token;

    py::object handle_token(Token const& token) override {
        PYBIND11_OVERLOAD_PURE(
            py::object,
            TokenFilter,
            handle_token,
            token
        );
    }

    void handle_eof() override {
        PYBIND11_OVERLOAD(
            void,
            TokenFilter,
            handle_eof,
        );
    }
};


void init_page(py::module& m)
{
    py::class_<QPDFPageObjectHelper>(m, "Page")
        .def(py::init<QPDFObjectHandle &>())
        .def_property_readonly("obj",
            [](QPDFPageObjectHelper &poh) {
                return poh.getObjectHandle();
            }
        )
        .def_property_readonly("images", &QPDFPageObjectHelper::getPageImages)
        .def("externalize_inline_images", &QPDFPageObjectHelper::externalizeInlineImages)
        .def("rotate", &QPDFPageObjectHelper::rotatePage)
        .def("page_contents_coalesce", &QPDFPageObjectHelper::coalesceContentStreams)
        .def("_parse_page_contents", &QPDFPageObjectHelper::parsePageContents)
        .def("remove_unreferenced_resources", &QPDFPageObjectHelper::removeUnreferencedResources)
        .def("as_form_xobject", &QPDFPageObjectHelper::getFormXObjectForPage)
        .def("_filter_page_contents",
            [](QPDFPageObjectHelper &poh, TokenFilter &tf) {
                Pl_Buffer pl_buffer("filter_page");
                poh.filterPageContents(&tf, &pl_buffer);
                PointerHolder<Buffer> phbuf(pl_buffer.getBuffer());
                poh.getObjectHandle().getKey("/Contents").replaceStreamData(
                    phbuf, QPDFObjectHandle::newNull(), QPDFObjectHandle::newNull()
                );
            }
        )
        .def("add_content_token_filter",
            [](QPDFPageObjectHelper &poh, PointerHolder<QPDFObjectHandle::TokenFilter> tf) {
                poh.addContentTokenFilter(tf);
            },
            py::keep_alive<1, 2>()
        )
        ;

    py::class_<QPDFObjectHandle::TokenFilter, PointerHolder<QPDFObjectHandle::TokenFilter>>qpdftokenfilter (m, "_QPDFTokenFilter");

    py::class_<TokenFilter, TokenFilterTrampoline, PointerHolder<TokenFilter>>(m, "TokenFilter", qpdftokenfilter)
        .def(py::init<>())
        .def("handle_token", &TokenFilter::handle_token)
        .def("handle_eof", &TokenFilter::handle_eof)
        ;

    py::enum_<QPDFTokenizer::token_type_e>(m, "TokenType")
        .value("bad", QPDFTokenizer::token_type_e::tt_bad)
        .value("array_close", QPDFTokenizer::token_type_e::tt_array_close)
        .value("array_open", QPDFTokenizer::token_type_e::tt_array_open)
        .value("brace_close", QPDFTokenizer::token_type_e::tt_brace_close)
        .value("brace_open", QPDFTokenizer::token_type_e::tt_brace_open)
        .value("dict_close", QPDFTokenizer::token_type_e::tt_dict_close)
        .value("dict_open", QPDFTokenizer::token_type_e::tt_dict_open)
        .value("integer", QPDFTokenizer::token_type_e::tt_integer)
        .value("name", QPDFTokenizer::token_type_e::tt_name)
        .value("real", QPDFTokenizer::token_type_e::tt_real)
        .value("string", QPDFTokenizer::token_type_e::tt_string)
        .value("null", QPDFTokenizer::token_type_e::tt_null)
        .value("bool", QPDFTokenizer::token_type_e::tt_bool)
        .value("word", QPDFTokenizer::token_type_e::tt_word)
        .value("eof", QPDFTokenizer::token_type_e::tt_eof)
        .value("space", QPDFTokenizer::token_type_e::tt_space)
        .value("comment", QPDFTokenizer::token_type_e::tt_comment)
        .value("inline_image", QPDFTokenizer::token_type_e::tt_inline_image)
        ;

    py::class_<QPDFTokenizer::Token>(m, "Token")
        .def(py::init<QPDFTokenizer::token_type_e, py::bytes>())
        .def_property_readonly("type_", &QPDFTokenizer::Token::getType)
        .def_property_readonly("value", &QPDFTokenizer::Token::getValue)
        .def_property_readonly("raw_value",
            [](const QPDFTokenizer::Token& t) -> py::bytes {
                return t.getRawValue();
            }
        )
        .def_property_readonly("error_msg", &QPDFTokenizer::Token::getErrorMessage)
        .def("__eq__", &QPDFTokenizer::Token::operator==)
        ;
}
