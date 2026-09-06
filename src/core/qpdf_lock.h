// SPDX-FileCopyrightText: 2024 James R. Barlow
// SPDX-License-Identifier: MPL-2.0

#pragma once

// nanobind/nanobind.h includes Python.h, which must be included before any
// standard library headers. See note in pikepdf.h.
#include <nanobind/nanobind.h>

#include <algorithm>
#include <atomic>
#include <cstdint>
#include <memory>
#include <mutex>
#include <unordered_map>
#include <vector>

#include <qpdf/QPDF.hh>
#include <qpdf/QPDFObjectHandle.hh>

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
// QPDF, the document's conversion mode, and the set of direct objects that
// pikepdf tagged with this document as their owner.
//
// qpdf records an object's owning QPDF as a raw pointer, and ~QPDF only clears
// that pointer on objects still reachable from its object cache. A direct
// object that pikepdf adopted and that was later detached from the object
// graph -- or that Python still holds a reference to -- would otherwise keep a
// dangling pointer into freed memory, and qpdf dereferences the pointer
// internally before pikepdf gets a chance to check it. So every adopted object
// is remembered here as a weak_ptr (which does not keep it alive) and
// disconnected just before the QPDF is deleted.
struct QpdfEntry {
    ReentrantFtMutex mutex;
    std::atomic<ConversionMode> conversion_mode{ConversionMode::unset};

    // Remember an object that was just tagged with this document as its owner.
    void record_adopted(std::shared_ptr<QPDFObject> const &obj)
    {
        if (!obj)
            return; // LCOV_EXCL_LINE
        std::lock_guard<std::mutex> guard(adopted_mutex_);
        adopted_.emplace_back(obj);
        // Amortised pruning: the vector is compacted once it has grown to
        // twice the number of live entries measured at the previous prune,
        // so pruning costs O(1) per insertion on average.
        size_t threshold = std::max<size_t>(64, live_at_last_prune_ * 2);
        if (adopted_.size() > threshold) {
            adopted_.erase(
                std::remove_if(adopted_.begin(),
                    adopted_.end(),
                    [](std::weak_ptr<QPDFObject> const &w) { return w.expired(); }),
                adopted_.end());
            live_at_last_prune_ = adopted_.size();
        }
    }

    // Clear this document from every object it adopted that is still alive
    // and still owned by it. Called from the QPDF deleter while the QPDF is
    // still valid. The object's value is left intact; only the owner
    // association is removed. An object that was detached from this document
    // and adopted by another remains on this list, so the owner check keeps
    // the other document's ownership intact.
    void disconnect_adopted(QPDF *self)
    {
        std::lock_guard<std::mutex> guard(adopted_mutex_);
        for (auto &weak : adopted_) {
            if (auto sp = weak.lock()) {
                QPDFObjectHandle h(sp);
                if (h.getOwningQPDF() == self)
                    h.setObjectDescription(nullptr, "");
            }
        }
        adopted_.clear();
        live_at_last_prune_ = 0;
    }

private:
    std::mutex adopted_mutex_;
    std::vector<std::weak_ptr<QPDFObject>> adopted_;
    size_t live_at_last_prune_ = 0;
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
