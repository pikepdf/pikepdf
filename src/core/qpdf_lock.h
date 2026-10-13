// SPDX-FileCopyrightText: 2024 James R. Barlow
// SPDX-License-Identifier: MPL-2.0

#pragma once

// nanobind/nanobind.h includes Python.h, which must be included before any
// standard library headers. See note in pikepdf.h.
#include <nanobind/nanobind.h>

#include <algorithm>
#include <atomic>
#include <cstdint>
#include <functional>
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
    // Mirrors QPDF::setSuppressWarnings(), which qpdf offers no way to read
    // back. False means qpdf logs each warning as it is issued.
    std::atomic<bool> warnings_suppressed{true};

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
// Entries are shared: a thread that is locking a QPDF, or waiting for its
// lock, holds a reference to the entry, so the mutex outlives the QPDF if
// another thread destroys the document in the meantime.
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
        auto entry = std::make_shared<QpdfEntry>();
        std::lock_guard<std::mutex> guard(map_mutex_);
        map_[q] = std::move(entry);
    }

    // Remove q's entry. *entry* is the entry the caller locked: once q has
    // been deleted, its address may already have been reused by a new QPDF
    // with an entry of its own, which must be left alone.
    void unregister_qpdf(QPDF *q, QpdfEntry const *entry)
    {
        std::lock_guard<std::mutex> guard(map_mutex_);
        auto it = map_.find(q);
        if (it != map_.end() && it->second.get() == entry)
            map_.erase(it);
    }

    // The entry for q, kept alive for as long as the caller holds the result.
    // Use this to lock a QPDF that another thread might be destroying.
    std::shared_ptr<QpdfEntry> lookup_shared(QPDF *q)
    {
        if (!q)
            return nullptr;
        std::lock_guard<std::mutex> guard(map_mutex_);
        auto it = map_.find(q);
        return (it != map_.end()) ? it->second : nullptr;
    }

    // The entry for q as a borrowed pointer, valid only while q is known to
    // be alive: the caller holds q's lock, or a reference to the Pdf.
    QpdfEntry *lookup_entry(QPDF *q) { return lookup_shared(q).get(); }

    ReentrantFtMutex *lookup(QPDF *q)
    {
        auto *entry = lookup_entry(q);
        return entry ? &entry->mutex : nullptr;
    }

    // ~QPDF clears the owner of each of its objects and then destroys the
    // object's value. A thread that reads the cleared owner in between finds
    // no lock to take, and would go on to read a value that is being
    // destroyed. So destruction of a QPDF is bracketed by begin_teardown() and
    // end_teardown(), and a thread about to use an object that has no owner
    // calls wait_for_teardown() first. Teardowns are serialized by a
    // re-entrant mutex, so that code run by the destroying thread itself --
    // including the teardown of another QPDF -- passes straight through.
    //
    // begin_teardown() must be called with the QPDF's own lock held, before
    // any owner is cleared.
    void begin_teardown()
    {
        teardown_mutex_.lock();
        teardowns_.fetch_add(1);
    }

    void end_teardown()
    {
        teardowns_.fetch_sub(1);
        teardown_mutex_.unlock();
    }

    void wait_for_teardown()
    {
        if (teardowns_.load() != 0) {
            teardown_mutex_.lock();
            teardown_mutex_.unlock();
        }
    }

    QpdfRegistry(const QpdfRegistry &) = delete;
    QpdfRegistry &operator=(const QpdfRegistry &) = delete;

private:
    QpdfRegistry() = default;

    std::mutex map_mutex_;
    std::unordered_map<QPDF *, std::shared_ptr<QpdfEntry>> map_;
    ReentrantFtMutex teardown_mutex_;
    std::atomic<int> teardowns_{0};
};

// RAII guard that locks a single QPDF's mutex via the registry.
// Takes no lock if q is null or not registered (direct/unowned objects), but
// does wait for any QPDF that is being destroyed: see wait_for_teardown().
//
// The guard shares ownership of the registry entry. If another thread destroys
// the QPDF while this one waits for the lock, the wait ends once the QPDF is
// gone and the guard then holds the mutex of a dead entry, which is harmless:
// by then qpdf has disconnected the document's objects, and they are safe to
// use without a lock.
class QpdfLockGuard {
public:
    explicit QpdfLockGuard(QPDF *q) : entry_(QpdfRegistry::instance().lookup_shared(q))
    {
        if (entry_)
            entry_->mutex.lock();
        else
            QpdfRegistry::instance().wait_for_teardown();
    }

    ~QpdfLockGuard()
    {
        if (entry_)
            entry_->mutex.unlock();
    }

    // The registry entry of the locked QPDF, or nullptr for unowned objects.
    // Lets callers read the document's conversion mode without a second
    // registry lookup.
    QpdfEntry *entry() const { return entry_.get(); }

    QpdfLockGuard(const QpdfLockGuard &) = delete;
    QpdfLockGuard &operator=(const QpdfLockGuard &) = delete;

private:
    std::shared_ptr<QpdfEntry> entry_;
};

// RAII guard that locks two QPDF mutexes in consistent pointer order
// to prevent deadlocks. Used by copy_foreign(), with_same_owner_as(), etc.
class DualQpdfLockGuard {
public:
    DualQpdfLockGuard(QPDF *a, QPDF *b)
    {
        auto &reg = QpdfRegistry::instance();
        auto ea = reg.lookup_shared(a);
        auto eb = reg.lookup_shared(b);

        if (ea == eb) {
            // Same QPDF or both null -- single lock at most
            first_ = std::move(ea);
        } else if (!eb || (ea && std::less<QpdfEntry *>()(ea.get(), eb.get()))) {
            first_ = std::move(ea);
            second_ = std::move(eb);
        } else {
            first_ = std::move(eb);
            second_ = std::move(ea);
        }

        if (first_)
            first_->mutex.lock();
        if (second_)
            second_->mutex.lock();
        if (!first_ || (!second_ && a != b))
            reg.wait_for_teardown(); // At least one object has no owner
    }

    ~DualQpdfLockGuard()
    {
        if (second_)
            second_->mutex.unlock();
        if (first_)
            first_->mutex.unlock();
    }

    DualQpdfLockGuard(const DualQpdfLockGuard &) = delete;
    DualQpdfLockGuard &operator=(const DualQpdfLockGuard &) = delete;

private:
    // Shared for the same reason as QpdfLockGuard::entry_.
    std::shared_ptr<QpdfEntry> first_;
    std::shared_ptr<QpdfEntry> second_;
};

// RAII guard that locks any number of QPDFs, in the same consistent order as
// DualQpdfLockGuard. Null and unregistered pointers are skipped, and the same
// QPDF may be listed more than once.
class MultiQpdfLockGuard {
public:
    explicit MultiQpdfLockGuard(std::vector<QPDF *> const &qpdfs)
    {
        auto &reg = QpdfRegistry::instance();
        bool unowned = false;
        for (auto *q : qpdfs) {
            if (auto entry = reg.lookup_shared(q))
                entries_.push_back(std::move(entry));
            else
                unowned = true;
        }
        std::sort(entries_.begin(), entries_.end(), [](auto const &a, auto const &b) {
            return std::less<QpdfEntry *>()(a.get(), b.get());
        });
        entries_.erase(std::unique(entries_.begin(), entries_.end()), entries_.end());
        for (auto &entry : entries_)
            entry->mutex.lock();
        if (unowned)
            reg.wait_for_teardown();
    }

    ~MultiQpdfLockGuard()
    {
        for (auto it = entries_.rbegin(); it != entries_.rend(); ++it)
            (*it)->mutex.unlock();
    }

    MultiQpdfLockGuard(const MultiQpdfLockGuard &) = delete;
    MultiQpdfLockGuard &operator=(const MultiQpdfLockGuard &) = delete;

private:
    std::vector<std::shared_ptr<QpdfEntry>> entries_;
};

// From qpdf.cpp. Turn a QPDF into one that a pikepdf.Pdf can hold: registered
// for locking, and unregistered again when the last reference to it is dropped.
std::shared_ptr<QPDF> register_qpdf(
    std::unique_ptr<QPDF> owned, ConversionMode mode = ConversionMode::unset);
