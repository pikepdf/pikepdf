/*
 * This Source Code Form is subject to the terms of the Mozilla Public
 * License, v. 2.0. If a copy of the MPL was not distributed with this
 * file, You can obtain one at http://mozilla.org/MPL/2.0/.
 *
 * Copyright (C) 2019, James R. Barlow (https://github.com/jbarlow83/)
 */

#include <qpdf/QPDFObjectHandle.hh>

#include <pybind11/pybind11.h>

#include "pikepdf.h"

void init_rectangle(py::module_ &m)
{
    using Rect = QPDFObjectHandle::Rectangle;
    py::class_<Rect>(m, "Rectangle")
        .def(py::init<>())
        .def(py::init<double, double, double, double>())
        .def(py::init([](QPDFObjectHandle &h) {
            if (h.isArray() && h.getArrayNItems() == 4)
                return h.getArrayAsRectangle();
            throw py::cast_error("not a numeric array");
        }))
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
        .def("as_array", [](Rect &r) { return QPDFObjectHandle::newArray(r); });

    py::implicitly_convertible<Rect, QPDFObjectHandle>();
}