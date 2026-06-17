// SPDX-FileCopyrightText: 2022 James R. Barlow
// SPDX-License-Identifier: MPL-2.0

#include "pikepdf.h"

#include <qpdf/QPDFObjectHandle.hh>

void init_rectangle(py::module_ &m)
{
    using Point = std::pair<double, double>;
    using Rect = QPDFObjectHandle::Rectangle;

    py::class_<Rect>(m, "Rectangle", py::type_slots(pikepdf_gc_slots))
        .def(py::init<double, double, double, double>())
        .def("__init__",
            [](Rect *self, QPDFObjectHandle &h) {
                if (!h.isArray()) {
                    throw py::type_error(
                        "Object is not an array; cannot convert to Rectangle");
                }
                // isRectangle() is true iff h is an array of exactly four numeric
                // values, which is precisely when getArrayAsRectangle() succeeds.
                // Guarding with it removes the ambiguity that getArrayAsRectangle()
                // returns (0,0,0,0) both on error and for a genuine zero rectangle.
                // The helper performs the same min/max normalization done by hand.
                if (!h.isRectangle()) {
                    throw py::type_error(
                        "Array is not a valid Rectangle; need exactly 4 numeric "
                        "elements");
                }
                new (self) Rect(h.getArrayAsRectangle());
            })
        .def("__init__",
            [](Rect *self, const Rect &r) {
                new (self) Rect(r.llx, r.lly, r.urx, r.ury);
            })
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
        .def_prop_rw(
            "llx", [](Rect &r) { return r.llx; }, [](Rect &r, double v) { r.llx = v; })
        .def_prop_rw(
            "lly", [](Rect &r) { return r.lly; }, [](Rect &r, double v) { r.lly = v; })
        .def_prop_rw(
            "urx", [](Rect &r) { return r.urx; }, [](Rect &r, double v) { r.urx = v; })
        .def_prop_rw(
            "ury", [](Rect &r) { return r.ury; }, [](Rect &r, double v) { r.ury = v; })
        .def_prop_ro("width", [](Rect &r) { return r.urx - r.llx; })
        .def_prop_ro("height", [](Rect &r) { return r.ury - r.lly; })
        .def_prop_ro("lower_left", [](Rect &r) { return Point(r.llx, r.lly); })
        .def_prop_ro("lower_right", [](Rect &r) { return Point(r.urx, r.lly); })
        .def_prop_ro("upper_right", [](Rect &r) { return Point(r.urx, r.ury); })
        .def_prop_ro("upper_left", [](Rect &r) { return Point(r.llx, r.ury); })
        .def("as_array", [](Rect &r) { return QPDFObjectHandle::newArray(r); });
}
