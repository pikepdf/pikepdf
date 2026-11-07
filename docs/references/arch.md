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

Threads may share a `Pdf`. The guarantee is like the one free-threaded Python
gives for a {class}`list` or {class}`dict`: concurrent calls do not crash or
corrupt the document, but a sequence of calls is not atomic, so the data can
end up inconsistent unless you coordinate the threads.

Each `Pdf` has a lock. Every method and property of a pikepdf class that
reads or changes a `Pdf`, or any of its objects, holds the lock of that `Pdf`
while it runs. A call that involves several `Pdf`s, such as copying a page
from one to another, holds all of their locks. This holds on GIL-enabled
interpreters too. The GIL by itself does not provide it: pikepdf runs Python
code in the middle of many operations (when reading from a Python stream, for
example), and the GIL can pass to another thread whenever that happens.

Some methods are implemented in Python and change a `Pdf` in several steps.
Those that do hold the lock across all of the steps, so another thread sees
the change made in full or not at all:

- {meth}`pikepdf.Page.add_resource`, {meth}`pikepdf.Page.add_overlay` and
  {meth}`pikepdf.Page.add_underlay`
- {meth}`pikepdf.Pdf.add_pages_from` and {meth}`pikepdf.Pdf.add_blank_page`
- {attr}`pikepdf.Pdf.docinfo`
- setting the value of a field of a {class}`pikepdf.form.Form`, and
  {meth}`pikepdf.form.SignatureField.stamp_overlay`
- the functions of {mod}`pikepdf.sanitize`, and
  {meth}`pikepdf.sanitize.Sanitizer.apply`
- reading the outline when {meth}`pikepdf.Pdf.open_outline` is called, and
  writing it back when its `with` block ends; likewise writing the metadata
  back when the `with` block of {meth}`pikepdf.Pdf.open_metadata` ends

What is not protected:

- **A sequence of calls.** Reading a value and writing back a new one can be
  interleaved with calls from another thread. Wrap each such sequence in
  `with pdf.lock():`, which is re-entrant, or coordinate the threads with your
  own {class}`threading.Lock`. To make a sequence that involves several
  `Pdf`s atomic, use your own lock rather than nesting `pdf.lock()` blocks;
  see {ref}`callback-restrictions`.
- **Edits made through `open_metadata()` and `open_outline()`.** These read
  the document when they are opened and write the whole of it back when the
  `with` block ends. A change another thread made in between is overwritten.
- **Reads that take several steps.** A helper that reads a `Pdf` in several
  calls, such as the properties of {class}`pikepdf.PdfImage`, can see some
  values from before another thread's change and some from after.
- **The methods above, used on a page or object that belongs to no `Pdf`.**
  They hold the lock of the `Pdf` the page belongs to, so on a page that has
  not been added to one, each step is protected but the method as a whole is
  not. Add the page to its `Pdf` before calling them.

### Objects that belong to no `Pdf`

A {class}`pikepdf.Dictionary` or {class}`pikepdf.Array` that you have created
and not yet added to a `Pdf` has no `Pdf` lock to take. Every such object is
protected by one lock that they all share, so sharing one between threads is
as safe as sharing an object of a `Pdf`. Once the object is added to a `Pdf`
it belongs to that `Pdf`, and from then on it is protected by that `Pdf`'s
lock instead. Scalars such as {class}`pikepdf.Name` cannot be changed, and take
no lock.

Because the lock is shared, threads that each build objects of their own wait
for one another, even though the objects are unrelated. Add a `Dictionary` or
`Array` to the `Pdf` it is meant for as soon as you create it, and fill it in
there, rather than building a large structure before adding it:

```python
# Each change takes only pdf's lock
pdf.Root.Extra = pikepdf.Dictionary()
extra = pdf.Root.Extra
for key, value in items:
    extra[key] = value

# Each change takes the lock that every unattached object shares
extra = pikepdf.Dictionary()
for key, value in items:
    extra[key] = value
pdf.Root.Extra = extra
```

Such objects are rarely useful on their own, so in practice they are usually
attached soon after they are created, and the shared lock is rarely contended.

An unattached object may hold objects of a `Pdf`, such as
`pikepdf.Dictionary(P=pdf.pages[0].obj)`. An operation that reads through it
to them, such as `repr()`, `==` or a {class}`pikepdf.Page` method, takes that
`Pdf`'s lock as well. To find which `Pdf`s it needs, it looks at everything in
the object that was created in Python, which is one more reason to keep such
objects small. Simple operations such as indexing, assignment, `len()` and
`append()` do not do this, so building a large object stays fast, but every
operation still has to wait for the shared lock.

An object that holds objects of more than one `Pdf` can be created and read,
but it cannot be added to any `Pdf`: {exc}`pikepdf.ForeignObjectError` is
raised.

How these locks work inside pikepdf is described in {doc}`locking`.

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

The same applies to Python code that pikepdf runs while it works on an object
that belongs to no `Pdf`, which holds the lock that all such objects share. An
example is the iterable passed to {meth}`pikepdf.Array.extend`: if it is a
generator that reads a `Pdf`, it takes that `Pdf`'s lock while holding the
shared one, and a thread doing the reverse, such as adding an unattached object
to that `Pdf`, can make one of the two raise {exc}`RuntimeError`. Pass a list
rather than a generator that uses a `Pdf`.

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
