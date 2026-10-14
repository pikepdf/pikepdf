# Architecture

pikepdf uses [nanobind](https://github.com/wjakob/nanobind) to bind the
C++ interface of QPDF. Earlier versions used
[pybind11](https://github.com/pybind/pybind11), which was selected after
evaluating Cython, CFFI and SWIG; pikepdf migrated to nanobind in v10 for
better performance and free-threaded Python support.

In addition to bindings pikepdf includes support code written in a mix of C++
and Python, mainly to present a clean Pythonic interface to C++ and implement
higher level functionality.

## Internals

Internally the package presents a module named `pikepdf` from which objects
can be imported. The C++ extension module is currently named `pikepdf._core`.
Users of `pikepdf` should not directly access `_core` since it is an
internal interface. In previous versions, this library was named `_qpdf`.

In general, modules or objects behind an underscore are private (although they
may be returned in some situations).

## Thread safety

pikepdf supports free-threaded (no-GIL) CPython and publishes `cp314t` wheels.

Each `Pdf` has a lock, and every pikepdf method takes the lock of each `Pdf`
it reads or changes, so one call never sees another call on the same `Pdf`
half done. This holds on GIL-enabled interpreters too. The GIL by itself
does not provide it: pikepdf runs Python code in the middle of many
operations (when reading from a Python stream, for example) and the GIL can
pass to another thread whenever that happens.

Only single calls are protected. A sequence of calls, such as reading a value
and writing back a new one, can still be interleaved with calls from another
thread. If more than one thread modifies the same `Pdf`, wrap each such
sequence in `with pdf.lock():`, or coordinate the threads with your own
{class}`threading.Lock`.

(callback-restrictions)=

### Callbacks

pikepdf calls your code while it is in the middle of working on a `Pdf`: a
{class}`pikepdf.TokenFilter` or {class}`pikepdf.StreamParser`, a `progress`
function, and the methods of a Python stream that a `Pdf` is being read from
or written to. The `Pdf` is locked for the duration.

**A callback may only use the `Pdf` it was called for.** If a callback uses
another `Pdf` while a second thread, working on that one, uses the first, each
thread holds the lock the other needs. pikepdf detects this and raises
{exc}`RuntimeError` in one of the two threads, which lets the other continue.
The same applies to nested `with pdf.lock():` blocks that two threads enter in
opposite orders. Treat the error as a bug in the calling code rather than
something to catch and retry: collect what the callback needs from other
documents before starting, or apply what it found afterwards.

Some callbacks are more restricted still, whether or not threads are involved:

- A `progress` function passed to {meth}`pikepdf.Pdf.save` or
  {meth}`pikepdf.Pdf.check_pdf_syntax`, and the `write` method of a stream
  being saved to, must not use the `Pdf` at all. It is part way through
  being written; reading it can disturb the writer and modifying it will
  almost certainly corrupt the output.
- The `read` and `seek` methods of a stream that a `Pdf` was opened from are
  called whenever pikepdf loads more of the file, which can be during almost
  any operation. They must not use that `Pdf`.
- A token filter or stream parser may read the `Pdf` it is filtering, but
  should not modify the content stream it is being fed.

It is not currently possible to pickle pikepdf objects or marshall them across
process boundaries (as would be required to use pikepdf in
{mod}`multiprocessing`). If this were implemented, it would not be much more
efficient than saving a full PDF and sending it to another process.
Parallelizing work (for example, by dividing work by PDF pages) can still be
achieved by having each worker process open the same file.

## File handles

Because of technical limitations in underlying libraries, pikepdf keeps the
source PDF file open when a content is copied from it to another PDF, even when
all Python variables pointing to the source are removed. If a PDF is being
assembled from many sources, then all of those sources are held open in memory.
