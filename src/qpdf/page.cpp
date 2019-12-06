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
#include "object_parsers.h"

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

    virtual py::object handle_token(Token const& token) = 0;
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
};

void init_page(py::module& m)
{
    py::class_<QPDFPageObjectHelper>(m, "Page")
        .def(py::init<QPDFObjectHandle &>())
        .def_property_readonly("obj",
            [](QPDFPageObjectHelper &poh) {
                return poh.getObjectHandle();
            },
            R"~~~(
                Get the underlying :class:`pikepdf.Object`.
            )~~~"
        )
        .def_property_readonly("_images", &QPDFPageObjectHelper::getPageImages)
        .def("_get_mediabox", &QPDFPageObjectHelper::getMediaBox)
        .def("_get_cropbox", &QPDFPageObjectHelper::getCropBox)
        .def("_get_trimbox", &QPDFPageObjectHelper::getTrimBox)
        .def("externalize_inline_images", &QPDFPageObjectHelper::externalizeInlineImages,
            py::arg("min_size") = 0,
            R"~~~(
                Convert inlines image to normal (external) images.

                Args:
                    min_size (int): minimum size in bytes
            )~~~"
        )
        .def("rotate", &QPDFPageObjectHelper::rotatePage,
            py::arg("angle"), py::arg("relative"),
            R"~~~(
                Rotate a page.

                If ``relative`` is ``False``, set the rotation of the
                page to angle. Otherwise, add angle to the rotation of the
                page. ``angle`` must be a multiple of ``90``. Adding ``90`` to
                the rotation rotates clockwise by ``90`` degrees.
            )~~~"
        )
        .def("contents_coalesce", &QPDFPageObjectHelper::coalesceContentStreams,
            R"~~~(
                Coalesce a page's content streams.

                A page's content may be a
                stream or an array of streams. If this page's content is an
                array, concatenate the streams into a single stream. This can
                be useful when working with files that split content streams in
                arbitrary spots, such as in the middle of a token, as that can
                confuse some software.
            )~~~"
        )
        .def("remove_unreferenced_resources", &QPDFPageObjectHelper::removeUnreferencedResources,
            R"~~~(
                Removes from the resources dictionary any object not referenced in the content stream.

                A page's resources dictionary maps names to objects elsewhere
                in the file. This method walks through a page's contents and
                keeps tracks of which resources are referenced somewhere in the
                contents. Then it removes from the resources dictionary any
                object that is not referenced in the contents. This
                method is used by page splitting code to avoid copying unused
                objects in files that used shared resource dictionaries across
                multiple pages.
            )~~~"
        )
        .def("as_form_xobject", &QPDFPageObjectHelper::getFormXObjectForPage,
            py::arg("handle_transformations") = true,
            R"~~~(
                Return a form XObject that draws this page.

                This is useful for
                n-up operations, underlay, overlay, thumbnail generation, or
                any other case in which it is useful to replicate the contents
                of a page in some other context. The dictionaries are shallow
                copies of the original page dictionary, and the contents are
                coalesced from the page's contents. The resulting object handle
                is not referenced anywhere.

                Args:
                    handle_transformations (bool): If True, the resulting form
                        XObject's ``/Matrix`` will be set to replicate rotation
                        (``/Rotate``) and scaling (``/UserUnit``) in the page's
                        dictionary. In this way, the page's transformations will
                        be preserved when placing this object on another page.
            )~~~"
        )
        .def("get_filtered_contents",
            [](QPDFPageObjectHelper &poh, TokenFilter &tf) {
                Pl_Buffer pl_buffer("filter_page");
                poh.filterPageContents(&tf, &pl_buffer);

                PointerHolder<Buffer> buf(pl_buffer.getBuffer());
                auto data = reinterpret_cast<const char*>(buf->getBuffer());
                auto size = buf->getSize();
                return py::bytes(data, size);
            },
            py::arg("tf"),
            R"~~~(
                Apply a :class:`pikepdf.TokenFilter` to a content stream, without modifying it.

                This may be used when the results of a token filter do not need
                to be applied, such as when filtering is being used to retrieve
                information rather than edit the content stream.

                Note that it is possible to create a subclassed ``TokenFilter``
                that saves information of interest to its object attributes; it
                is not necessary to return data in the content stream.

                To modify the content stream, use :meth:`pikepdf.Page.add_content_token_filter`.

                Returns:
                    bytes: the modified content stream
            )~~~"
        )
        .def("add_content_token_filter",
            [](QPDFPageObjectHelper &poh, PointerHolder<QPDFObjectHandle::TokenFilter> tf) {
                poh.addContentTokenFilter(tf);
            },
            py::keep_alive<1, 2>(), py::arg("tf"),
            R"~~~(
                Attach a :class:`pikepdf.TokenFilter` to a page's content stream.

                This function applies token filters lazily, if/when the page's
                content stream is read for any reason, such as when the PDF is
                saved. If never access, the token filter is not applied.

                Multiple token filters may be added to a page/content stream.

                If the page's contents is an array of streams, it is coalesced.
            )~~~"
        )
        .def("parse_contents",
            [](QPDFPageObjectHelper &poh, PyParserCallbacks &parsercallbacks) {
                poh.parsePageContents(&parsercallbacks);
            },
            R"~~~(
                Parse a page's content streams using a :class:`pikepdf.StreamParser`.

                The content stream may be interpreted by the StreamParser but is
                not altered.

                If the page's contents is an array of streams, it is coalesced.
            )~~~"
        )
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
        .def_property_readonly("type_", &QPDFTokenizer::Token::getType,
            R"~~~(
                Returns the type of token.

                Return type:
                    pikepdf.TokenType
            )~~~"
        )
        .def_property_readonly("value", &QPDFTokenizer::Token::getValue,
            R"~~~(
                Interprets the token as a string.

                Return type:
                    str or bytes
            )~~~"
        )
        .def_property_readonly("raw_value",
            [](const QPDFTokenizer::Token& t) -> py::bytes {
                return t.getRawValue();
            },
            R"~~~(
                The binary representation of a token.

                Return type:
                    bytes
            )~~~"
        )
        .def_property_readonly("error_msg", &QPDFTokenizer::Token::getErrorMessage)
        .def("__eq__", &QPDFTokenizer::Token::operator==)
        ;

    py::class_<QPDFObjectHandle::TokenFilter,
        PointerHolder<QPDFObjectHandle::TokenFilter>>qpdftokenfilter (m, "_QPDFTokenFilter");

    py::class_<TokenFilter, TokenFilterTrampoline, PointerHolder<TokenFilter>>(m, "TokenFilter", qpdftokenfilter)
        .def(py::init<>())
        .def("handle_token", &TokenFilter::handle_token,
            R"~~~(
                Handle a :class:`pikepdf.Token`.

                This is an abstract method that must be defined in a subclass
                of ``TokenFilter``. The method will be called for each token.
                The implementation may return either ``None`` to discard the
                token, the original token to include it, a new token, or an
                iterable containing zero or more tokens. An implementation may
                also buffer tokens and release them in groups (for example, it
                could collect an entire PDF command with all of its operands,
                and then return all of it).

                The final token will always be a token of type ``TokenType.eof``,
                (unless an exception is raised).

                If this method raises an exception, the exception will be
                caught by C++, consumed, and repalced with a less informative
                exception. Use :meth:`pikepdf.Pdf.get_warnings` to view the
                original.

                Return type:
                    None or list or pikepdf.Token
            )~~~",
            py::arg_v("token", QPDFTokenizer::Token(), "pikepdf.Token()")
        )
        ;
}
