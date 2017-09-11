#pragma once

#include <qpdf/PointerHolder.hh>
#include <qpdf/QPDFObjectHandle.hh>
#include <pybind11/pybind11.h>

namespace pybind11 {
    PYBIND11_RUNTIME_EXCEPTION(attr_error, PyExc_AttributeError);
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

QPDFObjectHandle objecthandle_encode(py::handle obj);