# v10

## Breaking changes for v10.x
- Dropped Python 3.9 compatibility, since it is end of life. Python 3.10 through
  3.14 are supported.
- Dropped macOS 13 support, since it is end of life.
- Dropped macOS 14 Intel wheels, because GitHub doesn't provide a way to build
  them - macOS 15 Intel works fine.
- Dropped deprecated method `Pdf.check()` (use `.check_pdf_syntax()`).

pikepdf now declares unstable "support" for freethreading, and does not publish
freethreading wheels. All tests seem to pass, but that's because the existing
tests don't try to create race conditions. Must be compiled manually.

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

