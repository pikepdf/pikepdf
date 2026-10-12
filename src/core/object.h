// SPDX-FileCopyrightText: 2022 James R. Barlow
// SPDX-License-Identifier: MPL-2.0

#pragma once

// Declarations shared between object.cpp, object_arithmetic.cpp and
// object_methods.cpp, which together bind the QPDFObjectHandle ("Object")
// class, and object_list.cpp and object_map.cpp, which bind its containers.
// The binding is split across translation units so each one's nanobind
// template instantiation uses less peak compiler memory.

#include "locked_bindings.h"
#include "namepath.h"
#include "pikepdf.h"

#include <memory>
#include <optional>
#include <string>
#include <utility>

#include <qpdf/Buffer.hh>
#include <qpdf/Constants.h>
#include <qpdf/QPDFObjectHandle.hh>

// A Buffer owns a copy of the stream data it was made from, and the parser
// callbacks are an interface that Python implements. Neither holds Pdf state.
template <>
struct LockOwner<Buffer> : NoLock {};
template <>
struct LockOwner<QPDFObjectHandle::ParserCallbacks> : NoLock {};

// A binding parameter that accepts any Python object, and knows whether that
// object is a pikepdf Object.
//
// For a binding that treats an Object one way and every other value another:
// pikepdf.as_int() reads an Object, and returns a native int as it is.
// Declared where the parameter used to be py::object, it lets the code that
// takes the locks see the Object and lock its Pdf. Any other value reaches the
// body untouched, as an OpaqueObject would. If the body goes on to convert
// such a value to a PDF object, nothing that the value refers to is locked.
//
// The Python object is borrowed from the caller of the binding, which keeps
// its arguments alive for the length of the call. These bindings are among
// the most often called, and a reference of its own would cost them.
class ObjectOrValue {
public:
    ObjectOrValue() = default;
    explicit ObjectOrValue(py::handle value) : value_(value)
    {
        if (py::isinstance<QPDFObjectHandle>(value_))
            pdf_object_ = py::inst_ptr<QPDFObjectHandle>(value_);
    }

    // The Object, or nullptr if the value is anything else. It belongs to the
    // Python object.
    QPDFObjectHandle *pdf_object() const { return pdf_object_; }

    py::object object() const { return py::borrow<py::object>(value_); }
    py::handle handle() const { return value_; }

    // The Pdf to lock, or nullptr for an unowned Object or any other value
    QPDF *owner() const { return pdf_object_ ? pdf_object_->getOwningQPDF() : nullptr; }

private:
    py::handle value_;
    QPDFObjectHandle *pdf_object_ = nullptr;
};

template <>
struct LockOwner<ObjectOrValue> {
    static constexpr bool declared = true;
    static constexpr bool locks = true;
    static QPDF *of(ObjectOrValue const &value) { return value.owner(); }
};

namespace nanobind {
namespace detail {
template <>
struct type_caster<ObjectOrValue> {
    NB_TYPE_CASTER(ObjectOrValue, const_name("object"))

    bool from_python(handle src, uint8_t, cleanup_list *) noexcept
    {
        value = ObjectOrValue(src);
        return true;
    }
};
} // namespace detail
} // namespace nanobind

// Locks the Pdf of a value that was read out of a container, when that is not
// the container's own Pdf, which the binding already holds. A Dictionary or
// Array that has no owner can hold an object that belongs to a Pdf.
class ChildLockGuard {
public:
    ChildLockGuard(QPDFObjectHandle const &container, QPDFObjectHandle const &child)
    {
        QPDF *owner = child.getOwningQPDF();
        if (owner && owner != container.getOwningQPDF())
            guard_.emplace(owner);
    }

private:
    std::optional<QpdfLockGuard> guard_;
};

// Helpers defined in object.cpp and used by object_methods.cpp, and by the other
// binding translation units that need to read or write a PDF dictionary.
//
// A function whose name ends in _locked takes no lock: its caller holds the
// lock of the Pdf that owns the object, as a locked binding does for each of
// its arguments. So do the helpers that only the Object bindings call. Those
// that other translation units call lock the object's owner themselves.
std::string string_from_key(py::handle key);
py::str safe_decode(std::string const &s);
void ensure_array(QPDFObjectHandle h, const char *action);
size_t list_range_check(QPDFObjectHandle h, int index);
bool object_has_key(QPDFObjectHandle h, std::string const &key);
bool array_has_item(QPDFObjectHandle haystack, QPDFObjectHandle needle);
QPDFObjectHandle object_get_key(QPDFObjectHandle h, std::string const &key);
QPDFObjectHandle object_get_key_locked(QPDFObjectHandle &h, std::string const &key);
QPDF *live_owner(QPDFObjectHandle &h);
QPDFObjectHandle adopt_into(QPDF *owner, QPDFObjectHandle value);
void adopt_children_into(QPDF *owner, QPDFObjectHandle container);
QPDFObjectHandle adopt_key_on_read(QPDFObjectHandle holder,
    QPDFObjectHandle dict,
    std::string const &key,
    QPDFObjectHandle value);
QPDFObjectHandle adopt_item_on_read(
    QPDFObjectHandle array, int index, QPDFObjectHandle value);
void adopt_children_on_read(QPDFObjectHandle holder, QPDFObjectHandle container);
QPDFObjectHandle make_direct_indirect(QPDF *owner, QPDFObjectHandle direct);
void refuse_to_steal(QPDFObjectHandle &h, QPDF *target);
void refuse_foreign_indirect(QPDFObjectHandle const &h, QPDF *target);
void disconnect_from_owner(QPDF *owner, QPDFObjectHandle old);
void disconnect_detached(QPDFObjectHandle &container, QPDFObjectHandle old);
void object_set_key(
    QPDFObjectHandle h, std::string const &key, QPDFObjectHandle &value);
void object_set_key_locked(
    QPDFObjectHandle &h, std::string const &key, QPDFObjectHandle const &value);
void object_del_key(QPDFObjectHandle h, std::string const &key);
void object_del_key_locked(QPDFObjectHandle &h, std::string const &key);
QPDFObjectHandle traverse_namepath(
    QPDFObjectHandle h, NamePath const &path, bool for_set = false);
QPDFObjectHandle copy_object(QPDFObjectHandle &h);
std::shared_ptr<Buffer> get_stream_data(
    QPDFObjectHandle &h, qpdf_stream_decode_level_e decode_level);

// Python stand-in for a numeric Object, defined in object_arithmetic.cpp. The
// caller holds the lock on the object's owner.
py::object arithmetic_operand(QPDFObjectHandle &h, bool other_is_float);

// Number protocol of the Object binding, defined in object_arithmetic.cpp.
void init_object_arithmetic(locked_class_<QPDFObjectHandle> &object);
// _ObjectList and _ObjectMapping, defined in object_list.cpp and
// object_map.cpp.
void init_object_list(py::module_ &m);
void init_object_map(py::module_ &m);
// Second half of the Object binding, defined in object_methods.cpp.
void init_object_methods(locked_class_<QPDFObjectHandle> &object);
// Module-level pikepdf.as_int() and friends, defined in object_methods.cpp.
void init_typed_conversions(py::module_ &m);
