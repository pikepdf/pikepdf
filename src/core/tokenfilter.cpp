// SPDX-FileCopyrightText: 2022 James R. Barlow
// SPDX-License-Identifier: MPL-2.0

#include <sstream>
#include <iostream>
#include <iomanip>
#include <cctype>

#include "pikepdf.h"

#include <qpdf/QPDFObjectHandle.hh>
#include <qpdf/QPDFPageObjectHelper.hh>

class TokenFilter : public QPDFObjectHandle::TokenFilter {
public:
    using QPDFObjectHandle::TokenFilter::TokenFilter;
    virtual ~TokenFilter() = default;
    using Token            = QPDFTokenizer::Token;

    void handleToken(Token const &token) override
    {
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
        } catch (const py::cast_error &) {
            throw py::type_error("returned object that is not a token");
        }
    }

    virtual py::object handle_token(Token const &token) = 0;
};

class TokenFilterTrampoline : public TokenFilter {
public:
    using TokenFilter::TokenFilter;
    using Token = QPDFTokenizer::Token;

    py::object handle_token(Token const &token) override
    {
        PYBIND11_OVERRIDE_PURE(py::object, TokenFilter, handle_token, token);
    }
};

void init_tokenfilter(py::module_ &m)
{
    py::enum_<QPDFTokenizer::token_type_e>(m, "TokenType")
        .value("bad", QPDFTokenizer::token_type_e::tt_bad)
        .value("array_close", QPDFTokenizer::token_type_e::tt_array_close)
        .value("array_open", QPDFTokenizer::token_type_e::tt_array_open)
        .value("brace_close", QPDFTokenizer::token_type_e::tt_brace_close)
        .value("brace_open", QPDFTokenizer::token_type_e::tt_brace_open)
        .value("dict_close", QPDFTokenizer::token_type_e::tt_dict_close)
        .value("dict_open", QPDFTokenizer::token_type_e::tt_dict_open)
        .value("integer", QPDFTokenizer::token_type_e::tt_integer)
        .value("name_", QPDFTokenizer::token_type_e::tt_name)
        .value("real", QPDFTokenizer::token_type_e::tt_real)
        .value("string", QPDFTokenizer::token_type_e::tt_string)
        .value("null", QPDFTokenizer::token_type_e::tt_null)
        .value("bool", QPDFTokenizer::token_type_e::tt_bool)
        .value("word", QPDFTokenizer::token_type_e::tt_word)
        .value("eof", QPDFTokenizer::token_type_e::tt_eof)
        .value("space", QPDFTokenizer::token_type_e::tt_space)
        .value("comment", QPDFTokenizer::token_type_e::tt_comment)
        .value("inline_image", QPDFTokenizer::token_type_e::tt_inline_image);

    py::class_<QPDFTokenizer::Token>(m, "Token")
        .def(py::init<QPDFTokenizer::token_type_e, py::bytes>())
        .def_property_readonly("type_", &QPDFTokenizer::Token::getType)
        .def_property_readonly("value", &QPDFTokenizer::Token::getValue)
        .def_property_readonly("raw_value",
            [](const QPDFTokenizer::Token &t) -> py::bytes { return t.getRawValue(); })
        .def_property_readonly("error_msg", &QPDFTokenizer::Token::getErrorMessage)
        .def("__eq__", &QPDFTokenizer::Token::operator==, py::is_operator());

    py::class_<QPDFObjectHandle::TokenFilter,
        std::shared_ptr<QPDFObjectHandle::TokenFilter>>
        qpdftokenfilter(m, "_QPDFTokenFilter");

    py::class_<TokenFilter, TokenFilterTrampoline, std::shared_ptr<TokenFilter>>(
        m, "TokenFilter", qpdftokenfilter)
        .def(py::init<>())
        .def("handle_token",
            &TokenFilter::handle_token,
            py::arg_v("token", QPDFTokenizer::Token(), "pikepdf.Token()"));
}
