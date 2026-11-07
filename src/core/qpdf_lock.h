// SPDX-FileCopyrightText: 2024 James R. Barlow
// SPDX-License-Identifier: MPL-2.0

#pragma once

// nanobind/nanobind.h includes Python.h, which must be included before any
// standard library headers. See note in pikepdf.h.
#include <nanobind/nanobind.h>

#include <algorithm>
#include <atomic>
#include <condition_variable>
#include <cstdint>
#include <functional>
#include <initializer_list>
#include <memory>
#include <mutex>
#include <new>
#include <optional>
#include <stdexcept>
#include <unordered_map>
#include <unordered_set>
#include <vector>

#include <qpdf/QPDF.hh>
#include <qpdf/QPDFObjectHandle.hh>

namespace py = nanobind;

// Raised in a thread that would otherwise wait for ever: see
// ReentrantFtMutex::lock(). Reaches Python as a RuntimeError.
class DeadlockError : public std::runtime_error {
public:
    DeadlockError()
        : std::runtime_error(
              "Deadlock avoided: this thread holds the lock of one Pdf and needs "
              "the lock of another, which is held by a thread that is waiting "
              "for the first. Code that runs while a Pdf is locked, such as a "
              "callback or the body of a `with pdf.lock()` block, may only use "
              "that Pdf.")
    {
    }
};

// Re-entrant mutex that serializes access to one QPDF.
//
// Re-entrancy is required because:
//  - A method body locks the owning QPDF, then the return-value type caster
//    also resolves indirect objects on the same QPDF.
//  - Python augmented methods call multiple C++ methods in sequence, each of
//    which locks.
//  - TokenFilter/StreamParser callbacks from C++ into Python may call back
//    into pikepdf methods on the same QPDF.
//
// The lock is real on every build. The GIL alone does not serialize use of a
// QPDF: it changes hands whenever Python code runs, and pikepdf runs Python in
// the middle of qpdf operations -- callbacks, the methods of a Python stream,
// logging, and finalizers run by a garbage collection -- and releases it
// outright while it writes a file. Another thread could then enter the same
// QPDF part way through.
//
// The lock is owner_, the identifier of the thread that holds it, and depth_.
// On a GIL build only the thread holding the GIL reads or writes owner_, so
// taking a free lock is a few plain loads and stores; on a free-threaded
// build it is taken with a compare-and-swap. A thread that finds it held
// detaches from the interpreter (giving up the GIL, if there is one) and
// sleeps until it is released.
//
// A released lock goes to whichever thread asks for it next, which is
// usually the thread that just released it, still running. A fair lock that
// hands itself to the longest waiter, as PyMutex does once a waiter has
// waited for a millisecond, forms a convoy when threads take the lock often:
// every handover waits for a sleeping thread to be scheduled, which on a busy
// machine can take far longer than the work done under the lock.
//
// Every lock() and unlock() must be made by a thread that holds the GIL (or,
// on a free-threaded build, is attached to the interpreter).
//
// A single call that needs several Pdfs locks them in a fixed order, but a
// thread can also come to hold one lock and then ask for another: from a
// callback that pikepdf runs while a Pdf is locked, or from nested
// `with pdf.lock()` blocks. Two threads doing so in opposite orders would wait
// for each other for ever. lock() notices this and throws DeadlockError in the
// thread that would have completed the cycle; as that thread unwinds it gives
// up the lock it holds, and the other thread carries on.
class ReentrantFtMutex {
public:
    // Take the lock, or throw DeadlockError if waiting for it could never end.
    void lock() { lock_impl(true); }

    // Take the lock, waiting for as long as it takes. For code that cannot
    // throw, such as destructors and noexcept type casters.
    void lock_unchecked() { lock_impl(false); }

    void unlock()
    {
        if (--depth_ == 0) {
            owner_.store(0, sync_order);
            // On a free-threaded build, the store above and this load pair
            // with the waiter's increment of waiters_ and its attempt to take
            // the lock: either the waiter sees the lock free, or this sees
            // the waiter.
            if (waiters_.load(sync_order) > 0) {
                // Taking sleep_mutex_ orders this release after a waiter's
                // check of owner_, so the waiter cannot miss the notification.
                {
                    std::lock_guard<std::mutex> sleep(sleep_mutex_);
                }
                released_.notify_all();
            }
        }
    }

    // Take the lock if that needs no wait, and say whether it was taken.
    bool try_lock()
    {
        auto tid = current_thread_id();
        if (owner_.load(std::memory_order_relaxed) == tid) {
            ++depth_;
            return true;
        }
        if (!try_take(tid))
            return false;
        depth_ = 1;
        return true;
    }

    // Give up the lock entirely, however many times this thread has taken it,
    // and return that number for resume(). Returns 0 if this thread does not
    // hold the lock.
    int suspend()
    {
        if (owner_.load(std::memory_order_relaxed) != current_thread_id())
            return 0;
        int depth = depth_;
        depth_ = 1;
        unlock();
        return depth;
    }

    // Take the lock back after suspend(). Waits without the check for a
    // deadlock, since the caller's own guards expect to find the lock held.
    void resume(int depth)
    {
        if (depth == 0)
            return;
        lock_unchecked();
        depth_ = depth;
    }

private:
    void lock_impl(bool check)
    {
        auto tid = current_thread_id();
        if (owner_.load(std::memory_order_relaxed) == tid) {
            ++depth_;
            return;
        }
        if (!try_take(tid)) {
            // Another thread holds the lock, so this one is about to wait.
            // An uncontended lock never reaches this, and pays nothing for it.
            Waiting waiting(tid, this, check);
            waiters_.fetch_add(1, sync_order);
            // Another thread may take the lock between this one waking and
            // trying to take it, so try again each time.
            while (!try_take(tid)) {
                py::gil_scoped_release release;
                std::unique_lock<std::mutex> sleep(sleep_mutex_);
                released_.wait(sleep, [this] { return owner_.load(sync_order) == 0; });
                // sleep_mutex_ is given up before this thread attaches to the
                // interpreter again, so an attached thread -- one holding the
                // GIL, or one a garbage collection is waiting for -- never
                // waits for sleep_mutex_'s holder.
            }
            waiters_.fetch_sub(1, std::memory_order_relaxed);
        }
        depth_ = 1;
    }

    // Take the lock if it is free.
    bool try_take(unsigned long tid)
    {
#if defined(NB_FREE_THREADED)
        unsigned long expected = 0;
        return owner_.compare_exchange_strong(
            expected, tid, sync_order, std::memory_order_relaxed);
#else
        // The GIL makes the check and the store one step.
        if (owner_.load(std::memory_order_relaxed) != 0)
            return false;
        owner_.store(tid, std::memory_order_relaxed);
        return true;
#endif
    }

    // Records, for as long as it exists, that a thread is waiting for a mutex.
    //
    // Every waiting thread is recorded in one table, under one mutex. A thread
    // about to wait follows the chain from the mutex it wants to the thread
    // that holds it, to the mutex that thread is waiting for, and so on. If
    // the chain comes back to the thread itself, none of the threads on it
    // could ever move. Each of them recorded itself before it began to wait,
    // so the last to arrive finds the whole cycle.
    //
    // A thread's entry outlives its wait by a moment, since it is removed
    // after the mutex has been acquired. Such an entry cannot produce a false
    // report: the mutex it names is by then owned by that same thread or by
    // nobody, never by the thread doing the check.
    class Waiting {
    public:
        Waiting(unsigned long tid, ReentrantFtMutex *wanted, bool check) : tid_(tid)
        {
            std::lock_guard<std::mutex> guard(table_mutex());
            if (check) {
                auto &waiting = table();
                ReentrantFtMutex *m = wanted;
                // The bound only guards against following stale entries
                // round a loop that does not include this thread.
                for (int steps = 0; steps < 64; ++steps) {
                    auto holder = m->owner_.load(std::memory_order_relaxed);
                    if (holder == 0)
                        break;
                    if (holder == tid)
                        throw DeadlockError();
                    auto it = waiting.find(holder);
                    if (it == waiting.end())
                        break;
                    m = it->second;
                }
            }
            table()[tid] = wanted;
        }

        ~Waiting()
        {
            std::lock_guard<std::mutex> guard(table_mutex());
            table().erase(tid_);
        }

        Waiting(const Waiting &) = delete;
        Waiting &operator=(const Waiting &) = delete;

    private:
        static std::mutex &table_mutex()
        {
            static std::mutex m;
            return m;
        }

        static std::unordered_map<unsigned long, ReentrantFtMutex *> &table()
        {
            static std::unordered_map<unsigned long, ReentrantFtMutex *> t;
            return t;
        }

        unsigned long tid_;
    };

    static unsigned long current_thread_id()
    {
        return static_cast<unsigned long>(PyThread_get_thread_ident());
    }

#if defined(NB_FREE_THREADED)
    static constexpr auto sync_order = std::memory_order_seq_cst;
#else
    // The GIL orders everything but a sleeping thread's check of owner_, and
    // sleep_mutex_ orders that.
    static constexpr auto sync_order = std::memory_order_relaxed;
#endif

    // Used only to sleep while another thread holds the lock: the lock itself
    // is owner_.
    std::mutex sleep_mutex_;
    std::condition_variable released_;
    // The number of threads waiting for the lock, so that unlock() notifies
    // only when there is someone to wake.
    std::atomic<int> waiters_{0};
    // The thread holding the lock, or 0. Read and written only with the GIL
    // held on a GIL build, but atomic because a sleeping thread reads it in
    // released_'s predicate.
    std::atomic<unsigned long> owner_{0};
    // Written only by the thread holding the lock.
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
// The registry's own map_mutex_ is a real std::mutex (not a ReentrantFtMutex) because
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
        teardown_mutex_.lock_unchecked();
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
            teardown_mutex_.lock_unchecked();
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

// Objects that belong to no Pdf.
//
// A Dictionary or Array built in Python belongs to no Pdf until it is added to
// one, so there is no Pdf lock to protect it. All such containers share one
// lock instead, unowned_mutex(). Scalars need no lock, since they cannot be
// changed. Threads that each build containers of their own contend for this
// lock, which is one reason to add a container to its Pdf straight away.
//
// The guards below take it when they are given unowned_owner(), a stand-in
// owner that lock_target() returns for such a container. It is always taken
// after any Pdf lock, never before: code that holds it does not go on to take
// a Pdf lock. Pdf locks are taken in the registry's order, so this rule makes
// the order of every lock fixed.
//
// An object's owner changes when it is added to a Pdf or taken out of one, and
// pikepdf holds both the Pdf's lock and this one when it does so. A thread that
// has locked an object's owner and finds the owner unchanged therefore knows
// that it cannot change until the lock is released. The guards that take an
// object, rather than a QPDF, read its owner again once they hold the lock and
// start over if it changed.

inline ReentrantFtMutex &unowned_mutex()
{
    static ReentrantFtMutex mutex;
    return mutex;
}

// Never dereferenced: only compared.
inline QPDF *unowned_owner()
{
    static char tag;
    return reinterpret_cast<QPDF *>(&tag);
}

// What to lock to use h: its Pdf, unowned_owner() for a container that belongs
// to no Pdf, or nullptr for a scalar that belongs to no Pdf.
inline QPDF *lock_target(QPDFObjectHandle const &h)
{
    if (QPDF *owner = h.getOwningQPDF())
        return owner;
    if (h.isDictionary() || h.isArray())
        return unowned_owner();
    return nullptr;
}

// Holds unowned_mutex() for a guard, which declares it after its Pdf entries,
// so that it is released first.
class UnownedLockHold {
public:
    UnownedLockHold() = default;
    ~UnownedLockHold() { release(); }

    void lock(bool check)
    {
        if (check)
            unowned_mutex().lock();
        else
            unowned_mutex().lock_unchecked();
        held_ = true;
    }

    // Take the lock unless this already holds it.
    void ensure()
    {
        if (!held_)
            lock(true);
    }

    void release()
    {
        if (held_)
            unowned_mutex().unlock();
        held_ = false;
    }

    UnownedLockHold(const UnownedLockHold &) = delete;
    UnownedLockHold &operator=(const UnownedLockHold &) = delete;

private:
    bool held_ = false;
};

// RAII guard that locks a single QPDF's mutex via the registry.
// For unowned_owner() it takes unowned_mutex(). For null or an unregistered
// QPDF it takes no lock. Either way, an object with no owner waits for any
// QPDF that is being destroyed: see wait_for_teardown().
//
// The guard shares ownership of the registry entry. If another thread destroys
// the QPDF while this one waits for the lock, the wait ends once the QPDF is
// gone and the guard then holds the mutex of a dead entry, which is harmless:
// by then qpdf has disconnected the document's objects, and they are safe to
// use without a lock.
class QpdfLockGuard {
public:
    explicit QpdfLockGuard(QPDF *q) { acquire(q, true); }

    // For code that cannot throw: waits without checking for a deadlock.
    QpdfLockGuard(QPDF *q, std::nothrow_t) noexcept { acquire(q, false); }

    // Lock what h needs, checking afterwards that h's owner did not change
    // while this thread waited.
    explicit QpdfLockGuard(QPDFObjectHandle const &h) { acquire_for(h, true); }

    QpdfLockGuard(QPDFObjectHandle const &h, std::nothrow_t) noexcept
    {
        acquire_for(h, false);
    }

    // Lock q from code that may hold unowned_mutex(), which must not be held
    // while waiting for a Pdf lock. If q's lock is not free at once,
    // unowned_mutex() is set aside while this thread waits for it, then taken
    // back, so the locks end up taken in the usual order. Only for a caller
    // that has finished with the objects unowned_mutex() protects, since
    // another thread may change them in the meantime.
    struct AfterUnowned {};
    QpdfLockGuard(QPDF *q, AfterUnowned) { acquire_after_unowned(q, true); }

    QpdfLockGuard(QPDF *q, AfterUnowned, std::nothrow_t) noexcept
    {
        acquire_after_unowned(q, false);
    }

    ~QpdfLockGuard() { release(); }

    // The registry entry of the locked QPDF, or nullptr for unowned objects.
    // Lets callers read the document's conversion mode without a second
    // registry lookup.
    QpdfEntry *entry() const { return entry_.get(); }

    QpdfLockGuard(const QpdfLockGuard &) = delete;
    QpdfLockGuard &operator=(const QpdfLockGuard &) = delete;

private:
    void acquire(QPDF *q, bool check)
    {
        auto &reg = QpdfRegistry::instance();
        if (q != unowned_owner())
            entry_ = reg.lookup_shared(q);
        if (entry_) {
            if (check)
                entry_->mutex.lock();
            else
                entry_->mutex.lock_unchecked();
            return;
        }
        reg.wait_for_teardown();
        if (q == unowned_owner())
            unowned_.lock(check);
    }

    void acquire_after_unowned(QPDF *q, bool check)
    {
        auto &reg = QpdfRegistry::instance();
        entry_ = reg.lookup_shared(q);
        if (!entry_) {
            reg.wait_for_teardown();
            return;
        }
        if (entry_->mutex.try_lock())
            return;
        auto &unowned = unowned_mutex();
        int depth = unowned.suspend();
        try {
            if (check)
                entry_->mutex.lock();
            else
                entry_->mutex.lock_unchecked();
        } catch (...) {
            entry_.reset();
            unowned.resume(depth);
            throw;
        }
        unowned.resume(depth);
    }

    void acquire_for(QPDFObjectHandle const &h, bool check)
    {
        QPDF *q = lock_target(h);
        for (;;) {
            acquire(q, check);
            // See ArgsGuard in locked_bindings.h
            if (!q)
                return;
            QPDF *now = lock_target(h);
            if (now == q)
                return;
            release();
            q = now;
        }
    }

    void release()
    {
        unowned_.release();
        if (entry_)
            entry_->mutex.unlock();
        entry_.reset();
    }

    std::shared_ptr<QpdfEntry> entry_;
    UnownedLockHold unowned_;
};

// RAII guard that locks two QPDF mutexes in consistent pointer order
// to prevent deadlocks. Used by copy_foreign(), with_same_owner_as(), etc.
class DualQpdfLockGuard {
public:
    DualQpdfLockGuard(QPDF *a, QPDF *b) { acquire(a, b); }

    // Lock what a and b need, checking afterwards that neither owner changed
    // while this thread waited.
    DualQpdfLockGuard(QPDFObjectHandle const &a, QPDFObjectHandle const &b)
    {
        QPDF *qa = lock_target(a);
        QPDF *qb = lock_target(b);
        for (;;) {
            acquire(qa, qb);
            QPDF *now_a = lock_target(a);
            QPDF *now_b = lock_target(b);
            if (now_a == qa && now_b == qb)
                return;
            release();
            qa = now_a;
            qb = now_b;
        }
    }

    ~DualQpdfLockGuard() { release(); }

    DualQpdfLockGuard(const DualQpdfLockGuard &) = delete;
    DualQpdfLockGuard &operator=(const DualQpdfLockGuard &) = delete;

private:
    void acquire(QPDF *a, QPDF *b)
    {
        auto &reg = QpdfRegistry::instance();
        bool unowned = a == unowned_owner() || b == unowned_owner();
        auto ea = a == unowned_owner() ? nullptr : reg.lookup_shared(a);
        auto eb = b == unowned_owner() ? nullptr : reg.lookup_shared(b);

        std::shared_ptr<QpdfEntry> first, second;
        if (ea == eb) {
            // Same QPDF or both null -- single lock at most
            first = std::move(ea);
        } else if (!eb || (ea && std::less<QpdfEntry *>()(ea.get(), eb.get()))) {
            first = std::move(ea);
            second = std::move(eb);
        } else {
            first = std::move(eb);
            second = std::move(ea);
        }

        // Each entry is kept only once its mutex is held, so that release()
        // undoes exactly what was done if a later lock throws.
        try {
            if (first) {
                first->mutex.lock();
                first_ = std::move(first);
            }
            if (second) {
                second->mutex.lock();
                second_ = std::move(second);
            }
            if (!first_ || (!second_ && a != b))
                reg.wait_for_teardown(); // At least one object has no owner
            if (unowned)
                unowned_.lock(true);
        } catch (...) {
            // The destructor does not run for a constructor that throws
            release();
            throw;
        }
    }

    void release()
    {
        unowned_.release();
        if (second_)
            second_->mutex.unlock();
        if (first_)
            first_->mutex.unlock();
        first_.reset();
        second_.reset();
    }

    // Shared for the same reason as QpdfLockGuard::entry_.
    std::shared_ptr<QpdfEntry> first_;
    std::shared_ptr<QpdfEntry> second_;
    UnownedLockHold unowned_;
};

// RAII guard that locks any number of QPDFs, in the same consistent order as
// DualQpdfLockGuard. Null and unregistered pointers are skipped, and the same
// QPDF may be listed more than once. unowned_owner() takes unowned_mutex(),
// after every Pdf lock.
class MultiQpdfLockGuard {
public:
    explicit MultiQpdfLockGuard(std::vector<QPDF *> const &qpdfs)
    {
        auto &reg = QpdfRegistry::instance();
        bool no_owner = false;
        bool unowned = false;
        for (auto *q : qpdfs) {
            if (q == unowned_owner()) {
                no_owner = unowned = true;
            } else if (auto entry = reg.lookup_shared(q)) {
                entries_.push_back(std::move(entry));
            } else {
                no_owner = true;
            }
        }
        std::sort(entries_.begin(), entries_.end(), [](auto const &a, auto const &b) {
            return std::less<QpdfEntry *>()(a.get(), b.get());
        });
        entries_.erase(std::unique(entries_.begin(), entries_.end()), entries_.end());
        size_t locked = 0;
        try {
            for (; locked < entries_.size(); ++locked)
                entries_[locked]->mutex.lock();
            if (no_owner)
                reg.wait_for_teardown();
            if (unowned)
                unowned_.lock(true);
        } catch (...) {
            // The destructor does not run for a constructor that throws
            while (locked > 0)
                entries_[--locked]->mutex.unlock();
            throw;
        }
    }

    ~MultiQpdfLockGuard()
    {
        unowned_.release();
        for (auto it = entries_.rbegin(); it != entries_.rend(); ++it)
            (*it)->mutex.unlock();
    }

    MultiQpdfLockGuard(const MultiQpdfLockGuard &) = delete;
    MultiQpdfLockGuard &operator=(const MultiQpdfLockGuard &) = delete;

private:
    std::vector<std::shared_ptr<QpdfEntry>> entries_;
    UnownedLockHold unowned_;
};

// Objects of a Pdf held by an object that belongs to no Pdf.
//
// A Dictionary or Array that belongs to no Pdf can hold objects that belong to
// one: indirect objects, and containers adopted by a Pdf. An operation that
// reads through it to those objects, such as repr(), == or a Page helper, needs
// their Pdfs' locks as well as unowned_mutex(). It may resolve an indirect
// object, which makes qpdf parse it from the file.
//
// The Pdfs it can reach are found by walking the direct objects that belong to
// no Pdf, which unowned_mutex() protects, and stopping at anything that belongs
// to a Pdf: everything below that belongs to the same Pdf, since adoption
// refuses objects that refer to another. The walk visits only the objects built
// in Python, which is one reason to keep such a container small and to add it
// to its Pdf soon.
//
// The guards that use this take every lock at once, in the usual order, then
// walk again and start over if what they found changed.

inline constexpr int REACH_MAX_DEPTH = 1000;

// Add the Pdfs that own objects reachable from h's children through objects
// that belong to no Pdf. h belongs to no Pdf, and the caller holds
// unowned_mutex(). A container built in Python can contain itself, so each
// one is visited once.
inline void add_reachable_owners(QPDFObjectHandle h,
    std::vector<QPDF *> &owners,
    std::unordered_set<QPDFObject const *> &visited,
    int depth = 0)
{
    if (depth > REACH_MAX_DEPTH || !visited.insert(h.getObj().get()).second)
        return;
    auto add_child = [&](QPDFObjectHandle child) {
        if (!child.isInitialized())
            return;
        if (child.isIndirect()) {
            if (QPDF *owner = child.getOwningQPDF())
                owners.push_back(owner);
            return;
        }
        // A scalar cannot change, so it needs no lock whatever owns it
        if (!child.isDictionary() && !child.isArray())
            return;
        if (QPDF *owner = child.getOwningQPDF()) {
            owners.push_back(owner);
            return;
        }
        add_reachable_owners(child, owners, visited, depth + 1);
    };
    // Not ditems(), which leaves out null values and so resolves every
    // indirect object in the dictionary to find out which are null. Those
    // belong to Pdfs whose locks this walk is looking for.
    if (h.isDictionary()) {
        for (auto const &item : h.getDictAsMap())
            add_child(item.second);
    } else if (h.isArray()) {
        for (auto const &item : h.aitems())
            add_child(item);
    }
}

inline void add_reachable_owners(QPDFObjectHandle h, std::vector<QPDF *> &owners)
{
    std::unordered_set<QPDFObject const *> visited;
    add_reachable_owners(h, owners, visited);
}

// Sort and remove duplicates, so that two sets of owners compare equal.
inline void normalize_owners(std::vector<QPDF *> &owners)
{
    std::sort(owners.begin(), owners.end(), std::less<QPDF *>());
    owners.erase(std::unique(owners.begin(), owners.end()), owners.end());
}

// RAII guard that locks what each of a list of objects needs, and for an
// object that belongs to no Pdf, the Pdfs of the objects reachable from it.
// For code outside the locked bindings, which do the same for their arguments.
class ReachGuard {
public:
    explicit ReachGuard(std::initializer_list<QPDFObjectHandle> objects)
        : objects_(objects)
    {
        auto owners = targets();
        std::vector<QPDF *> reached;
        for (;;) {
            std::vector<QPDF *> all(owners);
            all.insert(all.end(), reached.begin(), reached.end());
            guard_.emplace(all);
            auto now = targets();
            if (now != owners) {
                guard_.reset();
                owners = std::move(now);
                reached.clear();
                continue;
            }
            auto now_reached = reachable();
            if (now_reached == reached)
                return;
            guard_.reset();
            reached = std::move(now_reached);
        }
    }

    ReachGuard(const ReachGuard &) = delete;
    ReachGuard &operator=(const ReachGuard &) = delete;

private:
    std::vector<QPDF *> targets() const
    {
        std::vector<QPDF *> owners;
        for (auto const &h : objects_)
            owners.push_back(lock_target(h));
        return owners;
    }

    std::vector<QPDF *> reachable() const
    {
        std::vector<QPDF *> owners;
        for (auto const &h : objects_)
            if (lock_target(h) == unowned_owner())
                add_reachable_owners(h, owners);
        normalize_owners(owners);
        return owners;
    }

    std::vector<QPDFObjectHandle> objects_;
    std::optional<MultiQpdfLockGuard> guard_;
};

// From qpdf.cpp. Turn a QPDF into one that a pikepdf.Pdf can hold: registered
// for locking, and unregistered again when the last reference to it is dropped.
std::shared_ptr<QPDF> register_qpdf(
    std::unique_ptr<QPDF> owned, ConversionMode mode = ConversionMode::unset);
