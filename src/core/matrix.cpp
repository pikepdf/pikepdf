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

void init_matrix(py::module_ &m)
{
    py::class_<QPDFMatrix>(m, "Matrix", R"~~~(
            An affine matrix for PDF transformations.

            PDF matrices are encoded as :class:`pikepdf.Array` with exactly
            six numeric elements, ordered as ``a b c d e f``.

            .. math::

                \begin{bmatrix}
                a & b & 0 \\
                c & d & 0 \\
                e & f & 1 \\
                \end{bmatrix}

            The parameters mean approximately the following:
            * ``a`` is the horizontal scaling factor.
            * ``b`` is horizontal skewing.
            * ``c`` is vertical skewing.
            * ``d`` is the vertical scaling factor.
            * ``e`` is the horizontal translation.
            * ``f`` is the vertical translation.

            For pure scaling and translation, ``b`` and ``c`` should both be
            0.

            PDF transformation matrices are the transpose of most textbook
            treatments.  In a textbook, typically ``A × vc`` is used to
            transform a column vector ``vc=(x, y, 1)`` by the affine matrix ``A``.
            In PDF, the matrix is the transpose of that in the textbook,
            and ``vr × A'`` is used to transform a row vector ``vr=(x, y, 1)``.

            Transformation matrices specify the transformation from the new
            (transformed) coordinate system to the original (untransformed)
            coordinate system.

            PDF order:

            .. math::

                \begin{equation}
                \begin{bmatrix}
                x' \\
                y' \\
                1
                \end{bmatrix}
                =
                \begin{bmatrix}
                x \\
                y \\
                1
                \end{bmatrix}
                \begin{bmatrix}
                a & b & 0 \\
                c & d & 0 \\
                e & f & 1
                \end{bmatrix}
                \end{equation}


            To concatenate transformations, use the matrix multiple (``@``)
            operator to pre-multiply the next transformation onto existing
            transformations.

            Alternatively, use the .translated(), .scaled(), and .rotated()
            methods to chain transformation operations.

            Matrix objects are immutable. All transformation methods return
            new matrix objects.

            .. versionadded:: 8.7
        )~~~")
        .def(py::init<>())
        .def(py::init<double, double, double, double, double, double>())
        .def(py::init<QPDFMatrix const &>())
        .def(py::init<>([](const py::tuple &t) { return matrix_from_tuple(t); }))
        .def_readonly("a", &QPDFMatrix::a)
        .def_readonly("b", &QPDFMatrix::b)
        .def_readonly("c", &QPDFMatrix::c)
        .def_readonly("d", &QPDFMatrix::d)
        .def_readonly("e", &QPDFMatrix::e)
        .def_readonly("f", &QPDFMatrix::f)
        .def_property_readonly("shorthand",
            [](QPDFMatrix const &self) {
                return py::make_tuple(self.a, self.b, self.c, self.d, self.e, self.f);
            })
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
        .def("rotated",
            [](QPDFMatrix const &self, double angle_degrees_ccw) {
                QPDFMatrix copy(self);
                auto radians = angle_degrees_ccw * pi / 180.0;
                auto c       = std::cos(radians);
                auto s       = std::sin(radians);
                copy.concat(QPDFMatrix(c, -s, s, c, 0, 0));
                return copy;
            })
        .def(
            "__matmul__",
            [](QPDFMatrix const &self, QPDFMatrix const &other) {
                // a.concat(b) ==> b @ a
                auto copy = QPDFMatrix(other);
                copy.concat(self);
                return copy; // self @ other
            },
            py::is_operator())
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
        .def(py::pickle(
            [](QPDFMatrix const &self) {
                return py::make_tuple(self.a, self.b, self.c, self.d, self.e, self.f);
            },
            [](py::tuple t) { return matrix_from_tuple(t); }));
}
