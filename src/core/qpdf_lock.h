// SPDX-FileCopyrightText: 2024 James R. Barlow
// SPDX-License-Identifier: MPL-2.0

#pragma once

#include <atomic>
#include <memory>
#include <mutex>
#include <unordered_map>

#include <nanobind/nanobind.h>
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

// Global registry mapping QPDF* -> ReentrantFtMutex*.
//
// Every QPDF instance created by pikepdf is registered here at construction
// and unregistered at destruction. Object methods look up their owning QPDF's
// mutex via this registry.
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
        auto m = std::make_unique<ReentrantFtMutex>();
        std::lock_guard<std::mutex> guard(map_mutex_);
        map_[q] = std::move(m);
    }

    void unregister_qpdf(QPDF *q)
    {
        std::lock_guard<std::mutex> guard(map_mutex_);
        map_.erase(q);
    }

    ReentrantFtMutex *lookup(QPDF *q)
    {
        if (!q)
            return nullptr;
        std::lock_guard<std::mutex> guard(map_mutex_);
        auto it = map_.find(q);
        return (it != map_.end()) ? it->second.get() : nullptr;
    }

    QpdfRegistry(const QpdfRegistry &) = delete;
    QpdfRegistry &operator=(const QpdfRegistry &) = delete;

private:
    QpdfRegistry() = default;

    std::mutex map_mutex_;
    std::unordered_map<QPDF *, std::unique_ptr<ReentrantFtMutex>> map_;
};

// RAII guard that locks a single QPDF's mutex via the registry.
// No-op if q is null or not registered (direct/unowned objects).
class QpdfLockGuard {
public:
    explicit QpdfLockGuard(QPDF *q)
        : mutex_(q ? QpdfRegistry::instance().lookup(q) : nullptr)
    {
        if (mutex_)
            mutex_->lock();
    }

    ~QpdfLockGuard()
    {
        if (mutex_)
            mutex_->unlock();
    }

    QpdfLockGuard(const QpdfLockGuard &) = delete;
    QpdfLockGuard &operator=(const QpdfLockGuard &) = delete;

private:
    ReentrantFtMutex *mutex_;
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
