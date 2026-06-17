// SPDX-FileCopyrightText: 2022 James R. Barlow
// SPDX-License-Identifier: MPL-2.0

#include "parsers.h"
#include "pikepdf.h"
#include "qpdf_lock.h"

#include <cctype>
#include <iomanip>
#include <iostream>
#include <sstream>

#include <qpdf/Pipeline.hh>
#include <qpdf/Pl_Buffer.hh>
#include <qpdf/QPDFMatrix.hh>
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
            .def("_get_rotation",
                [](QPDFPageObjectHelper &poh) -> int {
                    // Resolve the effective /Rotate, honoring inheritance from the
                    // page tree, and normalize it to [0, 360).
                    QPDFObjectHandle rotate_obj = poh.getAttribute("/Rotate", false);
                    int rotate =
                        rotate_obj.isInteger() ? rotate_obj.getIntValueAsInt() : 0;
                    rotate %= 360;
                    if (rotate < 0)
                        rotate += 360;
                    return rotate;
                })
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
                "get_matrix_for_form_xobject_placement",
                [](QPDFPageObjectHelper &poh,
                    QPDFObjectHandle fo,
                    QPDFObjectHandle::Rectangle rect,
                    bool invert_transformations,
                    bool allow_shrink,
                    bool allow_expand) {
                    return poh.getMatrixForFormXObjectPlacement(
                        fo, rect, invert_transformations, allow_shrink, allow_expand);
                },
                py::arg("fo"), // LCOV_EXCL_LINE
                py::arg("rect"),
                py::kw_only(),
                py::arg("invert_transformations") = true,
                py::arg("allow_shrink") = true,
                py::arg("allow_expand") = false)
            .def(
                "get_matrix_for_transformations",
                [](QPDFPageObjectHelper &poh, bool invert) {
                    return QPDFMatrix(poh.getMatrixForTransformations(invert));
                },
                py::arg("invert") = false)
            .def("flatten_rotation",
                [](QPDFPageObjectHelper &poh) {
                    QpdfLockGuard lock(poh.getObjectHandle().getOwningQPDF());
                    poh.flattenRotation();
                })
            .def(
                "copy_annotations",
                [](QPDFPageObjectHelper &poh,
                    QPDFPageObjectHelper &from_page,
                    py::object matrix) {
                    // Default the matrix to identity. We use a None default rather
                    // than py::arg("matrix") = QPDFMatrix() because the latter would
                    // hold a live pikepdf.Matrix in the binding's defaults, which
                    // nanobind reports as a leak at interpreter shutdown.
                    QPDFMatrix cm =
                        matrix.is_none() ? QPDFMatrix() : py::cast<QPDFMatrix>(matrix);
                    QpdfLockGuard lock(poh.getObjectHandle().getOwningQPDF());
                    poh.copyAnnotations(from_page, cm);
                },
                py::arg("from_page"), // LCOV_EXCL_LINE
                py::arg("matrix") = py::none())
            .def_prop_ro("_images_recursive",
                [](QPDFPageObjectHelper &poh) {
                    QpdfLockGuard lock(poh.getObjectHandle().getOwningQPDF());
                    std::map<std::string, QPDFObjectHandle> result;
                    poh.forEachImage(true,
                        [&result](QPDFObjectHandle &obj,
                            QPDFObjectHandle &xobj_dict,
                            std::string const &key) { result[key] = obj; });
                    return result;
                })
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
                    // Keep token filter alive by storing ref on the QPDF object.
                    // Pdf has dynamic_attr() so the user could replace
                    // _token_filter_refs with a non-list; reset in that case
                    // so we don't reinterpret-cast a non-list and segfault.
                    py::object existing_refs = py::none();
                    if (py::hasattr(pyqpdf, "_token_filter_refs"))
                        existing_refs = pyqpdf.attr("_token_filter_refs");
                    if (!py::isinstance<py::list>(existing_refs)) {
                        py::setattr(pyqpdf, "_token_filter_refs", py::list());
                        existing_refs = pyqpdf.attr("_token_filter_refs");
                    }
                    py::list refs = py::borrow<py::list>(existing_refs);
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
            // The following accessors delegate to the underlying page dictionary
            // (``self.obj``). They were previously implemented in Python via
            // @augments; reimplementing them in C++ avoids the extra Python call
            // frames on these hot paths.
            .def("__getattr__",
                [](QPDFPageObjectHelper &poh, py::str name) {
                    return py::getattr(py::cast(poh.getObjectHandle()), name);
                })
            .def(
                "__setattr__",
                [](QPDFPageObjectHelper &poh, py::str name, py::object value) {
                    // Names defined on the Page class itself (properties such as
                    // mediabox, methods, etc.) are set on the instance so that
                    // property setters fire; everything else maps to a dictionary
                    // key on the underlying object.
                    py::object self = py::cast(poh);
                    if (py::hasattr(self.attr("__class__"), name)) {
                        py::module_::import_("builtins")
                            .attr("object")
                            .attr("__setattr__")(self, name, value);
                    } else {
                        py::setattr(py::cast(poh.getObjectHandle()), name, value);
                    }
                },
                py::arg("name"),
                py::arg("value").none())
            .def("__delattr__",
                [](QPDFPageObjectHelper &poh, py::str name) {
                    py::object self = py::cast(poh);
                    if (py::hasattr(self.attr("__class__"), name)) {
                        py::module_::import_("builtins")
                            .attr("object")
                            .attr("__delattr__")(self, name);
                    } else {
                        py::delattr(py::cast(poh.getObjectHandle()), name);
                    }
                })
            .def("__getitem__",
                [](QPDFPageObjectHelper &poh, py::handle key) -> py::object {
                    return py::cast(poh.getObjectHandle())[key];
                })
            .def("__setitem__",
                [](QPDFPageObjectHelper &poh, py::handle key, py::handle value) {
                    py::cast(poh.getObjectHandle())[key] = value;
                })
            .def("__delitem__",
                [](QPDFPageObjectHelper &poh, py::handle key) {
                    py::del(py::cast(poh.getObjectHandle())[key]);
                })
            .def("__contains__",
                [](QPDFPageObjectHelper &poh, py::handle key) {
                    py::object obj = py::cast(poh.getObjectHandle());
                    int rc = PySequence_Contains(obj.ptr(), key.ptr());
                    if (rc < 0)
                        throw py::python_error();
                    return rc == 1;
                })
            .def(
                "get",
                [](QPDFPageObjectHelper &poh,
                    py::handle key,
                    py::object default_) -> py::object {
                    py::object obj = py::cast(poh.getObjectHandle());
                    try {
                        return obj[key];
                    } catch (py::python_error &e) {
                        if (e.matches(PyExc_KeyError))
                            return default_;
                        throw; // LCOV_EXCL_LINE
                    }
                },
                py::arg("key"),
                py::arg("default") = py::none())
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

    // Make Page unhashable. pybind11 made bound types unhashable by default; we
    // explicitly clear __hash__ here to preserve that behavior under nanobind,
    // which otherwise inherits Python's identity-based default hash.
    page_class.attr("__hash__") = py::none();
}
