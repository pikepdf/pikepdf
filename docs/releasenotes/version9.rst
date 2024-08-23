v9.2.0
======

- Updated C++/Python exception translation to new pybind11 2.12.0+ protocol,
  fixing possible undefined behavior in multithreaded applications.
- pybind11 2.12.0 is now required.
- qpdf 11.9.1 is now used to build wheels.
- Modernized copyright information to REUSE.toml specification.
- Added a new test file for a rare case, CCITT with EndOfLine=True. Thanks
  @ekordas. :issue:`602,601`

v9.1.2
======

- Fixed handling of CalRGB and CalGray images with palettes.
- Fixed a test suite failure when numpy 2.1 is installed. :issue:`603`
- Prevented use of setuptools 72+ since it seems to introduce build errors.
- Added a missing #include header. :issue:`600`

v9.1.1
======

- Fixed an issue where small floating point values would be recorded in
  scientific notation, contrary to the PDF specification. :issue:`598`
- Fixed some false positive warnings on Windows C++ compilers.
- Improved support for Python 3.13 pre-release.

v9.1.0
======

- Fixed a potential resource leak if we opened a file to read it as a PDF but
  it was not a valid PDF.
- When overwriting an existing PDF with ``Pdf.save()``, pikepdf now attempts to
  retain the original file permissions and ownership.
- Fixed missing return type for PageList.Extend. :issue:`592`
- Fixed exception if ``jbig2dec --version`` exists but valids to return a
  version number.
- Fixed tests on Python 3.13 pre-release. Thanks @QuLogic.
- Changed all references of "QPDF" to "qpdf", its new spelling. Thanks @m-holger.

v9.0.0
======

- Removed deprecated pikepdf.PdfMatrix. Use pikepdf.Matrix instead.
- Removed deprecated pikepdf._qpdf submodule.
- Pdf.pages no longer coerces PDF dictionaries to page objects. You must
  explicitly insert/add pikepdf.Page objects.
- pikepdf.Object.parse() no longer accepts string input; only bytes are allowed.
- macOS 12 is our minimum supported version for x86_64, and macos 14 is our
  minimum supported version for ARM64/Apple Silicon. v8 accidentally
  ended support for older versions at some point - this change is formalizing that.
  Efforts were made to continue support for older verions, but it is not sustainable.
- We now generate binary wheels for musllinux-aarch64 (Alpine ARM64).
