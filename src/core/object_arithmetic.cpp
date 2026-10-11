// SPDX-FileCopyrightText: 2022 James R. Barlow
// SPDX-License-Identifier: MPL-2.0

// Number protocol for the QPDFObjectHandle ("Object") binding: conversion to
// Python numbers, rounding, ordering and arithmetic for Integer and Real.

#include "numeric-inl.h"
#include "object.h"
#include "pikepdf.h"
#include "qpdf_lock.h"

#include <optional>
#include <string>
#include <utility>

#include <qpdf/QPDFObjectHandle.hh>

// Python stand-in for a numeric Object in arithmetic: int for Integer and
// Decimal for Real, the same types implicit mode would have produced, so the
// result of an expression does not depend on the conversion mode. The one
// exception is a Real combined with a Python float, where Decimal arithmetic
// would refuse the float; the Real becomes a float instead.
py::object arithmetic_operand(QPDFObjectHandle &h, bool other_is_float)
{
    if (h.isInteger())
        return py::cast(h.getIntValue());
    if (h.isReal()) {
        auto value = real_as_double(h);
        if (!value)
            throw py::type_error(
                ("Real object '" + h.getRealValue() + "' is not a valid number")
                    .c_str());
        if (other_is_float)
            return py::cast(*value);
        return decimal_from_pdfobject(h);
    }
    throw py::type_error("Object is not numeric");
}

using binary_number_fn = PyObject *(*)(PyObject *, PyObject *);

static PyObject *number_power(PyObject *a, PyObject *b)
{
    return PyNumber_Power(a, b, Py_None);
}

// Binary arithmetic delegated to Python's number protocol on the stand-ins,
// so int/float/Decimal/Fraction semantics, result types and exceptions
// (ZeroDivisionError, OverflowError) are exactly the standard library's.
// A non-numeric Object raises TypeError; a non-numeric other operand returns
// NotImplemented so Python names both types in its own TypeError.
static py::object binary_arithmetic(
    QPDFObjectHandle &self, py::handle other, binary_number_fn fn, bool reflected)
{
    py::object lhs, rhs;
    if (py::isinstance<QPDFObjectHandle>(other)) {
        auto &other_h = py::cast<QPDFObjectHandle &>(other);
        DualQpdfLockGuard lock(self.getOwningQPDF(), other_h.getOwningQPDF());
        lhs = arithmetic_operand(self, false);
        rhs = arithmetic_operand(other_h, false);
    } else {
        QpdfLockGuard lock(self.getOwningQPDF());
        lhs = arithmetic_operand(self, py::isinstance<py::float_>(other));
        if (!PyNumber_Check(other.ptr()))
            return py::borrow<py::object>(py::handle(Py_NotImplemented));
        rhs = py::borrow(other);
    }
    if (reflected)
        std::swap(lhs, rhs);
    PyObject *result = fn(lhs.ptr(), rhs.ptr());
    if (!result)
        throw py::python_error();
    return py::steal(result);
}

// Python stand-in for a numeric Object in a one-operand number protocol
// method, so round(), int(), format() and so on give the result they would
// give on the value implicit mode produces.
static py::object number_operand(QPDFObjectHandle &self)
{
    QpdfLockGuard lock(self.getOwningQPDF());
    return arithmetic_operand(self, false);
}

static py::object unary_arithmetic(QPDFObjectHandle &self, PyObject *(*fn)(PyObject *))
{
    py::object operand = number_operand(self);
    PyObject *result = fn(operand.ptr());
    if (!result)
        throw py::python_error();
    return py::steal(result);
}

// Python operand standing in for a numeric Object in an ordering comparison:
// int for Integer, Decimal for Real (exact, like __eq__), nullopt for any
// other type. A Real whose token text is not a valid number cannot be ordered.
static std::optional<py::object> ordering_operand(QPDFObjectHandle &h)
{
    if (h.isInteger())
        return py::cast(h.getIntValue());
    if (h.isReal()) {
        if (!real_as_double(h))
            throw py::type_error(
                ("Real object '" + h.getRealValue() + "' is not a valid number")
                    .c_str());
        return decimal_from_pdfobject(h);
    }
    return std::nullopt;
}

// Ordering comparison (<, <=, >, >=) for Integer and Real against Python
// numbers and other numeric Objects, delegated to Python's own comparison so
// int/float/Decimal/Fraction semantics are exactly the standard library's.
// Returns NotImplemented for non-numeric operands so Python reports the
// pikepdf type names in its TypeError. Reflected comparisons need no extra
// methods: Python swaps operands and calls the mirrored operator on us.
static py::object compare_numeric(QPDFObjectHandle &self, py::handle other, int op)
{
    auto not_implemented = [] {
        return py::borrow<py::object>(py::handle(Py_NotImplemented));
    };
    py::object lhs, rhs;
    if (py::isinstance<QPDFObjectHandle>(other)) {
        auto &other_h = py::cast<QPDFObjectHandle &>(other);
        DualQpdfLockGuard lock(self.getOwningQPDF(), other_h.getOwningQPDF());
        auto l = ordering_operand(self);
        if (!l)
            return not_implemented();
        auto r = ordering_operand(other_h);
        if (!r)
            return not_implemented();
        lhs = *l;
        rhs = *r;
    } else {
        QpdfLockGuard lock(self.getOwningQPDF());
        auto l = ordering_operand(self);
        if (!l)
            return not_implemented();
        if (!PyNumber_Check(other.ptr()))
            return not_implemented();
        lhs = *l;
        rhs = py::borrow(other);
    }
    PyObject *result = PyObject_RichCompare(lhs.ptr(), rhs.ptr(), op);
    if (!result)
        throw py::python_error();
    return py::steal(result);
}

void init_object_arithmetic(py::class_<QPDFObjectHandle> &object)
{
    object
        .def("__int__",
            [](QPDFObjectHandle &h) -> py::object {
                // Truncates a Real, as int() of a Decimal does.
                py::object operand = number_operand(h);
                PyObject *result = PyNumber_Long(operand.ptr());
                if (!result)
                    throw py::python_error();
                return py::steal(result);
            })
        .def("__index__",
            [](QPDFObjectHandle &h) -> long long {
                if (!h.isInteger())
                    throw py::type_error("Object is not an integer");
                return h.getIntValue();
            })
        .def("__float__",
            [](QPDFObjectHandle &h) -> double {
                if (h.isInteger())
                    return static_cast<double>(h.getIntValue());
                if (h.isReal())
                    return std::stod(h.getRealValue());
                throw py::type_error("Object is not numeric");
            })
        .def(
            "__round__",
            [](QPDFObjectHandle &h, py::object ndigits) {
                py::object operand = number_operand(h);
                if (ndigits.is_none())
                    return operand.attr("__round__")();
                return operand.attr("__round__")(ndigits);
            },
            py::arg("ndigits") = py::none())
        .def("__trunc__",
            [](QPDFObjectHandle &h) { return number_operand(h).attr("__trunc__")(); })
        .def("__floor__",
            [](QPDFObjectHandle &h) { return number_operand(h).attr("__floor__")(); })
        .def("__ceil__",
            [](QPDFObjectHandle &h) { return number_operand(h).attr("__ceil__")(); })
        .def("__neg__",
            [](QPDFObjectHandle &h) { return unary_arithmetic(h, PyNumber_Negative); })
        .def("__pos__",
            [](QPDFObjectHandle &h) { return unary_arithmetic(h, PyNumber_Positive); })
        .def("__abs__",
            [](QPDFObjectHandle &h) { return unary_arithmetic(h, PyNumber_Absolute); })
        // Ordering comparisons for Integer and Real
        .def(
            "__lt__",
            [](QPDFObjectHandle &h, py::object other) {
                return compare_numeric(h, other, Py_LT);
            },
            py::is_operator())
        .def(
            "__le__",
            [](QPDFObjectHandle &h, py::object other) {
                return compare_numeric(h, other, Py_LE);
            },
            py::is_operator())
        .def(
            "__gt__",
            [](QPDFObjectHandle &h, py::object other) {
                return compare_numeric(h, other, Py_GT);
            },
            py::is_operator())
        .def(
            "__ge__",
            [](QPDFObjectHandle &h, py::object other) {
                return compare_numeric(h, other, Py_GE);
            },
            py::is_operator());

    // Binary arithmetic for Integer and Real. Each operator gets a forward
    // and a reflected method that share one implementation.
    struct ArithmeticOp {
        char const *name;
        char const *reflected_name;
        binary_number_fn fn;
    };
    static constexpr ArithmeticOp arithmetic_ops[] = {
        {"__add__", "__radd__", PyNumber_Add},
        {"__sub__", "__rsub__", PyNumber_Subtract},
        {"__mul__", "__rmul__", PyNumber_Multiply},
        {"__truediv__", "__rtruediv__", PyNumber_TrueDivide},
        {"__floordiv__", "__rfloordiv__", PyNumber_FloorDivide},
        {"__mod__", "__rmod__", PyNumber_Remainder},
        {"__pow__", "__rpow__", number_power},
        {"__divmod__", "__rdivmod__", PyNumber_Divmod},
    };
    for (auto const &op : arithmetic_ops) {
        object.def(
            op.name,
            [fn = op.fn](QPDFObjectHandle &h, py::object other) {
                return binary_arithmetic(h, other, fn, false);
            },
            py::is_operator());
        object.def(
            op.reflected_name,
            [fn = op.fn](QPDFObjectHandle &h, py::object other) {
                return binary_arithmetic(h, other, fn, true);
            },
            py::is_operator());
    }
}
