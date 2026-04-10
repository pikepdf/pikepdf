// SPDX-FileCopyrightText: 2022 James R. Barlow
// SPDX-License-Identifier: MPL-2.0

#include <cctype>
#include <iomanip>
#include <iostream>
#include <sstream>

#include "parsers.h"
#include "pikepdf.h"
#include "qpdf_lock.h"

#include <qpdf/Pipeline.hh>
#include <qpdf/Pl_Buffer.hh>
#include <qpdf/QPDFPageLabelDocumentHelper.hh>
#include <qpdf/QPDFPageObjectHelper.hh>

size_t page_index(QPDF &owner, QPDFObjectHandle page)
{
    QpdfLockGuard lock(&owner);
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
        py::module_::import_("pikepdf._cpphelpers").attr("label_from_label_dict");
    py::str result = py::borrow<py::str>(impl(label_dict));
    return py::cast<std::string>(result);
}

void init_page(py::module_ &m)
{
    auto page_class =
        py::class_<QPDFPageObjectHelper, QPDFObjectHelper>(
            m, "Page", py::type_slots(pikepdf_gc_slots))
            .def(py::init<QPDFObjectHandle &>())
            .def("__init__",
                [](QPDFPageObjectHelper *self, QPDFPageObjectHelper &poh) {
                    new (self) QPDFPageObjectHelper(poh.getObjectHandle());
                })
            .def("__copy__",
                [](QPDFPageObjectHelper &poh) { return poh.shallowCopyPage(); })
            .def_prop_ro("_images", &QPDFPageObjectHelper::getImages)
            .def_prop_ro("_form_xobjects", &QPDFPageObjectHelper::getFormXObjects)
            .def("_get_mediabox", &QPDFPageObjectHelper::getMediaBox)
            .def("_get_artbox", &QPDFPageObjectHelper::getArtBox)
            .def("_get_bleedbox", &QPDFPageObjectHelper::getBleedBox)
            .def("_get_cropbox", &QPDFPageObjectHelper::getCropBox)
            .def("_get_trimbox", &QPDFPageObjectHelper::getTrimBox)
            .def(
                "externalize_inline_images",
                [](QPDFPageObjectHelper &poh,
                    size_t min_size = 0,
                    bool shallow = false) {
                    return poh.externalizeInlineImages(min_size, shallow);
                },
                py::arg("min_size") = 0,
                py::arg("shallow") = false)
            .def("rotate",
                &QPDFPageObjectHelper::rotatePage,
                py::arg("angle"),
                py::arg("relative"))
            .def("contents_coalesce",
                &QPDFPageObjectHelper::coalesceContentStreams // LCOV_EXCL_LINE
                )
            .def(
                "_contents_add",
                [](QPDFPageObjectHelper &poh,
                    QPDFObjectHandle &contents,
                    bool prepend) { return poh.addPageContents(contents, prepend); },
                py::arg("contents"), // LCOV_EXCL_LINE
                py::kw_only(),
                py::arg("prepend") = false)
            .def(
                "_contents_add",
                [](QPDFPageObjectHelper &poh, py::bytes contents, bool prepend) {
                    auto q = poh.getObjectHandle().getOwningQPDF();
                    QpdfLockGuard lock(q);
                    if (!q) {
                        // LCOV_EXCL_START
                        throw std::logic_error(
                            "QPDFPageObjectHelper not attached to QPDF");
                        // LCOV_EXCL_STOP
                    }
                    auto stream = QPDFObjectHandle::newStream(q, to_string(contents));
                    return poh.addPageContents(stream, prepend);
                },
                py::arg("contents"),
                py::kw_only(),
                py::arg("prepend") = false)
            .def("remove_unreferenced_resources",
                &QPDFPageObjectHelper::removeUnreferencedResources // LCOV_EXCL_LINE
                )
            .def("as_form_xobject",
                &QPDFPageObjectHelper::getFormXObjectForPage, // LCOV_EXCL_LINE
                py::arg("handle_transformations") = true)
            .def(
                "calc_form_xobject_placement",
                [](QPDFPageObjectHelper &poh,
                    QPDFObjectHandle formx,
                    QPDFObjectHandle name,
                    QPDFObjectHandle::Rectangle rect,
                    bool invert_transformations,
                    bool allow_shrink,
                    bool allow_expand) -> py::bytes {
                    auto content = poh.placeFormXObject(formx,
                        name.getName(),
                        rect,
                        invert_transformations,
                        allow_shrink,
                        allow_expand);
                    return py::bytes(content.data(), content.size());
                },
                py::arg("formx"), // LCOV_EXCL_LINE
                py::arg("name"),
                py::arg("rect"),
                py::kw_only(), // LCOV_EXCL_LINE
                py::arg("invert_transformations") = true,
                py::arg("allow_shrink") = true,
                py::arg("allow_expand") = false)
            .def(
                "get_filtered_contents",
                [](QPDFPageObjectHelper &poh,
                    QPDFObjectHandle::TokenFilter &tf) -> py::bytes {
                    QpdfLockGuard lock(poh.getObjectHandle().getOwningQPDF());
                    Pl_Buffer pl_buffer("filter_page");
                    poh.filterContents(&tf, &pl_buffer);

                    // Hold .getBuffer in unique_ptr to ensure it is deleted.
                    // qpdf makes a copy and expects us to delete it.
                    std::unique_ptr<Buffer> buf(pl_buffer.getBuffer());
                    auto data = reinterpret_cast<const char *>(buf->getBuffer());
                    auto size = buf->getSize();
                    return py::bytes(data, size);
                },
                py::arg("tf") // LCOV_EXCL_LINE
                )
            .def(
                "add_content_token_filter",
                [](QPDFPageObjectHelper &poh,
                    std::shared_ptr<QPDFObjectHandle::TokenFilter> tf) {
                    QpdfLockGuard lock(poh.getObjectHandle().getOwningQPDF());
                    // TokenFilters may be processed after the Python objects have gone
                    // out of scope, so we need to keep them alive by attaching them to
                    // the corresponding QPDF object.
                    // Standard py::keep_alive<> won't cut it. We could make this
                    // function require a Pdf, or move it to the Pdf.
                    auto pyqpdf = py::cast(poh.getObjectHandle().getOwningQPDF());
                    auto pytf = py::cast(tf);
                    // Keep token filter alive by storing ref on the QPDF object
                    if (!py::hasattr(pyqpdf, "_token_filter_refs")) {
                        py::setattr(pyqpdf, "_token_filter_refs", py::list());
                    }
                    py::list refs =
                        py::borrow<py::list>(pyqpdf.attr("_token_filter_refs"));
                    refs.append(pytf);

                    poh.addContentTokenFilter(tf);
                },
                py::arg("tf"))
            .def(
                "parse_contents",
                [](QPDFPageObjectHelper &poh,
                    QPDFObjectHandle::ParserCallbacks &stream_parser) {
                    poh.parseContents(&stream_parser);
                },
                py::arg("stream_parser"))
            .def_prop_ro("index",
                [](QPDFPageObjectHelper &poh) {
                    QpdfLockGuard lock(poh.getObjectHandle().getOwningQPDF());
                    auto this_page = poh.getObjectHandle();
                    auto p_owner = this_page.getOwningQPDF();
                    if (!p_owner)
                        throw py::value_error("Page is not attached to a Pdf");
                    auto &owner = *p_owner;
                    return page_index(owner, this_page);
                })
            .def_prop_ro("label", [](QPDFPageObjectHelper &poh) {
                QpdfLockGuard lock(poh.getObjectHandle().getOwningQPDF());
                auto this_page = poh.getObjectHandle();
                auto p_owner = this_page.getOwningQPDF();
                if (!p_owner)
                    throw py::value_error("Page is not attached to a Pdf");
                auto &owner = *p_owner;
                auto index = page_index(owner, this_page);

                QPDFPageLabelDocumentHelper pldh(owner);
                auto label_dict = pldh.getLabelForPage(index);
                if (label_dict.isNull())
                    return std::to_string(index + 1);

                return label_string_from_dict(label_dict);
            });

    // Make Page unhashable (matches pybind11 behavior).
    page_class.attr("__hash__") = py::none();
}
