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

using TokenFilter = QPDFObjectHandle::TokenFilter;


class TokenFilterTrampoline : public TokenFilter {
public:
    using TokenFilter::TokenFilter;
    using Token = QPDFTokenizer::Token;

    void handleToken(Token const& token) override {
        PYBIND11_OVERLOAD_PURE_NAME(
            void,
            QPDFObjectHandle::TokenFilter,
            "_handle_token",
            handleToken,
            token
        );
    }

    void handleEOF() override {
        PYBIND11_OVERLOAD_NAME(
            void,
            QPDFObjectHandle::TokenFilter,
            "_handle_eof",
            handleEOF,
        );
    }
};

class TokenFilterPublicist : public TokenFilter {
public:
    using TokenFilter::writeToken;
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
            [](QPDFPageObjectHelper &poh, PointerHolder<TokenFilter> tf) {
                poh.addContentTokenFilter(tf);
            },
            py::keep_alive<1, 2>()
        )
        ;

    py::class_<TokenFilter, TokenFilterTrampoline, PointerHolder<TokenFilter>>(m, "_TokenFilter")
        .def(py::init<>())
        .def("_handle_token", &TokenFilter::handleToken)
        .def("_handle_eof", &TokenFilter::handleEOF)
        .def("_write_token", &TokenFilterPublicist::writeToken)
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
