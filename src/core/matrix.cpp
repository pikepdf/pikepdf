// SPDX-FileCopyrightText: 2023 James R. Barlow
// SPDX-License-Identifier: MPL-2.0

#include "locked_bindings.h"
#include "pikepdf.h"

#include <cmath>

#include <qpdf/Constants.h>
#include <qpdf/DLL.h>
#include <qpdf/QPDFExc.hh>
#include <qpdf/QPDFMatrix.hh>
#include <qpdf/Types.h>

constexpr double pi = 3.14159265358979323846;

QPDFMatrix matrix_from_tuple(const py::tuple &t)
{
    if (t.size() != 6) {
        throw py::value_error("tuple must have 6 elements");
    }
    return QPDFMatrix(py::cast<double>(t[0]),
        py::cast<double>(t[1]),
        py::cast<double>(t[2]),
        py::cast<double>(t[3]),
        py::cast<double>(t[4]),
        py::cast<double>(t[5]));
}

py::tuple tuple_from_matrix(const QPDFMatrix &m)
{
    return py::make_tuple(m.a, m.b, m.c, m.d, m.e, m.f);
}

// A matrix is six numbers. Only building one from an array reads a Pdf.
template <>
struct LockOwner<QPDFMatrix> : NoLock {};

void init_matrix(py::module_ &m)
{
    using Point = std::pair<double, double>;
    using Rect = QPDFObjectHandle::Rectangle;

    locked_class_<QPDFMatrix>(m, "Matrix", py::type_slots(pikepdf_gc_slots))
        .def_constructor<>()
        .def_static("identity", []() { return QPDFMatrix(); })
        .def_constructor<double, double, double, double, double, double>(py::arg("a"),
            py::arg("b"),
            py::arg("c"),
            py::arg("d"),
            py::arg("e"),
            py::arg("f"))
        .def_constructor<QPDFMatrix const &>(py::arg("other"))
        .def_init(
            [](QPDFObjectHandle &h) {
                if (!h.isMatrix()) {
                    // A TypeError, like a native value of the wrong type, so
                    // a caller's exception handling does not depend on the
                    // conversion mode.
                    throw py::type_error(
                        "pikepdf.Object could not be converted to Matrix");
                }
                return QPDFMatrix(h.getArrayAsMatrix());
            },
            py::arg("h")) // LCOV_EXCL_LINE
        .def_init(
            [](ObjectList &ol) {
                if (ol.size() != 6) {
                    throw py::value_error("ObjectList must have 6 elements");
                }
                std::vector<double> converted(6);
                for (int i = 0; i < 6; ++i) {
                    // Each number may be an object of a different Pdf
                    auto item = ol.at(i);
                    QpdfLockGuard lock(item.getOwningQPDF());
                    if (!item.getValueAsNumber(converted.at(i))) {
                        throw py::type_error("Values must be numeric");
                    }
                }
                return QPDFMatrix(converted.at(0),
                    converted.at(1),
                    converted.at(2),
                    converted.at(3),
                    converted.at(4),
                    converted.at(5));
            },
            // The list is locked while it is read, as its own methods do
            py::arg().lock())
        .def_init([](const py::tuple &t) { return matrix_from_tuple(t); },
            py::arg("t")) // LCOV_EXCL_LINE
        .def_ro("a", &QPDFMatrix::a)
        .def_ro("b", &QPDFMatrix::b)
        .def_ro("c", &QPDFMatrix::c)
        .def_ro("d", &QPDFMatrix::d)
        .def_ro("e", &QPDFMatrix::e)
        .def_ro("f", &QPDFMatrix::f)
        .def_prop_ro("shorthand", &tuple_from_matrix)
        .def("encode",
            [](QPDFMatrix const &self) {
                auto unparsed = self.unparse();
                return py::bytes(unparsed.data(), unparsed.size());
            })
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
                auto c = std::cos(radians);
                auto s = std::sin(radians);
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
                // Divide the adjugate by the determinant directly;
                // QPDFMatrix::scale() is a concatenation that would leave the
                // translation terms undivided.
                return QPDFMatrix(
                    // clang-format off
                    self.d / determinant,
                    -self.b / determinant,
                    -self.c / determinant,
                    self.a / determinant,
                    (self.c * self.f - self.d * self.e) / determinant,
                    (self.b * self.e - self.a * self.f) / determinant
                    // clang-format on
                );
            })
        .def(
            "__array__",
            [](QPDFMatrix const &self,
                OpaqueObject const &dtype,
                OpaqueObject const &copy) {
                // Use numpy via Python to avoid a runtime dependency on numpy.
                if (!copy.is_none() && !py::cast<bool>(copy.handle())) {
                    throw py::value_error("copy=False is not supported");
                }
                auto np = py::module_::import_("numpy");
                auto arr = np.attr("array")(
                    // clang-format off
                    py::make_tuple(
                        py::make_tuple(self.a, self.b, 0),
                        py::make_tuple(self.c, self.d, 0),
                        py::make_tuple(self.e, self.f, 1)
                    ),
                    // clang-format on
                    dtype.handle());
                return arr;
            },
            py::arg("dtype") = py::none(),
            py::arg("copy") = py::none())
        .def("as_array",
            [](QPDFMatrix const &self) { return QPDFObjectHandle::newArray(self); })
        .def(
            "transform",
            [](QPDFMatrix const &self, Point point) {
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
                return s.attr("format")(self.a, self.b, self.c, self.d, self.e, self.f);
            })
        .def("_repr_latex_",
            [](QPDFMatrix &self) {
                py::str s(R"($$
\begin{{bmatrix}}
{:g} & {:g} & 0 \\
{:g} & {:g} & 0 \\
{:g} & {:g} & 1
\end{{bmatrix}}
$$)");
                return s.attr("format")(self.a, self.b, self.c, self.d, self.e, self.f);
            })
        .def("__getstate__",
            [](QPDFMatrix const &self) { return tuple_from_matrix(self); })
        .def("__setstate__", [](QPDFMatrix &self, py::tuple t) {
            new (&self) QPDFMatrix(matrix_from_tuple(t));
        });
}
