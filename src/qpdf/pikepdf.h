/*
 * This Source Code Form is subject to the terms of the Mozilla Public
 * License, v. 2.0. If a copy of the MPL was not distributed with this
 * file, You can obtain one at http://mozilla.org/MPL/2.0/.
 *
 * Copyright (C) 2017, James R. Barlow (https://github.com/jbarlow83/)
 */

#pragma once

#include <exception>
#include <vector>
#include <map>

#include <qpdf/PointerHolder.hh>
#include <qpdf/QPDF.hh>
#include <qpdf/QPDFObjectHandle.hh>
#include <qpdf/QPDFPageObjectHelper.hh>

#include <pybind11/pybind11.h>
#include <pybind11/stl.h>
#include <pybind11/stl_bind.h>

using uint = unsigned int;

namespace pybind11 {
PYBIND11_RUNTIME_EXCEPTION(attr_error, PyExc_AttributeError);
PYBIND11_RUNTIME_EXCEPTION(notimpl_error, PyExc_NotImplementedError);
}; // namespace pybind11

// Declare PointerHolder<T> as a smart pointer
// https://pybind11.readthedocs.io/en/stable/advanced/smart_ptrs.html#custom-smart-pointers
PYBIND11_DECLARE_HOLDER_TYPE(T, PointerHolder<T>);
namespace pybind11 {
namespace detail {
template <typename T>
struct holder_helper<PointerHolder<T>> {
    static const T *get(const PointerHolder<T> &p) { return p.getPointer(); }
};
} // namespace detail
} // namespace pybind11

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
     * The ==take_ownership code paths are currently unused but present
     * for completeness. They are unused because pybind11 only sets
     * take_ownership when a binding returns raw pointers to Python, and
     * by making this caster private we prohibit that.
     */
private:
    // 'private': disallow returning pointers to QPDFObjectHandle from bindings
    static handle cast(
        const QPDFObjectHandle *csrc, return_value_policy policy, handle parent)
    {
        QPDFObjectHandle *src = const_cast<QPDFObjectHandle *>(csrc);
        if (!csrc)
            return none().release();

        bool primitive = true;
        handle h;

        switch (src->getTypeCode()) {
        case QPDFObject::object_type_e::ot_null:
            h = pybind11::none().release();
            break;
        case QPDFObject::object_type_e::ot_integer:
            h = pybind11::int_(src->getIntValue()).release();
            break;
        case QPDFObject::object_type_e::ot_boolean:
            h = pybind11::bool_(src->getBoolValue()).release();
            break;
        case QPDFObject::object_type_e::ot_real:
            h = decimal_from_pdfobject(*src).release();
            break;
        default:
            primitive = false;
            break;
        }
        if (primitive && h) {
            if (policy == return_value_policy::take_ownership) {
                // LCOV_EXCL_START
                // See explanation above - does not happen.
                delete csrc;
                // LCOV_EXCL_STOP
            }
            return h;
        }

        if (policy == return_value_policy::take_ownership) {
            // LCOV_EXCL_START
            // See explanation above - does not happen.
            h = base::cast(std::move(*csrc), policy, parent);
            delete csrc;
            // LCOV_EXCL_STOP
        } else {
            h = base::cast(*csrc, policy, parent);
        }
        QPDF *owner = src->getOwningQPDF();
        if (owner) {
            // Find the Python object that refers to our owner
            // Can do that by casting or more direct lookup
            // auto pyqpdf = pybind11::cast(owner);
            auto tinfo    = get_type_info(typeid(QPDF));
            handle pyqpdf = get_object_handle(owner, tinfo);

            // Tell pybind11 that it must keep pyqpdf alive as long as h is
            // alive
            keep_alive_impl(h, pyqpdf);
        }
        return h;
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

template <>
struct type_caster<QPDFPageObjectHelper>
    : public type_caster_base<QPDFPageObjectHelper> {
    using base = type_caster_base<QPDFPageObjectHelper>;

protected:
    QPDFPageObjectHelper value{QPDFObjectHandle()};

public:
    /**
     * Conversion part 1 (Python->C++): convert a PyObject into a Object
     */
    bool load(handle src, bool convert)
    {
        // Do whatever our base does
        return base::load(src, convert);
    }

    /**
     * Conversion part 2 (C++ -> Python): convert an instance into
     * a Python object.
     * Purpose of this is to establish the indirect keep_alive relationship
     * between QPDF and object helpers that refer back to in ways that pybind11
     * can't trace on its own. Object helpers implicitly reference an object
     handle
     * and whatever data is attached to the handle.
     * The ==take_ownership code paths are currently unused but present
     * for completeness. They are unused because pybind11 only sets
     * take_ownership when a binding returns raw pointers to Python, and
     * by making this caster private we prohibit that.
     */
private:
    // 'private': disallow returning pointers to QPDFPageObjectHelper from bindings
    static handle cast(
        const QPDFPageObjectHelper *csrc, return_value_policy policy, handle parent)
    {
        QPDFPageObjectHelper *src = const_cast<QPDFPageObjectHelper *>(csrc);
        if (!csrc)
            return none().release();

        handle h;

        if (policy == return_value_policy::take_ownership) {
            // LCOV_EXCL_START
            // See explanation above - does not happen.
            h = base::cast(std::move(*csrc), policy, parent);
            delete csrc;
            // LCOV_EXCL_STOP
        } else {
            h = base::cast(*csrc, policy, parent);
        }
        QPDF *owner = src->getObjectHandle().getOwningQPDF();
        if (owner) {
            // Find the Python object that refers to our owner
            // Can do that by casting or more direct lookup
            // auto pyqpdf = pybind11::cast(owner);
            auto tinfo    = get_type_info(typeid(QPDF));
            handle pyqpdf = get_object_handle(owner, tinfo);

            // Tell pybind11 that it must keep pyqpdf alive as long as h is
            // alive
            keep_alive_impl(h, pyqpdf);
        }
        return h;
    }

public:
    static handle cast(
        QPDFPageObjectHelper &&src, return_value_policy policy, handle parent)
    {
        return cast(&src, return_value_policy::move, parent);
    }

    static handle cast(
        const QPDFPageObjectHelper &src, return_value_policy policy, handle parent)
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
// From nametree.cpp
void init_nametree(py::module_ &m);

// From page.cpp
void init_page(py::module_ &m);
size_t page_index(QPDF &owner, QPDFObjectHandle page);

// From parsers.cpp
void init_parsers(py::module_ &m);

// From rectangle.cpp
void init_rectangle(py::module_ &m);

// From tokenfilter.cpp
void init_tokenfilter(py::module_ &m);

inline char *fix_pypy36_const_char(const char *s)
{
    // PyPy 7.3.1 (=Python 3.6) has a few functions incorrectly defined as requiring
    // char* where CPython specifies const char*. PyPy corrected this in newer versions.
    // So this harmless shim is needed to support some older PyPy's.
    return const_cast<char *>(s);
}

inline void python_warning(const char *msg, PyObject *category = PyExc_UserWarning)
{
    PyErr_WarnEx(category, msg, /*stacklevel=*/1);
}

inline void deprecation_warning(const char *msg)
{
    python_warning(msg, PyExc_DeprecationWarning);
}

// Support for recursion checks
class StackGuard {
public:
    StackGuard(const char *where)
    {
        Py_EnterRecursiveCall(fix_pypy36_const_char(where));
    }
    StackGuard(const StackGuard &) = delete;
    StackGuard &operator=(const StackGuard &) = delete;
    StackGuard(StackGuard &&)                 = delete;
    StackGuard &operator=(StackGuard &&) = delete;
    ~StackGuard() { Py_LeaveRecursiveCall(); }
};
