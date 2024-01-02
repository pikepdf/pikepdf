// SPDX-FileCopyrightText: 2023 James R. Barlow
// SPDX-License-Identifier: MPL-2.0

#include <cmath>

#include <qpdf/Constants.h>
#include <qpdf/Types.h>
#include <qpdf/DLL.h>
#include <qpdf/QPDFExc.hh>
#include <qpdf/QPDFMatrix.hh>

#include <pybind11/pybind11.h>
#include <pybind11/stl.h>

#include "pikepdf.h"

constexpr double pi = 3.14159265358979323846;

QPDFMatrix matrix_from_tuple(const py::tuple &t)
{
    if (t.size() != 6) {
        throw py::value_error("tuple must have 6 elements");
    }
    return QPDFMatrix(t[0].cast<double>(),
        t[1].cast<double>(),
        t[2].cast<double>(),
        t[3].cast<double>(),
        t[4].cast<double>(),
        t[5].cast<double>());
}

py::tuple tuple_from_matrix(const QPDFMatrix &m)
{
    return py::make_tuple(m.a, m.b, m.c, m.d, m.e, m.f);
}

void init_matrix(py::module_ &m)
{
    using Point = std::pair<double, double>;
    using Rect  = QPDFObjectHandle::Rectangle;

    py::class_<QPDFMatrix>(m, "Matrix")
        .def(py::init<>())
        .def(py::init<double, double, double, double, double, double>(),
            py::arg("a"),
            py::arg("b"),
            py::arg("c"),
            py::arg("d"),
            py::arg("e"),
            py::arg("f"))
        .def(py::init<QPDFMatrix const &>(), py::arg("other"))
        .def(py::init<>([](QPDFObjectHandle &h) {
            if (!h.isMatrix()) {
                throw py::value_error(
                    "pikepdf.Object could not be converted to Matrix");
            }
            // QPDF defines an older class, QPDFObjectHandle::Matrix,
            // for interop with QPDFObjectHandle. We want to ignore it as
            // much as possible, but here, only the older class has the
            // right function.
            QPDFObjectHandle::Matrix ohmatrix = h.getArrayAsMatrix();
            return QPDFMatrix(ohmatrix);
        }),
            py::arg("h")) // LCOV_EXCL_LINE
        .def(py::init<>([](ObjectList &ol) {
            if (ol.size() != 6) {
                throw py::value_error("ObjectList must have 6 elements");
            }
            std::vector<double> converted(6);
            for (int i = 0; i < 6; ++i) {
                if (!ol.at(i).getValueAsNumber(converted.at(i))) {
                    throw py::value_error("Values must be numeric");
                }
            }
            return QPDFMatrix(converted.at(0),
                converted.at(1),
                converted.at(2),
                converted.at(3),
                converted.at(4),
                converted.at(5));
        }))
        .def(py::init<>([](const py::tuple &t) { return matrix_from_tuple(t); }),
            py::arg("t")) // LCOV_EXCL_LINE
        .def_readonly("a", &QPDFMatrix::a)
        .def_readonly("b", &QPDFMatrix::b)
        .def_readonly("c", &QPDFMatrix::c)
        .def_readonly("d", &QPDFMatrix::d)
        .def_readonly("e", &QPDFMatrix::e)
        .def_readonly("f", &QPDFMatrix::f)
        .def_property_readonly("shorthand", &tuple_from_matrix)
        .def("encode", [](QPDFMatrix const &self) { return py::bytes(self.unparse()); })
        .def("translated",
            [](QPDFMatrix const &self, double tx, double ty) {
                QPDFMatrix copy(self);
                copy.translate(tx, ty);
                return copy;
            })
        .def("scaled",
            [](QPDFMatrix const &self, double sx, double sy) {
                QPDFMatrix copy(self);
                copy.scale(sx, sy);
                return copy;
            })
        .def(
            "rotated",
            [](QPDFMatrix const &self, double angle_degrees_ccw) {
                QPDFMatrix copy(self);
                auto radians = angle_degrees_ccw * pi / 180.0;
                auto c       = std::cos(radians);
                auto s       = std::sin(radians);
                copy.concat(QPDFMatrix(c, s, -s, c, 0, 0));
                return copy;
            },
            py::arg("angle_degrees_ccw"))
        .def(
            "__matmul__",
            [](QPDFMatrix const &self, QPDFMatrix const &other) {
                // As implemented by QPDFMatrix, b.concat(a) ==> a @ b
                // so we must compute other.concat(self) to get self @ other
                auto copy = QPDFMatrix(other);
                copy.concat(self);
                return copy; // self @ other
            },
            py::is_operator(),
            py::arg("other"))
        .def("inverse",
            [](QPDFMatrix const &self) {
                auto determinant = self.a * self.d - self.b * self.c;
                if (determinant == 0.0) {
                    throw std::domain_error("Matrix is not invertible");
                }
                auto adjugate = QPDFMatrix(
                    // clang-format off
                    self.d,
                    -self.b,
                    -self.c,
                    self.a,
                    self.c * self.f - self.d * self.e,
                    self.b * self.e - self.a * self.f
                    // clang-format on
                );
                adjugate.scale(1.0 / determinant, 1.0 / determinant);
                return adjugate;
            })
        .def("__array__",
            [](QPDFMatrix const &self) {
                // Use numpy via Python to avoid a runtime dependency on numpy.
                auto np  = py::module_::import("numpy");
                auto arr = np.attr("array")(
                    // clang-format off
                    py::make_tuple(
                        py::make_tuple(self.a, self.b, 0),
                        py::make_tuple(self.c, self.d, 0),
                        py::make_tuple(self.e, self.f, 1)
                    )
                    // clang-format on
                );
                return arr;
            })
        .def("as_array",
            [](QPDFMatrix const &self) { return QPDFObjectHandle::newArray(self); })
        .def(
            "transform",
            [](QPDFMatrix const &self, Point const &point) {
                double x = point.first;
                double y = point.second;
                double xp, yp;
                self.transform(x, y, xp, yp);
                return py::make_tuple(xp, yp);
            },
            py::arg("point"))
        .def(
            "transform",
            [](QPDFMatrix const &self, Rect const &rect) {
                auto trans_rect = self.transformRectangle(rect);
                return trans_rect;
            },
            py::arg("rect"))
        .def(
            "__eq__",
            [](QPDFMatrix &self, const QPDFMatrix &other) { return self == other; },
            py::is_operator())
        .def("__bool__",
            [](QPDFMatrix &self) {
                // numpy refuses to provide a truth value on arrays so we do too
                throw py::value_error("Truth value of Matrix is ambiguous");
            })
        .def("__repr__",
            [](QPDFMatrix &self) {
                py::str s("pikepdf.Matrix({:g}, {:g}, {:g}, {:g}, {:g}, {:g})");
                return s.format(self.a, self.b, self.c, self.d, self.e, self.f);
            })
        .def("_repr_latex_",
            [](QPDFMatrix &self) {
                py::str s("$$\n\\begin{{bmatrix}}\n"
                          "{:g} & {:g} & 0 \\\\\n"
                          "{:g} & {:g} & 0 \\\\\n"
                          "{:g} & {:g} & 1 \n"
                          "\\end{{bmatrix}}\n$$");
                return s.format(self.a, self.b, self.c, self.d, self.e, self.f);
            })
        .def(py::pickle([](QPDFMatrix const &self) { return tuple_from_matrix(self); },
            [](py::tuple t) { return matrix_from_tuple(t); }));
}
