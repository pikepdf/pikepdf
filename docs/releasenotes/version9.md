# v9.10.0

- Upgraded to pybind11 3.0, which is now required. Changed many of our pointer
  holder types to use the py::smart_holder.
- ``Pdf.check()`` is now deprecated, in favor of ``Pdf.check_pdf_syntax()``.
- Use explicit page number substitution in mupdf to avoid problems in how it
  names output files. {issue}`661`

# v9.9.0

- Upgraded to cibuildwheel 3.0.0.
- We now build Linux wheels using manylinux_2_28 which is based on AlmaLinux 8.
  This means that some of the libraries included in the pikepdf wheel will be
  upgraded to newer versions.
- C++-20 compiler is now required for building pikepdf.
- Fixed a reference counting test on Python 3.14a.
- We no longer build PyPy wheels by default.
- If a folder named ``../qpdf`` is found, we automatically use that as the
  companion qpdf when building. For developers this means building works
  without setting environment variables. Environment variables can still be
  set to redirect to specific installation.

# v9.8.1

- Introduced a new {class}`DimensionedFont` to avoid breaking changes in other
  code (mainly OCRmyPDF) that subclasses {class}`Font`. Remove the new
  abstract methods from {class}`Font.

# v9.8.0

- Added a significant new feature to support filling and rendering PDF forms.
  Thanks @dmjohnsson23. See `pikepdf.form` and `pikepdf.canvas`.
- Now building wheels against qpdf 12.2.0.
- We no longer build PyPy wheels on Windows, due to strange test failures that
  appear there and nowhere else.

# v9.7.1

- Numerous fixes to documentation, to fix some sections where documentation
  failed to generate properly, and to fix sphinx errors.

# v9.7.0

- Merged {pr}`639`, a branch containing support for calculating the current
  transformation matrix at time of rendering. This is a valuable building block
  for users wishing to determine when and where images are drawn. Thanks
  @rakurtz for the contribution.
- Clarified need for setuptools 77.0.3 to build. {issue}`648`

# v9.6.0

- `pikepdf.Object` that are indirect objects now raise an exception on attempts
  to hash them (add to dict-type containers), since they are in fact potentially
  mutable. For now, direct objects can still be hashed, but this is likely to be
  discontinued. {issue}`647`
- Wheels are now built against qpdf 12.0.0, which should bring performance
  improvements for most workloads.
- qpdf 11.9.0 is now the minimum build requirement.
- We no longer build PyPy wheels on macOS, due to poor supporting infrastructure
  and unfixed issues. pikepdf will likely drop PyPy in its next major release.
- `pikepdf._core._ObjectList` no longer reports its `repr()` correctly on
  Windows. This issue appears to be a compiler bug in MSVC++ and has no known
  resolution, but also very minor impact.
- setuptools 77.0.3 is now required for building.
- Updates to tooling.

# v9.5.2

- Fixed an issue where temporary files could be left behind when using
  allow_overwriting_input=True and a SIGINT is sent while the file is being
  flushed to disk, or generally within a specific timing window.
- Fixed an issue via OCRmyPDF by replacing an invalid Document Info dictionary
  with a valid dictionary.

# v9.5.1

- Bump version to address sigstore build issues.
- Pillow dropped PyPy 3.9 so we're dropping it too.

# v9.5.0

- Created setter for Outline management to make manipulating outlines easier.
  Thanks @Zhongheng-Cheng for this contribution. {issue}`636`
- pikepdf now sets XMP properties as subelements instead of inline properties,
  in line with the XMP specification. Thanks @federicobond. {issue}`628`
- pikepdf an issue with converting certain images to PIL. Thanks @DaveDeCaprio.
  {issue}`632`
- Added a new `pikepdf.exceptions` module which organizes all exceptions more
  conveniently.
- pikepdf now tries harder to extract corrupt images in a PDF when they are found.
- Fixed an issue where an exception handler referred to an object not in scope,
  causing another exception. Thanks @dhazelett. {issue}`627`
- Dropped a comment about an unsupported dependency.

# v9.4.2

- Internal type assertion error messages from qpdf that previously triggered
  a RuntimeError will now raise a PdfError. Generally these errors only occur
  in corrupted files.
- When we are updating XMP in the processing of saving, errors from updating
  XML are wrapped differently to clarify the context in which the error
  occurs.

# v9.4.1

- Fixed a process abort in JBIG2 handling related to cleanup of Python objects
  owned by C++ code.
- Fixed inconsistent behavior when setting metadata records to an empty value.
  {issue}`622`

# v9.4.0

- Added missing Python 3.13 wheels for a few platforms that were missing them,
  mainly ARM Linux, musllinux/Alpine, and Windows.
- Since Homebrew has ended support for macOS 12, macOS 13 is now the minimum
  requirement for Intel macOS.
- Suppressed some spurious warnings during build tests.

# v9.3.0

- Integrated OSS Fuzz.
- Prevented generation of PDF date strings with invalid trailing apostrophes,
  while still accepting them.
- Improved error message on parsing invalid date strings.
- Dropped support for Python 3.8 (end of life October 2024).

# v9.2.1

- Fixed some inconsistencies with the pikepdf.Rectangle class. {issue}`605`
- Python 3.13 with free-threading added to test matrix.
- Removed wheel package as build requirement since modern packing no longer
  needs it.

# v9.2.0

- Updated C++/Python exception translation to new pybind11 2.12.0+ protocol,
  fixing possible undefined behavior in multithreaded applications.
- pybind11 2.12.0 is now required.
- qpdf 11.9.1 is now used to build wheels.
- Modernized copyright information to REUSE.toml specification.
- Added a new test file for a rare case, CCITT with EndOfLine=True. Thanks
  @ekordas. {issue}`602,601`

# v9.1.2

- Fixed handling of CalRGB and CalGray images with palettes.
- Fixed a test suite failure when numpy 2.1 is installed. {issue}`603`
- Prevented use of setuptools 72+ since it seems to introduce build errors.
- Added a missing #include header. {issue}`600`

# v9.1.1

- Fixed an issue where small floating point values would be recorded in
  scientific notation, contrary to the PDF specification. {issue}`598`
- Fixed some false positive warnings on Windows C++ compilers.
- Improved support for Python 3.13 pre-release.

# v9.1.0

- Fixed a potential resource leak if we opened a file to read it as a PDF but
  it was not a valid PDF.
- When overwriting an existing PDF with `Pdf.save()`, pikepdf now attempts to
  retain the original file permissions and ownership.
- Fixed missing return type for PageList.Extend. {issue}`592`
- Fixed exception if `jbig2dec --version` exists but valids to return a
  version number.
- Fixed tests on Python 3.13 pre-release. Thanks @QuLogic.
- Changed all references of "QPDF" to "qpdf", its new spelling. Thanks @m-holger.

# v9.0.0

- Removed deprecated pikepdf.PdfMatrix. Use pikepdf.Matrix instead.
- Removed deprecated pikepdf.\_qpdf submodule.
- Pdf.pages no longer coerces PDF dictionaries to page objects. You must
  explicitly insert/add pikepdf.Page objects.
- pikepdf.Object.parse() no longer accepts string input; only bytes are allowed.
- macOS 12 is our minimum supported version for x86_64, and macos 14 is our
  minimum supported version for ARM64/Apple Silicon. v8 accidentally
  ended support for older versions at some point - this change is formalizing that.
  Efforts were made to continue support for older verions, but it is not sustainable.
- We now generate binary wheels for musllinux-aarch64 (Alpine ARM64).
