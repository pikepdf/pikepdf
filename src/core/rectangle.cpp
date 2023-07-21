// SPDX-FileCopyrightText: 2022 James R. Barlow
// SPDX-License-Identifier: MPL-2.0

#include <qpdf/QPDFObjectHandle.hh>

#include <pybind11/pybind11.h>

#include "pikepdf.h"

void init_rectangle(py::module_ &m)
{
    using Point = std::pair<double, double>;

    using Rect = QPDFObjectHandle::Rectangle;
    py::class_<Rect>(m,
        "Rectangle",
        R"~~~(
            A PDF rectangle.

            Typically this will be a rectangle in PDF units (points, 1/72").
            Unlike raster graphics, the rectangle is defined by the **lower**
            left and upper right points.

            Rectangles in PDF are encoded as :class:`pikepdf.Array` with exactly
            four numeric elements, ordered as ``llx lly urx ury``.
            See |pdfrm| section 7.9.5.

            The rectangle may be considered degenerate if the lower left corner
            is not strictly less than the upper right corner.

            .. versionadded:: 2.14
        )~~~")
        .def(py::init<double, double, double, double>())
        .def(py::init([](QPDFObjectHandle &h) {
            if (!h.isArray()) {
                throw py::type_error(
                    "Object is not an array; cannot convert to Rectangle");
            }
            if (h.getArrayNItems() != 4) {
                throw py::type_error("Array does not have exactly 4 elements; cannot "
                                     "convert to Rectangle");
            }
            Rect r = h.getArrayAsRectangle();
            if (r.llx == 0.0 && r.lly == 0.0 && r.urx == 0.0 && r.ury == 0.0)
                throw py::type_error("Failed to convert Array to a valid Rectangle");
            return r;
        }))
        .def(
            "__eq__",
            [](Rect &self, Rect &other) {
                return self.llx == other.llx && self.lly == other.lly &&
                       self.urx == other.urx && self.ury == other.ury;
            },
            py::is_operator())
        .def_property(
            "llx",
            [](Rect &r) { return r.llx; },
            [](Rect &r, double v) { r.llx = v; },
            "The lower left corner on the x-axis.")
        .def_property(
            "lly",
            [](Rect &r) { return r.lly; },
            [](Rect &r, double v) { r.lly = v; },
            "The lower left corner on the y-axis.")
        .def_property(
            "urx",
            [](Rect &r) { return r.urx; },
            [](Rect &r, double v) { r.urx = v; },
            "The upper right corner on the x-axis.")
        .def_property(
            "ury",
            [](Rect &r) { return r.ury; },
            [](Rect &r, double v) { r.ury = v; },
            "The upper right corner on the y-axis.")
        .def_property_readonly(
            "width",
            [](Rect &r) { return r.urx - r.llx; },
            "The width of the rectangle.")
        .def_property_readonly(
            "height",
            [](Rect &r) { return r.ury - r.lly; },
            "The height of the rectangle.")
        .def_property_readonly(
            "lower_left",
            [](Rect &r) { return Point(r.llx, r.lly); },
            "A point for the lower left corner.")
        .def_property_readonly(
            "lower_right",
            [](Rect &r) { return Point(r.urx, r.lly); },
            "A point for the lower right corner.")
        .def_property_readonly(
            "upper_right",
            [](Rect &r) { return Point(r.urx, r.ury); },
            "A point for the upper right corner.")
        .def_property_readonly(
            "upper_left",
            [](Rect &r) { return Point(r.llx, r.ury); },
            "A point for the upper left corner.")
        .def(
            "as_array",
            [](Rect &r) { return QPDFObjectHandle::newArray(r); },
            "Returns this rectangle as a :class:`pikepdf.Array`.");

    py::implicitly_convertible<Rect, QPDFObjectHandle>();
}
