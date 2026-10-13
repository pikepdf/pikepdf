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
//  - A pointer or std::optional argument is locked when it holds a value.
//  - A constructor is registered with def_init or def_constructor, which keep
//    the uninitialized `self` away from the code that looks for owners.
//  - A parameter may not be a bare py::object or py::handle, since nothing
//    is known about what it refers to until the body has run. Declare what
//    the binding accepts instead: an EncodedObject for any value that
//    converts to a PDF object, an OpaqueObject for one the binding does
//    not treat as belonging to a Pdf, or a specific type such as py::callable.
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
#include <new>
#include <optional>
#include <stdexcept>
#include <string_view>
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
    static QPDF *of(T const &helper) { return const_cast<QPDF *>(&helper.getQPDF()); }
};

template <>
struct LockOwner<EncodedObject> {
    static constexpr bool declared = true;
    static constexpr bool locks = true;
    static QPDF *of(EncodedObject const &value) { return value.owner(); }
};

// A pointer that may be null, and an optional that may be empty
template <typename T>
struct LockOwner<T *, std::enable_if_t<LockOwner<std::remove_cv_t<T>>::locks>> {
    static constexpr bool declared = true;
    static constexpr bool locks = true;
    static QPDF *of(T *p)
    {
        return p ? LockOwner<std::remove_cv_t<T>>::of(*p) : nullptr;
    }
};

template <typename T>
struct LockOwner<std::optional<T>, std::enable_if_t<LockOwner<T>::locks>> {
    static constexpr bool declared = true;
    static constexpr bool locks = true;
    static QPDF *of(std::optional<T> const &value)
    {
        return value ? LockOwner<T>::of(*value) : nullptr;
    }
};

namespace locked_detail {

template <typename Arg>
inline constexpr bool arg_untyped =
    std::is_same_v<std::remove_cvref_t<Arg>, py::object> ||
    std::is_same_v<std::remove_cvref_t<Arg>, py::handle>;

template <typename Arg>
inline constexpr bool arg_locks = LockOwner<std::remove_cvref_t<Arg>>::locks;

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
        if (std::string_view(name) == "__init__")
            throw std::logic_error(
                "register a constructor with def_init or def_constructor");
        cls_.def(name, wrap(std::forward<F>(f)), extra...);
        return *this;
    }

    // Register __init__ from a factory: a callable that takes the arguments
    // of the constructor and returns the new T. The Pdfs of its arguments are
    // locked while it runs and while its result is moved into place.
    template <typename F, typename... Extra>
    locked_class_ &def_init(F &&factory, const Extra &...extra)
    {
        using Lambda = std::remove_cvref_t<F>;
        cls_.def("__init__",
            init_from(std::forward<F>(factory), &Lambda::operator()),
            extra...);
        return *this;
    }

    // Register __init__ as the constructor T(Args...).
    template <typename... Args, typename... Extra>
    locked_class_ &def_constructor(const Extra &...extra)
    {
        return def_init(
            [](Args... args) { return T(std::forward<Args>(args)...); }, extra...);
    }

    // Register __init__ as the constructor Alias(Args...), for a class that
    // Python can subclass through a trampoline: the Alias of py::class_, named
    // among Bases. A trampoline is built in place, because nanobind finds the
    // Python object it belongs to from its address, so it cannot be returned
    // by a factory as def_init requires. T may then be abstract.
    template <typename... Args, typename... Extra>
    locked_class_ &def_trampoline_constructor(const Extra &...extra)
    {
        using Alias = typename py::class_<T, Bases...>::Alias;
        static_assert(!std::is_same_v<T, Alias>,
            "This class has no trampoline: use def_constructor.");
        static_assert(!(locked_detail::arg_untyped<Args> || ...),
            "A constructor may not take py::object or py::handle.");
        cls_.def(
            "__init__",
            [](T *self, Args... args) {
                locked_detail::OwnersGuard<locked_detail::n_locking<Args...>> guard(
                    locked_detail::owners_of<Args...>(args...));
                new (static_cast<void *>(self)) Alias(std::forward<Args>(args)...);
            },
            extra...);
        return *this;
    }

    template <typename F, typename... Extra>
    locked_class_ &def_static(const char *name, F &&f, const Extra &...extra)
    {
        cls_.def_static(name, wrap(std::forward<F>(f)), extra...);
        return *this;
    }

    // Data members are read in place; a class with data members that are
    // bound this way holds plain values.
    template <typename D, typename... Extra>
    locked_class_ &def_ro(const char *name, D member, const Extra &...extra)
    {
        cls_.def_ro(name, member, extra...);
        return *this;
    }

    template <typename D, typename... Extra>
    locked_class_ &def_ro_static(const char *name, D *value, const Extra &...extra)
    {
        cls_.def_ro_static(name, value, extra...);
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

    // A member function, which may belong to a base class of T, is bound as
    // a method of T.
    template <typename R, typename C, typename... Args>
    static auto wrap(R (C::*f)(Args...))
    {
        return locked_detail::LockedFunction<R (C::*)(Args...), R, T &, Args...>{f};
    }

    template <typename R, typename C, typename... Args>
    static auto wrap(R (C::*f)(Args...) const)
    {
        return locked_detail::LockedFunction<R (C::*)(Args...) const, R, T &, Args...>{
            f};
    }

    template <typename F, typename R, typename... Args>
    static auto init_from(F factory, R (F::*)(Args...) const)
    {
        static_assert(!(locked_detail::arg_untyped<Args> || ...),
            "A constructor may not take py::object or py::handle.");
        return [factory = std::move(factory)](T *self, Args... args) {
            locked_detail::OwnersGuard<locked_detail::n_locking<Args...>> guard(
                locked_detail::owners_of<Args...>(args...));
            new (self) T(factory(std::forward<Args>(args)...));
        };
    }

    template <typename F>
    static F wrap(Unlocked<F> f)
    {
        return std::move(f.f);
    }

    py::class_<T, Bases...> cls_;
};

// A module whose functions go through locked(), as locked_class_ does for the
// methods of a class.
class locked_module_ {
public:
    explicit locked_module_(py::module_ &m) : m_(m) {}

    template <typename F, typename... Extra>
    locked_module_ &def(const char *name, F &&f, const Extra &...extra)
    {
        m_.def(name, wrap(std::forward<F>(f)), extra...);
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

    py::module_ &m_;
};

// A shared_ptr argument, which may be null, is locked as what it points to.
// Pdf.pages takes its Pdf this way, since the PageList it returns shares
// ownership of the QPDF.
template <typename T>
struct LockOwner<std::shared_ptr<T>, std::enable_if_t<LockOwner<T>::locks>> {
    static constexpr bool declared = true;
    static constexpr bool locks = true;
    static QPDF *of(std::shared_ptr<T> const &p)
    {
        return p ? LockOwner<T>::of(*p) : nullptr;
    }
};

namespace locked_detail {
static_assert(arg_locks<std::shared_ptr<QPDF>>);
static_assert(arg_locks<std::shared_ptr<QPDF> const &>);
static_assert(!arg_locks<std::shared_ptr<int>>);
} // namespace locked_detail

// The rules above, checked where they are stated.
namespace locked_detail {
struct Undeclared {};
static_assert(!LockOwner<Undeclared>::declared);
static_assert(arg_locks<QPDF &> && arg_locks<QPDFObjectHandle const &>);
static_assert(arg_locks<QPDFObjectHandle>);
static_assert(arg_locks<QPDFObjectHandle *> && arg_locks<QPDF const *>);
static_assert(arg_locks<std::optional<QPDFObjectHandle>>);
static_assert(!arg_locks<int *> && !arg_locks<std::optional<int>>);
static_assert(!arg_locks<bool> && arg_locks<EncodedObject const &>);
static_assert(arg_untyped<py::object> && arg_untyped<py::handle const &>);
static_assert(!arg_untyped<OpaqueObject> && !arg_locks<OpaqueObject const &>);
static_assert(!arg_untyped<py::callable> && !arg_untyped<QPDFObjectHandle>);
static_assert(n_locking<QPDF &, bool, QPDFObjectHandle> == 2);
} // namespace locked_detail
