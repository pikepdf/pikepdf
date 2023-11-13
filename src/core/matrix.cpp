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

    py::class_<QPDFMatrix>(m, "Matrix", R"~~~(
            A 2D affine matrix for PDF transformations.

            PDF uses matrices to transform document coordinates to screen/device
            coordinates.

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

            The values (0, 0, 1) in the third column are fixed, so some
            general matrices cannot be converted to affine matrices.

            PDF transformation matrices are the transpose of most textbook
            treatments.  In a textbook, typically ``A × vc`` is used to
            transform a column vector ``vc=(x, y, 1)`` by the affine matrix ``A``.
            In PDF, the matrix is the transpose of that in the textbook,
            and ``vr × A'`` is used to transform a row vector ``vr=(x, y, 1)``.

            Transformation matrices specify the transformation from the new
            (transformed) coordinate system to the original (untransformed)
            coordinate system. x' and y' are the coordinates in the
            *untransformed* coordinate system, and x and y are the
            coordinates in the *transformed* coordinate system.

            PDF order:

            .. math::

                \begin{equation}
                \begin{bmatrix}
                x' & y' & 1
                \end{bmatrix}
                =
                \begin{bmatrix}
                x & y & 1
                \end{bmatrix}
                \begin{bmatrix}
                a & b & 0 \\
                c & d & 0 \\
                e & f & 1
                \end{bmatrix}
                \end{equation}

            To concatenate transformations, use the matrix multiple (``@``)
            operator to **pre**-multiply the next transformation onto existing
            transformations.

            Alternatively, use the .translated(), .scaled(), and .rotated()
            methods to chain transformation operations.

            Addition and other operations are not implemented because they're not
            that meaningful in a PDF context.

            Matrix objects are immutable. All transformation methods return
            new matrix objects.

            .. versionadded:: 8.7
        )~~~")
        .def(py::init<>(), "Construct an identity matrix.")
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
            py::arg("h"))
        .def(py::init<>([](ObjectList &ol) {
            if (ol.size() != 6) {
                throw py::value_error("ObjectList must have 6 elements");
            }
            double converted[6];
            for (int i = 0; i < 6; ++i) {
                if (!ol[i].getValueAsNumber(converted[i])) {
                    throw py::value_error("Values must be numeric");
                }
            }
            return QPDFMatrix(converted[0],
                converted[1],
                converted[2],
                converted[3],
                converted[4],
                converted[5]);
        }))
        .def(py::init<>([](const py::tuple &t) { return matrix_from_tuple(t); }),
            py::arg("t6"))
        .def_readonly("a", &QPDFMatrix::a)
        .def_readonly("b", &QPDFMatrix::b)
        .def_readonly("c", &QPDFMatrix::c)
        .def_readonly("d", &QPDFMatrix::d)
        .def_readonly("e", &QPDFMatrix::e)
        .def_readonly("f", &QPDFMatrix::f)
        .def_property_readonly("shorthand",
            &tuple_from_matrix,
            "Return the 6-tuple (a,b,c,d,e,f) that describes this matrix.")
        .def(
            "encode",
            [](QPDFMatrix const &self) { return py::bytes(self.unparse()); },
            R"~~~(
            Encode this matrix in bytes suitable for including in a PDF content stream.
            )~~~")
        .def(
            "translated",
            [](QPDFMatrix const &self, double tx, double ty) {
                QPDFMatrix copy(self);
                copy.translate(tx, ty);
                return copy;
            },
            "Return a translated copy of a matrix.")
        .def(
            "scaled",
            [](QPDFMatrix const &self, double sx, double sy) {
                QPDFMatrix copy(self);
                copy.scale(sx, sy);
                return copy;
            },
            "Return a scaled copy of a matrix.")
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
            py::arg("angle_degrees_ccw"),
            R"~~~(
            Return a rotated copy of a matrix.

            Args:
                angle_degrees_ccw: angle in degrees counterclockwise
            )~~~")
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
            py::arg("other"),
            R"~~~(
            Return the matrix product of two matrices.

            Can be used to concatenate transformations. Transformations should be
            composed by **pre**-multiplying matrices.
            )~~~")
        .def(
            "inverse",
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
            },
            R"~~~(
            Return the inverse of the matrix.

            The inverse matrix reverses the transformation of the original matrix.

            In rare situations, the inverse may not exist. In that case, an
            exception is thrown. The PDF will likely have rendering problems.
            )~~~")
        .def(
            "__array__",
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
            },
            R"~~~(
            Convert this matrix to a NumPy array.

            If numpy is not installed, this will throw an exception.
            )~~~")
        .def(
            "as_array",
            [](QPDFMatrix const &self) { return QPDFObjectHandle::newArray(self); },
            R"~~~(
            Convert this matrix to a pikepdf.Array.

            A Matrix cannot be inserted into a PDF directly. Use this function
            to convert a Matrix to a pikepdf.Array, which can be inserted.
            )~~~")
        .def(
            "transform",
            [](QPDFMatrix const &self, Point const &point) {
                double x = point.first;
                double y = point.second;
                double xp, yp;
                self.transform(x, y, xp, yp);
                return py::make_tuple(xp, yp);
            },
            py::arg("point"),
            R"~~~(
            Transform a point by this matrix.

            Computes [x y 1] @ self.
            )~~~")
        .def(
            "transform",
            [](QPDFMatrix const &self, Rect const &rect) {
                auto trans_rect = self.transformRectangle(rect);
                return trans_rect;
            },
            py::arg("rect"),
            R"~~~(
            Transform a rectangle by this matrix.

            The new rectangle tightly bounds the polygon resulting
            from transforming the four corners.
            )~~~")
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
