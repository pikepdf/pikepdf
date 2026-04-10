// SPDX-FileCopyrightText: 2022 James R. Barlow
// SPDX-License-Identifier: MPL-2.0

#pragma once

#include <exception>
#include <map>
#include <vector>

#include <qpdf/Constants.h>
#include <qpdf/QPDF.hh>
#include <qpdf/QPDFObjectHandle.hh>
#include <qpdf/QPDFPageObjectHelper.hh>

#include <nanobind/nanobind.h>
#include <nanobind/stl/bind_map.h>
#include <nanobind/stl/bind_vector.h>
#include <nanobind/stl/map.h>
#include <nanobind/stl/pair.h>
#include <nanobind/stl/set.h>
#include <nanobind/stl/shared_ptr.h>
#include <nanobind/stl/string.h>
#include <nanobind/stl/vector.h>

using uint = unsigned int;

// Use 'py' as alias for nanobind to minimize diff across all binding files.
// Most nanobind types share names with pybind11 (py::object, py::str, etc.).
namespace py = nanobind;

// GC traversal slots for all nanobind-bound types. Enables Py_TPFLAGS_HAVE_GC
// so Python's cyclic GC can break type-level reference cycles (type -> method
// descriptors -> type) at shutdown. See nanobind refleaks docs.
inline PyType_Slot pikepdf_gc_slots[] = {
    {Py_tp_traverse,
        (void *)+[](PyObject *self, visitproc visit, void *arg) -> int {
            Py_VISIT(Py_TYPE(self));
            return 0;
        }},
    {Py_tp_clear, (void *)+[](PyObject *) -> int { return 0; }},
    {0, nullptr}};

// From object_convert.cpp
py::object decimal_from_pdfobject(QPDFObjectHandle h);

// From pikepdf.cpp - forward declaration for type_caster
bool get_explicit_conversion_mode();

namespace nanobind {
namespace detail {
template <>
struct type_caster<QPDFObjectHandle> : public type_caster_base<QPDFObjectHandle> {
    using base = type_caster_base<QPDFObjectHandle>;

    NB_INLINE bool from_python(
        handle src, uint8_t flags, cleanup_list *cleanup) noexcept
    {
        return base::from_python(src, flags, cleanup);
    }

    template <typename T>
    NB_INLINE static handle from_cpp(
        T &&value, rv_policy policy, cleanup_list *cleanup) noexcept
    {
        QPDFObjectHandle *src;
        if constexpr (is_pointer_v<T>)
            src = (QPDFObjectHandle *)value;
        else
            src = (QPDFObjectHandle *)&value;

        if (!src)
            return handle(Py_None).inc_ref();

        // Adjust automatic policies to copy
        if (policy == rv_policy::automatic || policy == rv_policy::automatic_reference)
            policy = rv_policy::copy;

        // In explicit conversion mode, return scalars as pikepdf.Object
        // so that Integer/Boolean/Real types are preserved.
        // In implicit mode (default), auto-convert to native Python types.
        if (!get_explicit_conversion_mode()) {
            switch (src->getTypeCode()) {
            case qpdf_object_type_e::ot_null:
                return handle(Py_None).inc_ref();
            case qpdf_object_type_e::ot_integer:
                return nanobind::int_(src->getIntValue()).release();
            case qpdf_object_type_e::ot_boolean:
                return nanobind::bool_(src->getBoolValue()).release();
            case qpdf_object_type_e::ot_real:
                try {
                    return decimal_from_pdfobject(*src).release();
                } catch (...) {
                    return handle(); // noexcept: return null on failure
                }
            default:
                break;
            }
        } else {
            // Explicit mode: still convert null to None (no value in pikepdf.Null)
            if (src->getTypeCode() == qpdf_object_type_e::ot_null) {
                return handle(Py_None).inc_ref();
            }
        }
        return base::from_cpp(std::forward<T>(value), policy, cleanup);
    }
};

} // namespace detail
} // namespace nanobind

using ObjectList = std::vector<QPDFObjectHandle>;
NB_MAKE_OPAQUE(ObjectList);

using ObjectMap = std::map<std::string, QPDFObjectHandle>;
NB_MAKE_OPAQUE(ObjectMap);

// From qpdf.cpp
void init_qpdf(py::module_ &m);

// From object.cpp
size_t list_range_check(QPDFObjectHandle h, int index);
void init_object(py::module_ &m);

// From object_equality.cpp
bool objecthandle_equal(QPDFObjectHandle self, QPDFObjectHandle other);

// From object_repr.cpp
std::string objecthandle_scalar_value(QPDFObjectHandle h);
std::string objecthandle_pythonic_typename(QPDFObjectHandle h);
std::string objecthandle_repr_typename_and_value(QPDFObjectHandle h);
std::string objecthandle_repr(QPDFObjectHandle h);

// From object_convert.cpp
py::object decimal_from_pdfobject(QPDFObjectHandle h);
QPDFObjectHandle objecthandle_encode(const py::handle handle);
std::vector<QPDFObjectHandle> array_builder(const py::iterable iter);
std::map<std::string, QPDFObjectHandle> dict_builder(const py::dict dict);

// From acroform.cpp
void init_acroform(py::module_ &m);
// From annotation.cpp
void init_annotation(py::module_ &m);
// From embeddedfiles.cpp
void init_embeddedfiles(py::module_ &m);
// From job.cpp
void init_job(py::module_ &m);
// From logger.cpp
void init_logger(py::module_ &m);
std::shared_ptr<QPDFLogger> get_pikepdf_logger();
// From matrix.cpp
void init_matrix(py::module_ &m);
// From nametree.cpp
void init_nametree(py::module_ &m);
// From numbertree.cpp
void init_numbertree(py::module_ &m);
// From page.cpp
void init_page(py::module_ &m);
size_t page_index(QPDF &owner, QPDFObjectHandle page);
// From parsers.cpp
void init_parsers(py::module_ &m);
// From rectangle.cpp
void init_rectangle(py::module_ &m);
// From tokenfilter.cpp
void init_tokenfilter(py::module_ &m);

// pikepdf.cpp
uint get_decimal_precision();
bool get_mmap_default();
bool get_explicit_conversion_mode();

inline void python_warning(const char *msg, PyObject *category = PyExc_UserWarning)
{
    PyErr_WarnEx(category, msg, /*stacklevel=*/1);
}

inline void deprecation_warning(const char *msg)
{
    python_warning(msg, PyExc_DeprecationWarning); // LCOV_EXCL_LINE
}

// Helper: convert a py::bytes or py::str to std::string.
// Nanobind's std::string type_caster only accepts py::str, unlike pybind11
// which also accepts py::bytes. This helper handles both.
inline std::string to_string(py::handle src)
{
    if (py::isinstance<py::bytes>(src)) {
        py::bytes b = py::borrow<py::bytes>(src);
        return std::string(static_cast<const char *>(b.data()), b.size());
    }
    if (py::isinstance<py::str>(src)) {
        return py::cast<std::string>(src);
    }
    throw py::type_error("expected str or bytes");
}

// Support for recursion checks
class StackGuard {
public:
    StackGuard(const char *where)
    {
        if (Py_EnterRecursiveCall(where) != 0) {
            throw py::python_error();
        }
    }
    StackGuard(const StackGuard &) = delete;
    StackGuard &operator=(const StackGuard &) = delete;
    StackGuard(StackGuard &&) = delete;
    StackGuard &operator=(StackGuard &&) = delete;
    ~StackGuard() { Py_LeaveRecursiveCall(); }
};
