/*
 * This Source Code Form is subject to the terms of the Mozilla Public
 * License, v. 2.0. If a copy of the MPL was not distributed with this
 * file, You can obtain one at http://mozilla.org/MPL/2.0/.
 *
 * Copyright (C) 2017, James R. Barlow (https://github.com/jbarlow83/)
 */

#pragma once

#include <qpdf/PointerHolder.hh>
#include <qpdf/QPDF.hh>
#include <qpdf/QPDFObjectHandle.hh>
#include <pybind11/pybind11.h>

#if __cplusplus < 201402L  // If C++11

#include <memory>
#include <type_traits>
#include <utility>
#include <string>

// Provide make_unique for C++11 (not array-capable)
// See https://stackoverflow.com/questions/17902405/how-to-implement-make-unique-function-in-c11/17902439#17902439 for full version if needed
namespace std {
    template<typename T, typename ...Args>
    unique_ptr<T> make_unique( Args&& ...args )
    {
        return unique_ptr<T>( new T( std::forward<Args>(args)... ) );
    }

    string quoted(const char* s);
    string quoted(const string &s);
};
#endif // }}

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

#define DEBUG_TYPE_CONVERSION 1
#if DEBUG_TYPE_CONVERSION
namespace pybind11 { namespace detail {
    template <> struct type_caster<QPDFObjectHandle> : public type_caster_base<QPDFObjectHandle> {
        using base = type_caster_base<QPDFObjectHandle>;
    public:

        /**
         * Conversion part 1 (Python->C++): convert a PyObject into a Object
         */
        bool load(handle src, bool convert) {
            // We just want default behavior, and this is the best known way to
            // get it. Drawback is the required copy.
            if (base::load(src, convert)) {
                return true;
            }
            return false;
        }

        /**
         * Conversion part 2 (C++ -> Python): convert an instance into
         * a Python object.
         * Purpose of this is to establish the indirect keep_alive relationship
         * between QPDF and objects that refer back to in ways that pybind11
         * can't trace on its own.
         * Could consider unboxing Integer, Boolean, etc. here
         */
        static handle cast(QPDFObjectHandle src, return_value_policy policy, handle parent) {
            QPDF *owner = src.getOwningQPDF();
            handle h = base::cast(src, policy, parent);
            if (owner) {
                // Find the Python object that refers to our owner
                // Can do that by casting or more direct lookup
                //auto pyqpdf = pybind11::cast(owner);
                auto tinfo = get_type_info(typeid(QPDF));
                handle pyqpdf = get_object_handle(owner, tinfo);
                
                // Tell pybind11 that it must keep pyqpdf alive as long as h is
                // alive
                keep_alive_impl(h, pyqpdf);
            }
            return h;
        }
    };
}} // namespace pybind11::detail
#endif

namespace py = pybind11;

// From object.cpp
size_t list_range_check(QPDFObjectHandle& h, int index);
void init_object(py::module& m);

// From object_repr.cpp
std::string objecthandle_scalar_value(QPDFObjectHandle& h, bool escaped=true);
std::string objecthandle_pythonic_typename(QPDFObjectHandle& h, std::string prefix = "pikepdf.");
std::string objecthandle_repr_typename_and_value(QPDFObjectHandle& h);
std::string objecthandle_repr(QPDFObjectHandle& h);

// From object_convert.cpp
py::object decimal_from_pdfobject(QPDFObjectHandle& h);
py::object objecthandle_decode(QPDFObjectHandle& h);
QPDFObjectHandle objecthandle_encode(py::handle handle);
std::vector<QPDFObjectHandle> array_builder(py::iterable iter);
std::map<std::string, QPDFObjectHandle> dict_builder(py::dict dict);
