// SPDX-FileCopyrightText: 2022 James R. Barlow
// SPDX-License-Identifier: MPL-2.0

#include <sstream>
#include <iostream>
#include <iomanip>
#include <cctype>

#include "pikepdf.h"
#include "parsers.h"

#include <qpdf/QPDFPageObjectHelper.hh>
#include <qpdf/QPDFPageLabelDocumentHelper.hh>
#include <qpdf/Pipeline.hh>
#include <qpdf/Pl_Buffer.hh>

py::size_t page_index(QPDF &owner, QPDFObjectHandle page)
{
    if (&owner != page.getOwningQPDF())
        throw py::value_error("Page is not in this Pdf");

    int idx;
    try {
        idx = owner.findPage(page);
    } catch (const QPDFExc &e) {
        if (std::string(e.what()).find("page object not referenced") >= 0)
            throw py::value_error("Page is not consistently registered with Pdf");
        throw e;
    }
    if (idx < 0) {
        // LCOV_EXCL_START
        throw std::logic_error("Page index is negative");
        // LCOV_EXCL_STOP
    }

    return idx;
}

std::string label_string_from_dict(QPDFObjectHandle label_dict)
{
    auto impl =
        py::module_::import("pikepdf._cpphelpers").attr("label_from_label_dict");
    py::str result = impl(label_dict);
    return result;
}

void init_page(py::module_ &m)
{
    py::class_<QPDFPageObjectHelper,
        std::shared_ptr<QPDFPageObjectHelper>,
        QPDFObjectHelper>(m, "Page")
        .def(py::init<QPDFObjectHandle &>())
        .def(py::init([](QPDFPageObjectHelper &poh) {
            return QPDFPageObjectHelper(poh.getObjectHandle());
        }))
        .def(
            "__copy__", [](QPDFPageObjectHelper &poh) { return poh.shallowCopyPage(); })
        .def_property_readonly("_images", &QPDFPageObjectHelper::getImages)
        .def_property_readonly("_form_xobjects", &QPDFPageObjectHelper::getFormXObjects)
        .def("_get_mediabox", &QPDFPageObjectHelper::getMediaBox)
        .def("_get_cropbox", &QPDFPageObjectHelper::getCropBox)
        .def("_get_trimbox", &QPDFPageObjectHelper::getTrimBox)
        .def(
            "externalize_inline_images",
            [](QPDFPageObjectHelper &poh, size_t min_size = 0, bool shallow = false) {
                return poh.externalizeInlineImages(min_size, shallow);
            },
            py::arg("min_size") = 0,
            py::arg("shallow")  = false,
            R"~~~(
                Convert inline image to normal (external) images.

                Args:
                    min_size (int): minimum size in bytes
                    shallow (bool): If False, recurse into nested Form XObjects.
                        If True, do not recurse.
            )~~~")
        .def("rotate",
            &QPDFPageObjectHelper::rotatePage,
            py::arg("angle"),
            py::arg("relative"),
            R"~~~(
                Rotate a page.

                If ``relative`` is ``False``, set the rotation of the
                page to angle. Otherwise, add angle to the rotation of the
                page. ``angle`` must be a multiple of ``90``. Adding ``90`` to
                the rotation rotates clockwise by ``90`` degrees.
            )~~~")
        .def("contents_coalesce",
            &QPDFPageObjectHelper::coalesceContentStreams, // LCOV_EXCL_LINE
            R"~~~(
                Coalesce a page's content streams.

                A page's content may be a
                stream or an array of streams. If this page's content is an
                array, concatenate the streams into a single stream. This can
                be useful when working with files that split content streams in
                arbitrary spots, such as in the middle of a token, as that can
                confuse some software.
            )~~~")
        .def(
            "_contents_add",
            [](QPDFPageObjectHelper &poh, QPDFObjectHandle &contents, bool prepend) {
                return poh.addPageContents(contents, prepend);
            },
            py::arg("contents"), // LCOV_EXCL_LINE
            py::kw_only(),
            py::arg("prepend") = false)
        .def(
            "_contents_add",
            [](QPDFPageObjectHelper &poh, py::bytes contents, bool prepend) {
                auto q = poh.getObjectHandle().getOwningQPDF();
                if (!q) {
                    // LCOV_EXCL_START
                    throw std::logic_error("QPDFPageObjectHelper not attached to QPDF");
                    // LCOV_EXCL_STOP
                }
                auto stream = QPDFObjectHandle::newStream(q, contents);
                return poh.addPageContents(stream, prepend);
            },
            py::arg("contents"),
            py::kw_only(),
            py::arg("prepend") = false)
        .def("remove_unreferenced_resources",
            &QPDFPageObjectHelper::removeUnreferencedResources,
            R"~~~(
                Removes from the resources dictionary any object not referenced in the content stream.

                A page's resources dictionary maps names to objects elsewhere
                in the file. This method walks through a page's contents and
                keeps tracks of which resources are referenced somewhere in the
                contents. Then it removes from the resources dictionary any
                object that is not referenced in the contents. This
                method is used by page splitting code to avoid copying unused
                objects in files that use shared resource dictionaries across
                multiple pages.
            )~~~")
        .def("as_form_xobject",
            &QPDFPageObjectHelper::getFormXObjectForPage, // LCOV_EXCL_LINE
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
            )~~~")
        .def(
            "calc_form_xobject_placement",
            [](QPDFPageObjectHelper &poh,
                QPDFObjectHandle formx,
                QPDFObjectHandle name,
                QPDFObjectHandle::Rectangle rect,
                bool invert_transformations,
                bool allow_shrink,
                bool allow_expand) -> py::bytes {
                return py::bytes(poh.placeFormXObject(formx,
                    name.getName(),
                    rect,
                    invert_transformations,
                    allow_shrink,
                    allow_expand));
            },
            py::arg("formx"), // LCOV_EXCL_LINE
            py::arg("name"),
            py::arg("rect"),
            py::kw_only(), // LCOV_EXCL_LINE
            py::arg("invert_transformations") = true,
            py::arg("allow_shrink")           = true,
            py::arg("allow_expand")           = false,
            R"~~~(
                Generate content stream segment to place a Form XObject on this page.

                The content stream segment must then be added to the page's
                content stream.

                The default keyword parameters will preserve the aspect ratio.

                Args:
                    formx: The Form XObject to place.
                    name: The name of the Form XObject in this page's /Resources
                        dictionary.
                    rect: Rectangle describing the desired placement of the Form
                        XObject.
                    invert_transformations: Apply /Rotate and /UserUnit scaling
                        when determining FormX Object placement.
                    allow_shrink: Allow the Form XObject to take less than the
                        full dimensions of rect.
                    allow_expand: Expand the Form XObject to occupy all of rect.

                .. versionadded:: 2.14
            )~~~")
        .def(
            "get_filtered_contents",
            [](QPDFPageObjectHelper &poh,
                QPDFObjectHandle::TokenFilter &tf) -> py::bytes {
                Pl_Buffer pl_buffer("filter_page");
                poh.filterContents(&tf, &pl_buffer);

                // Hold .getBuffer in unique_ptr to ensure it is deleted.
                // QPDF makes a copy and expects us to delete it.
                std::unique_ptr<Buffer> buf(pl_buffer.getBuffer());
                auto data = reinterpret_cast<const char *>(buf->getBuffer());
                auto size = buf->getSize();
                return py::bytes(data, size);
            },
            py::arg("tf"), // LCOV_EXCL_LINE
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
                    The modified content stream.
            )~~~")
        .def(
            "add_content_token_filter",
            [](QPDFPageObjectHelper &poh,
                std::shared_ptr<QPDFObjectHandle::TokenFilter> tf) {
                // TokenFilters may be processed after the Python objects have gone
                // out of scope, so we need to keep them alive by attaching them to
                // the corresponding QPDF object.
                // Standard py::keep_alive<> won't cut it. We could make this
                // function require a Pdf, or move it to the Pdf.
                auto pyqpdf = py::cast(poh.getObjectHandle().getOwningQPDF());
                auto pytf   = py::cast(tf);
                py::detail::keep_alive_impl(pyqpdf, pytf);

                poh.addContentTokenFilter(tf);
            },
            py::arg("tf"),
            R"~~~(
                Attach a :class:`pikepdf.TokenFilter` to a page's content stream.

                This function applies token filters lazily, if/when the page's
                content stream is read for any reason, such as when the PDF is
                saved. If never access, the token filter is not applied.

                Multiple token filters may be added to a page/content stream.

                Token filters may not be removed after being attached to a Pdf.
                Close and reopen the Pdf to remove token filters.

                If the page's contents is an array of streams, it is coalesced.
            )~~~")
        .def(
            "parse_contents",
            [](QPDFPageObjectHelper &poh, PyParserCallbacks &parsercallbacks) {
                poh.parseContents(&parsercallbacks);
            },
            R"~~~(
                Parse a page's content streams using a :class:`pikepdf.StreamParser`.

                The content stream may be interpreted by the StreamParser but is
                not altered.

                If the page's contents is an array of streams, it is coalesced.
            )~~~")
        .def_property_readonly(
            "index",
            [](QPDFPageObjectHelper &poh) {
                auto this_page = poh.getObjectHandle();
                auto p_owner   = this_page.getOwningQPDF();
                if (!p_owner)
                    throw py::value_error("Page is not attached to a Pdf");
                auto &owner = *p_owner;
                return page_index(owner, this_page);
            },
            R"~~~(
                Returns the zero-based index of this page in the pages list.

                That is, returns ``n`` such that ``pdf.pages[n] == this_page``.
                A ``ValueError`` exception is thrown if the page is not attached
                to this ``Pdf``.

                .. versionadded:: 2.2
            )~~~")
        .def_property_readonly(
            "label",
            [](QPDFPageObjectHelper &poh) {
                auto this_page = poh.getObjectHandle();
                auto p_owner   = this_page.getOwningQPDF();
                if (!p_owner)
                    throw py::value_error("Page is not attached to a Pdf");
                auto &owner = *p_owner;
                auto index  = page_index(owner, this_page);

                QPDFPageLabelDocumentHelper pldh(owner);
                auto label_dict = pldh.getLabelForPage(index);
                if (label_dict.isNull())
                    return std::to_string(index + 1);

                return label_string_from_dict(label_dict);
            },
            R"~~~(
                Returns the page label for this page, accounting for section numbers.

                For example, if the PDF defines a preface with lower case Roman
                numerals (i, ii, iii...), followed by standard numbers, followed
                by an appendix (A-1, A-2, ...), this function returns the appropriate
                label as a string.

                It is possible for a PDF to define page labels such that multiple
                pages have the same labels. Labels are not guaranteed to
                be unique.

                .. versionadded:: 2.2

                .. versionchanged:: 2.9
                    Returns the ordinary page number if no special rules for page
                    numbers are defined.
            )~~~");
}
