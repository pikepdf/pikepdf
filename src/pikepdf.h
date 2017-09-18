/*
 * This Source Code Form is subject to the terms of the Mozilla Public
 * License, v. 2.0. If a copy of the MPL was not distributed with this
 * file, You can obtain one at http://mozilla.org/MPL/2.0/.
 *
 * Copyright (C) 2017, James R. Barlow (https://github.com/jbarlow83/)
 */

#pragma once

#include <qpdf/PointerHolder.hh>
#include <qpdf/QPDFObjectHandle.hh>
#include <pybind11/pybind11.h>

namespace pybind11 {
    PYBIND11_RUNTIME_EXCEPTION(attr_error, PyExc_AttributeError);
    PYBIND11_RUNTIME_EXCEPTION(notimpl_error, PyExc_NotImplementedError);
};

// Declare PointerHolder<T> as a smart pointer
// https://pybind11.readthedocs.io/en/stable/advanced/smart_ptrs.html#custom-smart-pointers
PYBIND11_DECLARE_HOLDER_TYPE(T, PointerHolder<T>);
namespace pybind11 { namespace detail {
    template <typename T>
    struct holder_helper<PointerHolder<T>> {
        static const T *get(const PointerHolder<T> &p) { return p.getPointer(); }
    };
}}

namespace py = pybind11;

QPDFObjectHandle objecthandle_encode(py::handle obj);otImplementedError);
};

// Declare PointerHolder<T> as a smart pointer
// https://pybind11.readthedocs.io/en/stable/advanced/smart_ptrs.html#custom-smart-pointers
PYBIND11_DECLARE_HOLDER_TYPE(T, PointerHolder<T>);
namespace pybind11 { namespace detail {
    template <typename T>
    struct holder_helper<PointerHolder<T>> {
        static const T *get(const PointerHolder<T> &p) { return p.getPointer(); }
    };
}}

namespace py = pybind11;

// From object.cpp
QPDFObjectHandle objecthandle_encode(py::handle obj);
size_t list_range_check(QPDFObjectHandle& h, int index);
void init_object(py::module& m);