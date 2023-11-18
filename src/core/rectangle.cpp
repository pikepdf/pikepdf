// SPDX-FileCopyrightText: 2022 James R. Barlow
// SPDX-License-Identifier: MPL-2.0

#include <qpdf/QPDFObjectHandle.hh>

#include <pybind11/pybind11.h>

#include "pikepdf.h"

void init_rectangle(py::module_ &m)
{
    using Point = std::pair<double, double>;
    using Rect  = QPDFObjectHandle::Rectangle;

    py::class_<Rect>(m, "Rectangle")
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
            py::arg("other"), // LCOV_EXCL_LINE
            py::is_operator())
        .def(
            "__le__",
            [](Rect &self, Rect &other) {
                return self.llx >= other.llx && self.lly >= other.lly &&
                       self.urx <= other.urx && self.ury <= other.ury;
            },
            py::arg("other"), // LCOV_EXCL_LINE
            py::is_operator())
        .def(
            "__and__",
            [](Rect &self, Rect &other) -> Rect {
                return {std::max(self.llx, other.llx),
                    std::max(self.lly, other.lly),
                    std::min(self.urx, other.urx),
                    std::min(self.ury, other.ury)};
            },
            py::arg("other"),
            py::is_operator())
        .def_property(
            "llx", [](Rect &r) { return r.llx; }, [](Rect &r, double v) { r.llx = v; })
        .def_property(
            "lly", [](Rect &r) { return r.lly; }, [](Rect &r, double v) { r.lly = v; })
        .def_property(
            "urx", [](Rect &r) { return r.urx; }, [](Rect &r, double v) { r.urx = v; })
        .def_property(
            "ury", [](Rect &r) { return r.ury; }, [](Rect &r, double v) { r.ury = v; })
        .def_property_readonly("width", [](Rect &r) { return r.urx - r.llx; })
        .def_property_readonly("height", [](Rect &r) { return r.ury - r.lly; })
        .def_property_readonly(
            "lower_left", [](Rect &r) { return Point(r.llx, r.lly); })
        .def_property_readonly(
            "lower_right", [](Rect &r) { return Point(r.urx, r.lly); })
        .def_property_readonly(
            "upper_right", [](Rect &r) { return Point(r.urx, r.ury); })
        .def_property_readonly(
            "upper_left", [](Rect &r) { return Point(r.llx, r.ury); })
        .def("as_array", [](Rect &r) { return QPDFObjectHandle::newArray(r); });

    py::implicitly_convertible<Rect, QPDFObjectHandle>();
}
