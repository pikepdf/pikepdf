// SPDX-FileCopyrightText: 2026 James R. Barlow
// SPDX-License-Identifier: MPL-2.0

#pragma once

// Bindings that hold the lock of every Pdf they touch, checked at compile time.
//
// A binding registered through locked_class_ is wrapped so that, before it
// runs, it locks the Pdf that owns each of its arguments. Which Pdf owns an
// argument is declared once per C++ type, by specializing LockOwner. A class
// cannot be bound with locked_class_ until its type has made that declaration,
// so "this class was never locked" is a compile error and not something to
// find by review or under ThreadSanitizer.
//
// What this does and does not establish:
//
//  - Every argument of a type that declares an owner has its Pdf locked for
//    the whole call. Calls that involve several Pdfs lock them all, in the
//    registry's consistent order, so two such calls cannot deadlock.
//  - Pointer arguments are not examined. The only ones in use are the
//    uninitialized `self` of an __init__ implemented with placement new.
//  - A parameter may not be a bare py::object or py::handle, since nothing
//    is known about what it refers to until the body has run. Declare what
//    the binding accepts instead: an EncodedObject for any value that
//    converts to a PDF object, or a specific type such as py::callable.
//    An EncodedObject built from a Python container can still hold objects
//    of another Pdf below its top level; that Pdf is not locked.
//  - The lock is released when the body returns. A return value that keeps
//    reading the Pdf afterwards, such as a lazy iterator over a qpdf
//    container, is not protected: return a snapshot instead.
//
// A binding that must not be wrapped is registered as unlocked(f), which
// states the exception where a reader will see it.

#include "pikepdf.h"
#include "qpdf_lock.h"

#include <array>
#include <cstddef>
#include <functional>
#include <type_traits>
#include <utility>

#include <qpdf/QPDF.hh>
#include <qpdf/QPDFDocumentHelper.hh>
#include <qpdf/QPDFObjectHandle.hh>
#include <qpdf/QPDFObjectHelper.hh>

// How to find the Pdf to lock for a value of type T.
//
// The primary template is what an undeclared type gets: it takes no lock when
// passed as an argument, and cannot be the class of a locked_class_.
template <typename T, typename Enable = void>
struct LockOwner {
    static constexpr bool declared = false;
    static constexpr bool locks = false;
};

// Base for the LockOwner of a type that holds no Pdf state, such as a matrix.
struct NoLock {
    static constexpr bool declared = true;
    static constexpr bool locks = false;
};

template <>
struct LockOwner<QPDF> {
    static constexpr bool declared = true;
    static constexpr bool locks = true;
    static QPDF *of(QPDF const &q) { return const_cast<QPDF *>(&q); }
};

template <>
struct LockOwner<QPDFObjectHandle> {
    static constexpr bool declared = true;
    static constexpr bool locks = true;
    static QPDF *of(QPDFObjectHandle const &h) { return h.getOwningQPDF(); }
};

// Page, annotation, name tree, number tree, file spec and form field helpers
template <typename T>
struct LockOwner<T, std::enable_if_t<std::is_base_of_v<QPDFObjectHelper, T>>> {
    static constexpr bool declared = true;
    static constexpr bool locks = true;
    static QPDF *of(T const &helper)
    {
        return helper.getObjectHandle().getOwningQPDF();
    }
};

// Interactive form, embedded file, outline and page label document helpers
template <typename T>
struct LockOwner<T, std::enable_if_t<std::is_base_of_v<QPDFDocumentHelper, T>>> {
    static constexpr bool declared = true;
    static constexpr bool locks = true;
    static QPDF *of(T const &helper) { return &helper.getQPDF(); }
};

template <>
struct LockOwner<EncodedObject> {
    static constexpr bool declared = true;
    static constexpr bool locks = true;
    static QPDF *of(EncodedObject const &value) { return value.owner(); }
};

namespace locked_detail {

template <typename Arg>
inline constexpr bool arg_untyped =
    std::is_same_v<std::remove_cvref_t<Arg>, py::object> ||
    std::is_same_v<std::remove_cvref_t<Arg>, py::handle>;

template <typename Arg>
inline constexpr bool arg_locks = !std::is_pointer_v<std::remove_reference_t<Arg>> &&
                                  LockOwner<std::remove_cvref_t<Arg>>::locks;

template <typename... Args>
inline constexpr std::size_t n_locking = (std::size_t{0} + ... + arg_locks<Args>);

template <typename... Args>
std::array<QPDF *, n_locking<Args...>> owners_of(std::remove_reference_t<Args> &...args)
{
    std::array<QPDF *, n_locking<Args...>> owners{};
    [[maybe_unused]] std::size_t n = 0;
    [[maybe_unused]] auto add = [&]<typename Arg>(std::remove_reference_t<Arg> &arg) {
        if constexpr (arg_locks<Arg>)
            owners[n++] = LockOwner<std::remove_cvref_t<Arg>>::of(arg);
    };
    (add.template operator()<Args>(args), ...);
    return owners;
}

// Holds the locks of N Pdfs. The common cases of one and two avoid the
// allocation that the general guard needs.
template <std::size_t N>
class OwnersGuard {
public:
    explicit OwnersGuard(std::array<QPDF *, N> const &owners)
        : guard_(std::vector<QPDF *>(owners.begin(), owners.end()))
    {
    }

private:
    MultiQpdfLockGuard guard_;
};

template <>
class OwnersGuard<0> {
public:
    explicit OwnersGuard(std::array<QPDF *, 0> const &) {}
};

template <>
class OwnersGuard<1> {
public:
    explicit OwnersGuard(std::array<QPDF *, 1> const &owners) : guard_(owners[0]) {}

private:
    QpdfLockGuard guard_;
};

template <>
class OwnersGuard<2> {
public:
    explicit OwnersGuard(std::array<QPDF *, 2> const &owners)
        : guard_(owners[0], owners[1])
    {
    }

private:
    DualQpdfLockGuard guard_;
};

// A callable with the signature R(Args...) that nanobind sees in place of f.
template <typename F, typename R, typename... Args>
struct LockedFunction {
    static_assert(!(arg_untyped<Args> || ...),
        "A locked binding may not take py::object or py::handle. Take an "
        "EncodedObject or a specific type, or register it with unlocked() "
        "if it does not use a Pdf.");

    F f;

    R operator()(Args... args) const
    {
        OwnersGuard<n_locking<Args...>> guard(owners_of<Args...>(args...));
        return std::invoke(f, std::forward<Args>(args)...);
    }
};

template <typename F, typename R, typename... Args>
LockedFunction<F, R, Args...> lock_lambda(F f, R (F::*)(Args...) const)
{
    return {std::move(f)};
}

template <typename F, typename R, typename... Args>
LockedFunction<F, R, Args...> lock_lambda(F f, R (F::*)(Args...))
{
    return {std::move(f)};
}

} // namespace locked_detail

// Wrap a callable so that it locks the Pdf of each of its arguments.

template <typename R, typename... Args>
auto locked(R (*f)(Args...))
{
    return locked_detail::LockedFunction<R (*)(Args...), R, Args...>{f};
}

template <typename R, typename C, typename... Args>
auto locked(R (C::*f)(Args...))
{
    return locked_detail::LockedFunction<R (C::*)(Args...), R, C &, Args...>{f};
}

template <typename R, typename C, typename... Args>
auto locked(R (C::*f)(Args...) const)
{
    return locked_detail::LockedFunction<R (C::*)(Args...) const, R, C &, Args...>{f};
}

template <typename F>
    requires requires { &std::remove_cvref_t<F>::operator(); }
auto locked(F &&f)
{
    using Lambda = std::remove_cvref_t<F>;
    return locked_detail::lock_lambda<Lambda>(std::forward<F>(f), &Lambda::operator());
}

// Marks a callable that locked_class_ registers as it is, without locking.
template <typename F>
struct Unlocked {
    F f;
};

template <typename F>
Unlocked<std::remove_cvref_t<F>> unlocked(F &&f)
{
    return {std::forward<F>(f)};
}

// A py::class_ whose every binding goes through locked().
template <typename T, typename... Bases>
class locked_class_ {
    static_assert(LockOwner<T>::declared,
        "Specialize LockOwner for this type before binding it: either say "
        "which Pdf owns it, or derive from NoLock if it holds no Pdf state.");

public:
    template <typename... Extra>
    locked_class_(py::handle scope, const char *name, const Extra &...extra)
        : cls_(scope, name, extra...)
    {
    }

    template <typename F, typename... Extra>
    locked_class_ &def(const char *name, F &&f, const Extra &...extra)
    {
        cls_.def(name, wrap(std::forward<F>(f)), extra...);
        return *this;
    }

    template <typename F, typename... Extra>
    locked_class_ &def_static(const char *name, F &&f, const Extra &...extra)
    {
        cls_.def_static(name, wrap(std::forward<F>(f)), extra...);
        return *this;
    }

    template <typename Getter, typename... Extra>
    locked_class_ &def_prop_ro(const char *name, Getter &&getter, const Extra &...extra)
    {
        cls_.def_prop_ro(name, wrap(std::forward<Getter>(getter)), extra...);
        return *this;
    }

    template <typename Getter, typename Setter, typename... Extra>
    locked_class_ &def_prop_rw(
        const char *name, Getter &&getter, Setter &&setter, const Extra &...extra)
    {
        cls_.def_prop_rw(name,
            wrap(std::forward<Getter>(getter)),
            wrap(std::forward<Setter>(setter)),
            extra...);
        return *this;
    }

private:
    template <typename F>
    static auto wrap(F &&f)
    {
        return locked(std::forward<F>(f));
    }

    template <typename F>
    static F wrap(Unlocked<F> f)
    {
        return std::move(f.f);
    }

    py::class_<T, Bases...> cls_;
};

// The rules above, checked where they are stated.
namespace locked_detail {
struct Undeclared {};
static_assert(!LockOwner<Undeclared>::declared);
static_assert(arg_locks<QPDF &> && arg_locks<QPDFObjectHandle const &>);
static_assert(arg_locks<QPDFObjectHandle>);
static_assert(!arg_locks<QPDFObjectHandle *>);
static_assert(!arg_locks<bool> && arg_locks<EncodedObject const &>);
static_assert(arg_untyped<py::object> && arg_untyped<py::handle const &>);
static_assert(!arg_untyped<py::callable> && !arg_untyped<QPDFObjectHandle>);
static_assert(n_locking<QPDF &, bool, QPDFObjectHandle> == 2);
} // namespace locked_detail
