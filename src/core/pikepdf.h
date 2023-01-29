// SPDX-FileCopyrightText: 2022 James R. Barlow
// SPDX-License-Identifier: MPL-2.0

#pragma once

#include <exception>
#include <vector>
#include <map>

#include <qpdf/QPDF.hh>
#include <qpdf/Constants.h>
#include <qpdf/QPDFObjectHandle.hh>
#include <qpdf/QPDFPageObjectHelper.hh>

#include <pybind11/pybind11.h>
#include <pybind11/stl.h>
#include <pybind11/stl_bind.h>

using uint = unsigned int;

namespace pybind11 {
PYBIND11_RUNTIME_EXCEPTION(notimpl_error, PyExc_NotImplementedError);
}; // namespace pybind11

// From object_convert.cpp
pybind11::object decimal_from_pdfobject(QPDFObjectHandle h);

namespace pybind11 {
namespace detail {
template <>
struct type_caster<QPDFObjectHandle> : public type_caster_base<QPDFObjectHandle> {
    using base = type_caster_base<QPDFObjectHandle>;

protected:
    QPDFObjectHandle value;

public:
    /**
     * Conversion part 1 (Python->C++): convert a PyObject into a Object
     */
    bool load(handle src, bool convert)
    {
        // Do whatever our base does
        // Potentially we could convert some scalars to QPDFObjectHandle here,
        // but most of the interfaces just expect straight C++ types.
        return base::load(src, convert);
    }

    /**
     * Conversion part 2 (C++ -> Python): convert an instance into
     * a Python object.
     * Purpose of this is to establish the indirect keep_alive relationship
     * between QPDF and objects that refer back to in ways that pybind11
     * can't trace on its own.
     * We also convert several QPDFObjectHandle types to native Python
     * objects here.
     * The ==take_ownership code is disabled. This would only occur if a raw
     * pointer is returned to Python, which we prohibit.
     */
private:
    // 'private': disallow returning pointers to QPDFObjectHandle from bindings
    static handle cast(
        const QPDFObjectHandle *csrc, return_value_policy policy, handle parent)
    {
        if (policy == return_value_policy::take_ownership) {
            throw std::logic_error(
                "return_value_policy::take_ownership not implemented");
        }
        QPDFObjectHandle *src = const_cast<QPDFObjectHandle *>(csrc);
        if (!csrc)
            return none().release(); // LCOV_EXCL_LINE

        switch (src->getTypeCode()) {
        case qpdf_object_type_e::ot_null:
            return pybind11::none().release();
        case qpdf_object_type_e::ot_integer:
            return pybind11::int_(src->getIntValue()).release();
        case qpdf_object_type_e::ot_boolean:
            return pybind11::bool_(src->getBoolValue()).release();
        case qpdf_object_type_e::ot_real:
            return decimal_from_pdfobject(*src).release();
        default:
            break;
        }
        return base::cast(*csrc, policy, parent);
    }

public:
    static handle cast(
        QPDFObjectHandle &&src, return_value_policy policy, handle parent)
    {
        return cast(&src, return_value_policy::move, parent);
    }

    static handle cast(
        const QPDFObjectHandle &src, return_value_policy policy, handle parent)
    {
        if (policy == return_value_policy::automatic ||
            policy == return_value_policy::automatic_reference)
            policy = return_value_policy::copy;
        return cast(&src, policy, parent);
    }
};

} // namespace detail
} // namespace pybind11

namespace py = pybind11;

using ObjectList = std::vector<QPDFObjectHandle>;
PYBIND11_MAKE_OPAQUE(ObjectList);

using ObjectMap = std::map<std::string, QPDFObjectHandle>;
PYBIND11_MAKE_OPAQUE(ObjectMap);

// From qpdf.cpp
void init_qpdf(py::module_ &m);

// From object.cpp
size_t list_range_check(QPDFObjectHandle h, int index);
void init_object(py::module_ &m);
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

// From annotation.cpp
void init_annotation(py::module_ &m);
// From embeddedfiles.cpp
void init_embeddedfiles(py::module_ &m);
// From job.cpp
void init_job(py::module_ &m);
// From logger.cpp
void init_logger(py::module_ &m);
std::shared_ptr<QPDFLogger> get_pikepdf_logger();
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

inline void python_warning(const char *msg, PyObject *category = PyExc_UserWarning)
{
    PyErr_WarnEx(category, msg, /*stacklevel=*/1);
}

inline void deprecation_warning(const char *msg)
{
    python_warning(msg, PyExc_DeprecationWarning); // LCOV_EXCL_LINE
}

// Support for recursion checks
class StackGuard {
public:
    StackGuard(const char *where) { Py_EnterRecursiveCall(where); }
    StackGuard(const StackGuard &)            = delete;
    StackGuard &operator=(const StackGuard &) = delete;
    StackGuard(StackGuard &&)                 = delete;
    StackGuard &operator=(StackGuard &&)      = delete;
    ~StackGuard() { Py_LeaveRecursiveCall(); }
};
