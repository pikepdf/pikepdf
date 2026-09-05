// SPDX-FileCopyrightText: 2022 James R. Barlow
// SPDX-License-Identifier: MPL-2.0

#include "parsers.h"
#include "pikepdf.h"
#include "qpdf_lock.h"

#include <cctype>
#include <iomanip>

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

// Store a page bounding box such as /MediaBox. Anything that encodes to a PDF
// array of exactly four numbers is accepted, which covers pikepdf.Rectangle,
// pikepdf.Array and a plain list of numbers. qpdf only discovers a malformed box
// when it reads one back -- long after the assignment that caused it -- so
// validate at assignment time instead.
static void page_set_box(QPDFPageObjectHelper &poh, char const *key, py::handle value)
{
    QPDFObjectHandle box;
    try {
        box = objecthandle_encode(value);
    } catch (const std::exception &) {
        // objecthandle_encode() raises py::python_error for a failed Python call
        // and std::runtime_error for a type it cannot represent; both derive from
        // std::exception and neither leaves the Python error indicator set.
        throw py::value_error("object is not a rectangle");
    }
    if (!box.isRectangle())
        throw py::value_error("object is not a rectangle");

    auto page = poh.getObjectHandle();
    QpdfLockGuard lock(page.getOwningQPDF());
    page.replaceKey(key, box);
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
            .def_prop_ro("form_xobjects",
                &QPDFPageObjectHelper::getFormXObjects,
                R"(Return all Form XObjects associated with this page.

This method does not recurse into nested Form XObjects.

.. versionadded:: 7.0.0
)")
            .def_prop_rw(
                "mediabox",
                [](QPDFPageObjectHelper &poh) { return poh.getMediaBox(true); },
                [](QPDFPageObjectHelper &poh, py::handle value) {
                    page_set_box(poh, "/MediaBox", value);
                },
                R"(Return page's /MediaBox, in PDF units.

According to the PDF specification:
"The media box defines the boundaries of the physical medium on which
the page is to be printed."
)")
            .def_prop_rw(
                "cropbox",
                [](QPDFPageObjectHelper &poh) { return poh.getCropBox(true, false); },
                [](QPDFPageObjectHelper &poh, py::handle value) {
                    page_set_box(poh, "/CropBox", value);
                },
                R"(Return page's effective /CropBox, in PDF units.

According to the PDF specification:
"The crop box defines the region to which the contents of the page
shall be clipped (cropped) when displayed or printed. It has no
defined meaning in the context of the PDF imaging model; it merely
imposes clipping on the page contents."

If the /CropBox is not defined, the /MediaBox is returned.
)")
            .def_prop_rw(
                "artbox",
                [](QPDFPageObjectHelper &poh) { return poh.getArtBox(true, false); },
                [](QPDFPageObjectHelper &poh, py::handle value) {
                    page_set_box(poh, "/ArtBox", value);
                },
                R"(Return page's effective /ArtBox, in PDF units.

According to the PDF specification:
"The art box defines the page's meaningful content area, including
white space."

If the /ArtBox is not defined, the /CropBox is returned.
)")
            .def_prop_rw(
                "bleedbox",
                [](QPDFPageObjectHelper &poh) { return poh.getBleedBox(true, false); },
                [](QPDFPageObjectHelper &poh, py::handle value) {
                    page_set_box(poh, "/BleedBox", value);
                },
                R"(Return page's effective /BleedBox, in PDF units.

According to the PDF specification:
"The bleed box defines the region to which the contents of the page
should be clipped when output in a print production environment."

If the /BleedBox is not defined, the /CropBox is returned.
)")
            .def_prop_rw(
                "trimbox",
                [](QPDFPageObjectHelper &poh) { return poh.getTrimBox(true, false); },
                [](QPDFPageObjectHelper &poh, py::handle value) {
                    page_set_box(poh, "/TrimBox", value);
                },
                R"(Return page's effective /TrimBox, in PDF units.

According to the PDF specification:
"The trim box defines the intended dimensions of the finished page
after trimming. It may be smaller than the media box to allow for
production-related content, such as printing instructions, cut marks,
or color bars."

If the /TrimBox is not defined, the /CropBox is returned (and if
/CropBox is not defined, /MediaBox is returned).
)")
            .def(
                "externalize_inline_images",
                [](QPDFPageObjectHelper &poh,
                    size_t min_size = 0,
                    bool shallow = false) {
                    return poh.externalizeInlineImages(min_size, shallow);
                },
                py::arg("min_size") = 0,
                py::arg("shallow") = false)
            .def(
                "rotate",
                [](QPDFPageObjectHelper &poh,
                    int angle,
                    py::args args,
                    py::object relative) {
                    // TODO(pikepdf 11): drop positional support for 'relative' --
                    // remove the py::args parameter and this deprecation shim.
                    if (args.size() > 0) {
                        if (args.size() > 1)
                            throw py::type_error(
                                ("rotate() takes at most 2 positional arguments but " +
                                    std::to_string(1 + args.size()) + " were given")
                                    .c_str());
                        deprecation_warning(
                            "Passing 'relative' as a positional argument to "
                            "Page.rotate() is deprecated; pass it as a keyword "
                            "argument instead, e.g. page.rotate(90, relative=True). "
                            "Positional support will be removed in pikepdf 11.");
                        relative = args[0];
                    }
                    int truth = PyObject_IsTrue(relative.ptr());
                    if (truth < 0)
                        throw py::python_error();
                    poh.rotatePage(angle, truth == 1);
                },
                py::arg("angle"),
                py::arg("args"),
                py::kw_only(),
                py::arg("relative") = false,
                R"(Rotate a page.

If ``relative`` is ``False`` (the default), set the rotation of the
page to angle. Otherwise, add angle to the rotation of the
page. ``angle`` must be a multiple of ``90``. Adding ``90`` to
the rotation rotates clockwise by ``90`` degrees.

Args:
    angle: Rotation angle in degrees.
    relative: If ``True``, add ``angle`` to the current
        rotation. If ``False``, set the rotation of the page
        to ``angle``.

.. deprecated:: 10.9
    Passing ``relative`` as a positional argument is deprecated; pass
    it as a keyword argument instead, e.g.
    ``page.rotate(90, relative=True)``. Positional support will be
    removed in pikepdf 11.
)")
            .def_prop_rw(
                "rotation",
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
                },
                [](QPDFPageObjectHelper &poh, int angle) {
                    poh.rotatePage(angle, false);
                },
                R"(The page's clockwise rotation in degrees, normalized to ``[0, 360)``.

Unlike the raw ``page.Rotate`` attribute, this property reports the
*effective* rotation: it resolves a ``/Rotate`` value inherited from the
page tree and reports ``0`` when no rotation is set, instead of raising.
Assigning to this property sets the absolute rotation; to rotate
relative to the current value, use :meth:`rotate` with ``relative=True``.

.. versionadded:: 10.9
)")
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
