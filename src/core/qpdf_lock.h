// SPDX-FileCopyrightText: 2024 James R. Barlow
// SPDX-License-Identifier: MPL-2.0

#pragma once

// nanobind/nanobind.h includes Python.h, which must be included before any
// standard library headers. See note in pikepdf.h.
#include <nanobind/nanobind.h>

#include <atomic>
#include <cstdint>
#include <memory>
#include <mutex>
#include <unordered_map>

#include <qpdf/QPDF.hh>

namespace py = nanobind;

// Re-entrant mutex wrapping nanobind's ft_mutex.
//
// Re-entrancy is required because:
//  - A method body locks the owning QPDF, then the return-value type caster
//    also resolves indirect objects on the same QPDF.
//  - Python augmented methods call multiple C++ methods in sequence, each of
//    which locks.
//  - TokenFilter/StreamParser callbacks from C++ into Python may call back
//    into pikepdf methods on the same QPDF.
//
// On GIL-enabled builds, ft_mutex is a no-op, so this entire mechanism
// compiles to near-zero cost.
class ReentrantFtMutex {
public:
    void lock()
    {
        auto tid = current_thread_id();
        if (owner_.load(std::memory_order_relaxed) == tid) {
            ++depth_;
            return;
        }
        mutex_.lock();
        owner_.store(tid, std::memory_order_relaxed);
        depth_ = 1;
    }

    void unlock()
    {
        if (--depth_ == 0) {
            owner_.store(0, std::memory_order_relaxed);
            mutex_.unlock();
        }
    }

private:
    static unsigned long current_thread_id()
    {
        return static_cast<unsigned long>(PyThread_get_thread_ident());
    }

    py::ft_mutex mutex_;
    std::atomic<unsigned long> owner_{0};
    int depth_{0};
};

// Per-Pdf object conversion mode. `unset` means "defer to the global setting".
enum class ConversionMode : int8_t { unset = 0, implicit = 1, explicit_ = 2 };

// Per-QPDF registry entry: the re-entrant mutex that serializes access to the
// QPDF, plus the document's conversion mode.
struct QpdfEntry {
    ReentrantFtMutex mutex;
    std::atomic<ConversionMode> conversion_mode{ConversionMode::unset};
};

// Global registry mapping QPDF* -> QpdfEntry*.
//
// Every QPDF instance created by pikepdf is registered here at construction
// and unregistered at destruction. Object methods look up their owning QPDF's
// entry via this registry.
//
// The registry's own map_mutex_ is a real std::mutex (not ft_mutex) because
// it protects the registry data structure itself, not a QPDF instance.
// It is held only briefly during register/unregister/lookup.
class QpdfRegistry {
public:
    static QpdfRegistry &instance()
    {
        static QpdfRegistry reg;
        return reg;
    }

    void register_qpdf(QPDF *q)
    {
        auto entry = std::make_unique<QpdfEntry>();
        std::lock_guard<std::mutex> guard(map_mutex_);
        map_[q] = std::move(entry);
    }

    void unregister_qpdf(QPDF *q)
    {
        std::lock_guard<std::mutex> guard(map_mutex_);
        map_.erase(q);
    }

    QpdfEntry *lookup_entry(QPDF *q)
    {
        if (!q)
            return nullptr;
        std::lock_guard<std::mutex> guard(map_mutex_);
        auto it = map_.find(q);
        return (it != map_.end()) ? it->second.get() : nullptr;
    }

    ReentrantFtMutex *lookup(QPDF *q)
    {
        auto *entry = lookup_entry(q);
        return entry ? &entry->mutex : nullptr;
    }

    QpdfRegistry(const QpdfRegistry &) = delete;
    QpdfRegistry &operator=(const QpdfRegistry &) = delete;

private:
    QpdfRegistry() = default;

    std::mutex map_mutex_;
    std::unordered_map<QPDF *, std::unique_ptr<QpdfEntry>> map_;
};

// RAII guard that locks a single QPDF's mutex via the registry.
// No-op if q is null or not registered (direct/unowned objects).
class QpdfLockGuard {
public:
    explicit QpdfLockGuard(QPDF *q)
        : entry_(q ? QpdfRegistry::instance().lookup_entry(q) : nullptr)
    {
        if (entry_)
            entry_->mutex.lock();
    }

    ~QpdfLockGuard()
    {
        if (entry_)
            entry_->mutex.unlock();
    }

    // The registry entry of the locked QPDF, or nullptr for unowned objects.
    // Lets callers read the document's conversion mode without a second
    // registry lookup.
    QpdfEntry *entry() const { return entry_; }

    QpdfLockGuard(const QpdfLockGuard &) = delete;
    QpdfLockGuard &operator=(const QpdfLockGuard &) = delete;

private:
    QpdfEntry *entry_;
};

// RAII guard that locks two QPDF mutexes in consistent pointer order
// to prevent deadlocks. Used by copy_foreign(), with_same_owner_as(), etc.
class DualQpdfLockGuard {
public:
    DualQpdfLockGuard(QPDF *a, QPDF *b)
    {
        auto &reg = QpdfRegistry::instance();
        auto *ma = a ? reg.lookup(a) : nullptr;
        auto *mb = b ? reg.lookup(b) : nullptr;

        if (ma == mb) {
            // Same QPDF or both null -- single lock at most
            first_ = ma;
            second_ = nullptr;
        } else if (!mb || (ma && ma < mb)) {
            first_ = ma;
            second_ = mb;
        } else {
            first_ = mb;
            second_ = ma;
        }

        if (first_)
            first_->lock();
        if (second_)
            second_->lock();
    }

    ~DualQpdfLockGuard()
    {
        if (second_)
            second_->unlock();
        if (first_)
            first_->unlock();
    }

    DualQpdfLockGuard(const DualQpdfLockGuard &) = delete;
    DualQpdfLockGuard &operator=(const DualQpdfLockGuard &) = delete;

private:
    ReentrantFtMutex *first_ = nullptr;
    ReentrantFtMutex *second_ = nullptr;
};
