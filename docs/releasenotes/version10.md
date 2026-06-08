# v10

## Breaking changes for v10.x
- Dropped Python 3.9 compatibility, since it is end of life. Python 3.10 through
  3.14 are supported.
- Dropped macOS 13 support, since it is end of life.
- Dropped macOS 14 Intel wheels, because GitHub doesn't provide a way to build
  them - macOS 15 Intel works fine.
- Dropped deprecated method `Pdf.check()` (use `.check_pdf_syntax()`).

pikepdf supports free-threaded (no-GIL) CPython. Starting with v10.8.0, pikepdf
publishes free-threaded CPython 3.14 (`cp314t`) wheels to PyPI; before v10.8.0,
free-threaded use required building from source. As always, coordinating
concurrent modification of the same object across threads requires a lock -- see
the architecture notes on thread safety.

## v10.8.0

- pikepdf now publishes free-threaded CPython 3.14 (`cp314t`) binary wheels to
  PyPI for Linux (manylinux and musllinux, x86-64 and aarch64), macOS (x86-64
  and Apple Silicon) and Windows (x86-64). Previously these wheels were not
  published and free-threaded users had to build pikepdf from source.
- Updated the PyPI "Free Threading" trove classifier from "1 - Unstable" to
  "3 - Supported".
- Some of pikepdf's dependencies (such as lxml and Pillow) publish their own
  free-threaded wheels; on less common platforms or when older versions are
  involved, free-threading might require source builds of those dependencies.
- Reimplemented `Page`'s attribute, item and `get` accessors in C++ instead of
  Python. These delegate to the underlying page dictionary and were previously
  implemented as Python augmentations; moving them to C++ removes extra Python
  call frames on these hot paths. Behavior is unchanged.
- Object construction (`Name`, `Array`, `Dictionary`, the `Name.Attr`
  shorthand, the scalar types `Integer`/`Boolean`/`Real`, and `NamePath`)
  is now implemented in C++ for improved performance. Behavior is unchanged.

## v10.7.3

- Upgraded to cibuildwheel 3.4.1 and refreshed pinned GitHub Actions
  (`actions/checkout@v6`, `actions/upload-artifact@v7`,
  `actions/download-artifact@v8`, `codecov/codecov-action@v6`). Dropped the
  CPython 3.15 prerelease test job, since cibuildwheel has not yet shipped a
  stable release with 3.15 support.
- Fixed Windows wheels bundling a fixed-version, un-mangled copy of the Microsoft
  Visual C++ runtime (`msvcp140*.dll`, `vcruntime140*.dll`, `concrt140.dll`)
  inside the package directory. These were inadvertently copied from qpdf's
  prebuilt release alongside `qpdf30.dll`. Shipping them caused a second,
  conflicting copy of the C++ runtime to load in the same process, which could
  corrupt CPython's per-thread state and produce a fatal `PyInterpreterState_Get
  ... the GIL is released (the current Python thread state is NULL)` error or an
  `ImportError` for `pikepdf._core`, typically only in some launch environments
  (e.g. a terminal but not IDLE) or when another extension was imported first.
  The Windows wheel now copies only qpdf's own DLLs; `delvewheel` vendors a
  name-mangled copy of the C++ standard library runtime and uses CPython's own
  `vcruntime140`, so the wheel remains self-contained without an un-mangled
  runtime in the package directory that could collide with the system copy.
  Fixes :issue:`718`.
- Improved the error message raised when `pikepdf._core` fails to import: it now
  reports the active interpreter, version, free-threading status, and (on Windows)
  a hint about the Visual C++ Redistributable and interpreter mismatches.
- Fixed a segmentation fault when comparing two *direct* (non-indirect)
  `Dictionary` or `Array` objects that form a cyclic reference graph, for example
  `a['/Kids'] = [b]; b['/Kids'] = [a]; a == b`. The cycle detector previously keyed
  its bookkeeping on `unparseBinary()`, which itself recurses through the whole
  graph and overflowed the C stack for direct cyclic objects. Equality now detects
  cycles by object identity instead, so such comparisons terminate. Fixes
  :issue:`731`.
- Fixed an `AttributeError` when reading a document outline ("bookmarks") whose
  items are missing the required `/Title` field. By default, `Pdf.open_outline()`
  now quietly treats a missing `/Title` as an empty string; passing
  `strict=True` raises `OutlineStructureError` instead. Fixes :issue:`730`.

## v10.7.2

- Fixed a segmentation fault when an object that is not an `Encryption`, `dict`,
  `bool`, or `None` (for example a `list` or `unittest.mock.MagicMock`) was passed
  to the `encryption` argument of `Pdf.save()`. A `TypeError` is now raised instead.
  Fixes :issue:`727`.
- Fixed a possible segmentation fault in `Page.add_content_token_filter()` if the
  user had previously assigned a non-list value to the private
  `Pdf._token_filter_refs` attribute. The attribute is now reset before use.
- Suppressed nanobind's `leaked instances/types/functions` report at
  interpreter shutdown. Module-scope Python state (e.g. `pytest.mark.parametrize`
  arguments) commonly holds pikepdf objects until the interpreter exits;
  nanobind reports these as leaks even though they are not bugs. Set the
  environment variable `PIKEPDF_NANOBIND_LEAK_WARNINGS=1` before importing
  pikepdf to re-enable the report for debugging. Fixes :issue:`728`.
- Fixed `Array.append(None)` raising `TypeError` instead of inserting a PDF
  null object. This was a nanobind migration regression vs. v10.5. Fixes
  :issue:`725`.
- Fixed `Dictionary.__setattr__(name, None)` (i.e. `d.Key = None`) raising
  `TypeError` instead of the documented `ValueError` advising to use `del` to
  remove the key. Same nanobind migration regression as `Array.append(None)`.
- Fixed macro redefinition warnings on Fedora rawhide (Python 3.14 + glibc
  2.42) by ensuring `Python.h` is included before any standard library headers
  in all translation units. Fixes :issue:`724`.
- Moved the 2-bit and 4-bit subbyte pixel unpack inner loops from Python into
  C++, eliminating per-byte interpreter overhead when decoding low-bit-depth
  images.

## v10.7.1

- Fixed build to continue generating Python version specific wheels for
  3.12 and 3.13 due to open issue in nanobind. Fixes :issue:`723`. Thanks
  @mgorny for reporting.
- Improved CI build to perform more detailed tests using python3-dbg (debug
  build) which has more assertions and would have uncovered this issue.

## v10.7.0

- Yanked release from PyPI due to segfaults on Python 3.12 and 3.13; fixed in
  10.7.1.
- Python 3.12+ are now built with abi3 (the Stable ABI). Earlier versions and
  freethreading builds continue to be built against the specific Python versions.
- Remove manual hack to generate docs/requirements.txt for the readthedocs.org.

## v10.6.0

- Released v10.6.0 with version bump only.

## v10.6.0rc2

- Fixed a regression during nanobind migration (exception hierarchy
  unintentionally changed).

## v10.6.0rc1

- Replaced pybind11 with nanobind and added full freethreading support. pikepdf
  binary size is now both ~20% smaller and about 10% faster thanks to nanobind.

## v10.5.1

- Updated lockfile to avoid a PyJWT CVE. We only depend use PyJWT via pygithub
  for developer release tooling not in pikepdf itself, so this is
  inconsequential for pikepdf users but does silence automated security
  advisories.
- Suppressed GCC ``-Wpsabi`` note about C++17 ABI change for ``std::pair`` in
  pybind11 headers.

## v10.5.0

- Fixed logger in ``ctm`` module using ``__file__`` instead of ``__name__``,
  which produced unhelpful log names. :issue:`712`
- Modernized README.
- Test all README code blocks instead of just one.

## v10.4.0

- Enums are now proper Python ``enum.Enum``/``enum.IntFlag`` types (PEP 435
  compliant), migrated from pybind11's deprecated ``py::enum_`` to
  ``py::native_enum``.
- Reimplemented the PDFDocEncoding codec in pure Python using the standard
  library charmap pattern, removing the C++ dependency on qpdf for encoding.
- Upgraded to qpdf 12.3.2.
- Fixed incorrect docstrings for ``StreamDecodeLevel``. :issue:`708`
- Fixed type stubs: added PEP 570 positional-only markers, and corrected
  ``index()`` signature.

## v10.3.0

- Fixed UnicodeDecodeError when listing keys of a dictionary containing invalid
  UTF-8. Thanks @qooxzuub. :issue:`696`
- Fixed an issue where opening a PDF with duplicate form field names would cause a
  crash. Accessing a duplicate field by name now returns a proxy list of all matching
  fields. Thanks @qooxzuub. :issue:`697`
- Added `.values()` accessor to `Object` for iterating over dictionary values. Thanks @qooxzuub.:issue:`699,697`
- Added `.copy()` and `.update()` methods to `Dictionary`. Thanks @qooxzuub.:issue:`700`
- Improved `Object.copy` implementation and added type stubs. Thanks @qooxzuub.:issue:`702`
- Fixed missing return in `SimpleFont._encode_diffmap()`. Thanks @lachlan.charlick :issue:`706`
- Improved error messages for invalid dictionary access. Thanks @qooxzuub.:issue:`701`
- Lazy load lxml and Pillow to improve import time. Thanks @qooxzuub. :issue:`704`
- Improved `atomic_overwrite` robustness for restricted directories and special files. :issue:`695`

## v10.2.0

- Fixed `unparse_content_stream()` not preserving literal strings when given raw
  Python tuples. :issue:`689`
- The {func}`pikepdf.explicit_conversion` context manager is now thread-local and
  takes precedence over the global setting from {func}`pikepdf.set_object_conversion_mode`.
  Nested context managers are supported via a depth counter.
- Moved explicit conversion functions to their own module for better code organization.
- Improved C++ test coverage to 97.5% (from 96.4% line coverage, 94.9% to 95.1% function coverage).

## v10.1.0

- Added {class}`pikepdf.NamePath` for ergonomic access to deeply nested PDF
  structures. NamePath provides a single-operation traversal with helpful error
  messages showing exactly where traversal failed.
  See {ref}`Accessing nested objects with NamePath <namepath>` for details.
- Added explicit scalar types: {class}`pikepdf.Integer`, {class}`pikepdf.Boolean`,
  and {class}`pikepdf.Real`. When explicit conversion mode is enabled, these types
  are returned instead of Python native types (`int`, `bool`, `Decimal`), enabling
  better type safety and static type checking.
- Added {func}`pikepdf.set_object_conversion_mode` and
  {func}`pikepdf.get_object_conversion_mode` to control conversion behavior globally.
- Added {func}`pikepdf.explicit_conversion` context manager for temporarily enabling
  explicit conversion mode.
- Added safe accessor methods to {class}`pikepdf.Object`: {meth}`~pikepdf.Object.as_int`,
  {meth}`~pikepdf.Object.as_bool`, {meth}`~pikepdf.Object.as_float`, and
  {meth}`~pikepdf.Object.as_decimal` with optional default parameters for type-safe
  access to scalar values.
- `pikepdf.Integer` and `pikepdf.Real` now support full arithmetic operations with
  both `int` and `float` operands, including true division (`/`).

## v10.0.3

- Fixed an issue where `PdfImage.as_pil_image()` would create additional unused objects in the PDF that called it.
- Fixed a shutdown segfault in the alpha release of Python 3.15.
- Fixed `Pdf.show_xref_table()` not actually showing its output.
- Pin test dependencies python-xmp-toolkit to < 2.1.0. python-xmp-toolkit 2.1.0 is effectively a breaking change, requiring a new version of libexempi to be installed that is not available on some cibuildwheel builders. As a workaround, we have pinned the older version. We only use python-xmp-toolkit for testing to confirm correctness--pikepdf has its own XML-based implementation of XMP.

## v10.0.2

- Fixed presentation of strings using `unparse_content_stream` - if the stream can be represented using PdfDocEncoding, it is rendered in that way for ease of reading. :issue:`682`
- Reformatted C++ source.

## v10.0.1

- Fixed issue with performing equality test on dictionaries with cyclic subgraphs.
  :issue:`677`

## v10.0.0

See breaking changes for v10.0.0 above.

