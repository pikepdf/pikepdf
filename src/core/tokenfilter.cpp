// SPDX-FileCopyrightText: 2022 James R. Barlow
// SPDX-License-Identifier: MPL-2.0

#include "locked_bindings.h"
#include "parsers.h"
#include "pikepdf.h"

#include <nanobind/trampoline.h>

#include <cctype>
#include <iomanip>

#include <qpdf/QPDFObjectHandle.hh>
#include <qpdf/QPDFPageObjectHelper.hh>

class TokenFilter : public QPDFObjectHandle::TokenFilter {
public:
    using QPDFObjectHandle::TokenFilter::TokenFilter;
    virtual ~TokenFilter() = default;
    using Token = QPDFTokenizer::Token;

    void handleToken(Token const &token) override
    {
        py::object result = handle_token(token);
        if (result.is_none())
            return;
        try {
            if (py::hasattr(result, "__iter__")) {
                for (auto item : result) {
                    const auto returned_token = py::cast<Token>(item);
                    writeToken(returned_token);
                }
            } else {
                const auto returned_token = py::cast<Token>(result);
                writeToken(returned_token);
            }
        } catch (const py::cast_error &) {
            throw py::type_error("returned object that is not a token");
        }
    }

    virtual py::object handle_token(Token const &token) = 0;
};

class TokenFilterTrampoline : public TokenFilter {
public:
    NB_TRAMPOLINE(TokenFilter, 1);
    using Token = QPDFTokenizer::Token;

    py::object handle_token(Token const &token) override
    {
        NB_OVERRIDE_PURE(handle_token, token);
    }
};

// A token is a value: its type and the bytes it was read from.
template <>
struct LockOwner<QPDFTokenizer::Token> : NoLock {};

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

    locked_class_<QPDFTokenizer::Token>(m, "Token", py::type_slots(pikepdf_gc_slots))
        .def_init([](QPDFTokenizer::token_type_e type, py::bytes value) {
            return QPDFTokenizer::Token(type, to_string(value));
        })
        .def_prop_ro("type_", &QPDFTokenizer::Token::getType)
        .def_prop_ro("value", &QPDFTokenizer::Token::getValue)
        .def("__repr__",
            [](const QPDFTokenizer::Token &t) {
                auto raw = t.getRawValue();
                return py::str("pikepdf.Token({}, {})")
                    .format(t.getType(), py::bytes(raw.data(), raw.size()));
            })
        .def_prop_ro("raw_value",
            [](const QPDFTokenizer::Token &t) -> py::bytes {
                auto v = t.getRawValue();
                return py::bytes(v.data(), v.size());
            })
        .def_prop_ro("error_msg", &QPDFTokenizer::Token::getErrorMessage)
        .def("__eq__", &QPDFTokenizer::Token::operator==, py::is_operator());

    // LockOwner for the token filter classes is declared in parsers.h, where
    // the bindings of Page that take a token filter can see it too.
    locked_class_<QPDFObjectHandle::TokenFilter>(
        m, "_QPDFTokenFilter", py::type_slots(pikepdf_gc_slots));

    // A filter is called by qpdf while it filters a content stream, which
    // pikepdf starts with the lock of that stream's Pdf held: see
    // Page.get_filtered_contents, and anything that reads a stream to which
    // Page.add_content_token_filter attached a filter. handle_token() is
    // therefore Python code that runs under a Pdf's lock. The lock is
    // re-entrant, so the override may use that Pdf.
    py::object qpdftokenfilter = m.attr("_QPDFTokenFilter");
    locked_class_<TokenFilter, TokenFilterTrampoline>(
        m, "TokenFilter", qpdftokenfilter, py::type_slots(pikepdf_gc_slots))
        .def_trampoline_constructor<>()
        .def("handle_token", &TokenFilter::handle_token, py::arg("token"));
}
