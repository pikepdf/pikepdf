# Locks

This page is for people working on pikepdf itself. It describes the locks
inside pikepdf, what each one protects, and how they behave on GIL-enabled
and free-threaded Python. For what users of pikepdf need to know, see
{ref}`callback-restrictions` and the thread safety section of
{doc}`arch`.

## Why pikepdf needs its own locks

qpdf is not thread-safe. A `QPDF` object, and every object handle that
belongs to it, may only be used by one thread at a time. Even reading is
unsafe, because qpdf loads objects from the file lazily: the first read of an
indirect object moves the file position, parses, and fills the object cache.

On a free-threaded build nothing stops two threads from calling into the
same `QPDF` at once, so a lock is obviously needed. On a GIL-enabled build
it is needed too, which is less obvious. The GIL serializes Python
bytecode, not qpdf operations, and it changes hands part way through many of
them:

- when qpdf reads from a Python stream (`readinto`, `seek` and `tell` run
  Python code);
- when it writes to a Python stream, or calls a `progress` function;
- when it runs a {class}`pikepdf.TokenFilter` or {class}`pikepdf.StreamParser`
  callback;
- when it logs a warning through the `logging` module;
- when an allocation triggers a garbage collection, which can run any
  finalizer, including the one that destroys another `Pdf`;
- when pikepdf releases the GIL outright, as it does while it opens a file
  and while it writes one.

Each of these gives another thread a chance to enter the same `QPDF` while
the first is still in the middle of an operation.

## Overview

| Lock | Protects | Kind |
|---|---|---|
| Per-`Pdf` lock (`QpdfEntry::mutex`) | one `QPDF` and all of its objects | `ReentrantFtMutex` |
| Teardown lock (`QpdfRegistry::teardown_mutex_`) | objects of a `QPDF` that is being destroyed | `ReentrantFtMutex`, global |
| Registry lock (`QpdfRegistry::map_mutex_`) | the map from `QPDF *` to its entry | `std::mutex`, global |
| Wait table lock (`ReentrantFtMutex::Waiting`) | the table used to detect deadlocks | `std::mutex`, global |
| Adopted objects lock (`QpdfEntry::adopted_mutex_`) | the list of direct objects a `Pdf` has adopted | `std::mutex`, per `Pdf` |
| qpdf globals lock (`qpdf_global_mutex`) | qpdf's global limits, through `pikepdf.settings` | `std::mutex`, global |
| Traversal locks (`ObjectSet`, `ContentScopes`) | the state of one graph traversal | `std::mutex`, per object |
| Pillow limit lock (`_pil_limit_lock`) | `PIL.Image.MAX_IMAGE_PIXELS` while pikepdf changes it | {class}`threading.Lock` |

Module-level settings that are a single value, such as the decimal precision
and the default conversion mode, are `constinit std::atomic` variables, not
locks. Per-thread state, such as the stack of conversion mode overrides, is
`thread_local`.

### On GIL-enabled and free-threaded Python

| Lock | GIL-enabled build | Free-threaded build |
|---|---|---|
| Per-`Pdf` lock | Real. An uncontended lock is a few plain loads and stores, which the GIL makes safe. A thread that finds it held releases the GIL and sleeps on a condition variable. | Real. nanobind's `ft_mutex` (a `PyMutex`), plus an owner and depth for re-entrancy. A waiting thread detaches from the interpreter while it waits. |
| Teardown lock | As the per-`Pdf` lock | As the per-`Pdf` lock |
| Deadlock check | Runs only when a lock is contended | Runs only when a lock is contended |
| Registry, wait table, adopted objects, qpdf globals, traversal | `std::mutex`. Needed, because a thread can be inside qpdf with the GIL released. Each is held only briefly and never while calling Python. | `std::mutex`, held only briefly and never while calling Python |
| `constinit std::atomic` settings | Atomic, though the GIL alone would suffice | Atomic; required |
| Pillow limit lock | {class}`threading.Lock` | {class}`threading.Lock` |

None of these locks compiles to nothing on a GIL-enabled build. Earlier
versions of pikepdf relied on the GIL and made the per-`Pdf` lock a no-op
there, which was wrong for the reasons listed above.

## The per-`Pdf` lock

Every `QPDF` that pikepdf creates is registered in `QpdfRegistry`
(`src/core/qpdf_lock.h`), which maps the `QPDF *` to a `QpdfEntry`. The entry
holds the lock, the document's conversion mode, and the list of adopted
objects. Entries are reference counted: a thread that is locking a `QPDF`,
or waiting to, holds a reference to the entry, so the lock outlives the
`QPDF` if another thread destroys the document meanwhile.

The lock is re-entrant. One call often locks the same `Pdf` more than once:
the binding locks it, then the type caster for the return value locks it
again to resolve indirect objects; a Python method in `_methods.py` calls
several bindings in turn; a callback calls back into pikepdf on the same
`Pdf`.

### How bindings take it

Bindings do not usually lock anything themselves. A class bound with
`locked_class_` (`src/core/locked_bindings.h`) wraps each method so that it
locks the `Pdf` that owns each of its arguments before the body runs. Which
`Pdf` owns a value of a given C++ type is declared once, by specializing
`LockOwner`; a class whose type has no such declaration cannot be bound with
`locked_class_`, so a forgotten lock is a compile error. A prek hook
(`cpp-locked-class` in `prek.toml`) rejects plain `py::class_` in the files
that have been converted. A binding that must not be wrapped is registered
as `unlocked(f)`, so the exception is visible where it is made.

Code that locks by hand uses one of three RAII guards:

- `QpdfLockGuard` locks one `QPDF`;
- `DualQpdfLockGuard` locks two, for example when copying objects between
  documents;
- `MultiQpdfLockGuard` locks any number.

The guards that take several locks always take them in the same order (by
the address of the registry entry), so two calls that each lock the same
pair of `Pdf`s cannot deadlock. If a later lock throws, they release the ones
already taken.

`Pdf.lock()` is the same lock, exposed to Python through `_acquire_lock` and
`_release_lock`, so that users can make a sequence of calls atomic.

### GIL-enabled builds

The lock is `owner_` (a thread identifier) and `depth_`. Only a thread that
holds the GIL reads or writes them, so taking a free lock or re-entering a
held one needs no atomic read-modify-write and no system call.

A thread that finds the lock held by another:

1. increments `waiters_`;
2. releases the GIL;
3. waits on the condition variable `released_` under `sleep_mutex_`;
4. releases `sleep_mutex_` before taking the GIL back, so a thread holding
   the GIL never waits for `sleep_mutex_`;
5. checks `owner_` again, since another thread may have taken the lock in
   between, and goes back to step 2 if so.

`unlock()` notifies the condition variable only when `waiters_` is non-zero,
so an uncontended unlock costs nothing extra. It briefly takes
`sleep_mutex_` before notifying, which orders the release after a waiter's
check of `owner_` and prevents a lost wake-up.

### Free-threaded builds

The lock is nanobind's `ft_mutex`, a `PyMutex`, with the same `owner_` and
`depth_` on top for re-entrancy. `PyMutex` detaches the thread from the
interpreter while it waits, so a waiting thread does not block a
stop-the-world garbage collection.

A free-threaded interpreter often runs with the GIL enabled, because
importing a module that does not declare free-threading support (lxml, for
example) turns it back on. The free-threaded implementation is used either way:
which one is compiled depends on the build, not on whether the GIL happens
to be enabled.

### Deadlock detection

A thread can hold one `Pdf`'s lock and then ask for another's: from a
callback that runs while a `Pdf` is locked, or from nested `with pdf.lock()`
blocks. Two threads doing that in opposite orders would wait for each other
for ever.

`ReentrantFtMutex::Waiting` keeps a global table of which thread is waiting
for which lock, under its own `std::mutex`. A thread about to wait follows
the chain from the lock it wants to that lock's holder, to the lock that
holder is waiting for, and so on. If the chain comes back to the thread
itself, it throws `DeadlockError`, which reaches Python as {exc}`RuntimeError`.
Unwinding releases the locks the thread holds, and the other threads in the
cycle carry on. Only contended locks pay for this check.

Code that cannot throw waits without the check: `lock_unchecked()`, and
`QpdfLockGuard(q, std::nothrow)`. The `QPDF` deleter, the teardown lock and
the return value type caster use these.

### Rules

- Every `lock()` must be made while holding the GIL, or while attached to
  the interpreter on a free-threaded build. Nothing checks this.
- `unlock()` must be called by the thread that called `lock()`. The owner is
  a thread identifier, so a lock that is not released before its thread
  exits stays held, and a later thread that is given the same identifier
  would be let in as if it were the owner.
- Never call Python code while holding one of the `std::mutex` locks listed
  above. Python code can release the GIL, run a garbage collection or wait
  for a per-`Pdf` lock, any of which can deadlock against a thread that
  needs the `std::mutex`.
- A lazy iterator over a qpdf container, returned from a binding, keeps
  reading the `Pdf` after the binding has released the lock. Return a
  snapshot instead.

## The teardown lock

`~QPDF` clears the owner of each of its objects and then destroys their
values. A thread that read one of those objects in between would find no
owner, take no lock, and read a value that is being destroyed.

So the `QPDF` deleter (`register_qpdf` in `src/core/qpdf.cpp`) takes the
document's own lock, then calls `QpdfRegistry::begin_teardown()`, which
takes the global teardown lock and increments a counter. It disconnects the
adopted objects, deletes the `QPDF`, unregisters it, and calls
`end_teardown()`. A thread about to use an object with no owner calls
`wait_for_teardown()`, which does nothing unless the counter is non-zero, and
otherwise takes and releases the teardown lock.

The teardown lock is re-entrant, so code run by the destroying thread
itself, including the destruction of a second `Pdf`, passes straight
through.

## The `std::mutex` locks

These protect small data structures and are never held while Python code
runs.

- **Registry lock.** Held while a `QPDF` is registered, unregistered or
  looked up. Lookups return a `shared_ptr` to the entry, so the caller can
  release the registry lock before taking the per-`Pdf` lock.
- **Wait table lock.** Held while a thread records that it is about to wait
  for a per-`Pdf` lock, checks for a cycle, and removes its record.
- **Adopted objects lock.** qpdf records an object's owner as a raw pointer,
  and `~QPDF` only clears that pointer on objects still in its cache. A direct
  object that pikepdf adopted and that was later detached would be left with
  a dangling pointer. Each `QpdfEntry` keeps weak references to the objects
  it adopted, and the deleter disconnects those still alive. This lock
  protects that list.
- **qpdf globals lock.** qpdf keeps its global limits in plain variables.
  This serializes the reads and writes made through `pikepdf.settings`. It
  cannot cover qpdf's own reads while it parses, so limits should be set
  before threads are started.
- **Traversal locks.** An `ObjectSet` or `ContentScopes`
  (`src/core/traversal.h`) can hold objects of several documents, or of
  none, so it cannot use a per-`Pdf` lock. Each has a mutex of its own.

## Testing

`tests/test_threading.py` and `tests/test_threading_object.py` run the same
operations from several threads. The `frequent_thread_switches` fixture
lowers the switch interval so that a GIL-enabled interpreter changes threads
as often as it can, which makes interleavings in the middle of a qpdf
operation likely. `run_threads` reuses its threads from one call to the
next: on a free-threaded build, starting a thread can take a tenth of a
second when every CPU is busy, as it is on a CI runner shared by several
test workers.

The ThreadSanitizer job (`.github/workflows/tsan.yml`, and
{doc}`debugging`) runs these tests on a free-threaded build with the GIL
disabled. Free-threaded wheel jobs mostly run with the GIL enabled, because
lxml turns it back on; set `PYTHON_GIL=0` to keep it off.
