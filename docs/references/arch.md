# Architecture

pikepdf uses [pybind11](https://github.com/pybind/pybind11) to bind the
C++ interface of QPDF. pybind11 was selected after evaluating Cython, CFFI and
SWIG as possible binding solutions.

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

Because of the global interpreter lock (GIL), it is safe to read pikepdf
objects across Python threads. Also because of the GIL, there may not be much
performance gain from doing so.

If one or more threads will be modifying pikepdf objects, you will have to
coordinate read and write access with a {class}`threading.Lock`.

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
