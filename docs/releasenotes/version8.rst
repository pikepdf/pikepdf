v8.15.0
=======

- Rebuild wheels with QPDF 11.9.0.
- Relaxed dependency requirements on lxml, now that that project is publishing wheels
  for less common platforms again.

v8.14.0
=======

- Added new code to suppress console window from appearing on Windows in some
  situations when decoding JBIG2.
- Updated GitHub Actions versions.
- Added QPDF_FUTURE environment variable for compile-time testing of new QPDF
  features. This option is mainly for the developers of QPDF to confirm that pikepdf
  supports change they are considering in future releases; other users will not
  gain any benefit.

v8.13.0
=======

- Enabled PyPy 3.10 support.

v8.12.0
=======

- Rebuilt wheels with QPDF 11.8.0.
- Improved test coverage slightly.
- Minor performance improvement when using file streams.
- Minor update to metadata documentation.

v8.11.2
=======

- Fixed handling of XMP metadata when metadata contains objects in a default
  namespace.

v8.11.1
=======

- macOS wheels are now linked against the GnuTLS crypto library instead of
  OpenSSL. Hopefully this will alleviate situations where the legacy crypto
  provider could not be loaded. :issue:`520`
- Replaced all relative imports with absolute imports.
- Excluded lxml 5.x for Python 3.8 and 3.9, since this project is not producing
  wheels for 3.8 and 3.9 for the latest versions.

v8.11.0
=======

- Rebuilt with QPDF 11.7.0.
- Added support for setting page boxes to a rectangle directly, e.g.
  ``page.mediabox = rectangle`` - previously rectangle had to
  manually converted to an array.
- Fixed rendering of PDF and individual pages in Jupyter/IPython. Newer versions
  of these tools are now pickier about what types of data they render, and don't
  render PDFs directly; we now provide SVG which works well. Requires installation
  of MuPDF as before.
- Fixed rendering of inline images in Jupyter/IPython, which was not implemented.
- Fixed build process to use new artifacts v4 actions on GitHub.

v8.10.1
=======

- Rebuilt with QPDF 11.6.4.
- Replaced use of a custom C++ logger with sharing QPDF's. It is still relayed to
  the Python logger.
- Added a simpler API for adding attachments from bytes data.
- Deprecated use of Object.parse(str) in favor of Object.parse(bytes).

v8.10.0
=======

- Fixed a performance regression when appending thousands of pages from one PDF to
  another.
- Fixed some obscure issues with iterators over ``Pdf.pages`` that would have led
  to incorrect or unintuitive behavior, like partial iteration not being accounted
  for.
- Using the ``Pdf.pages`` API to insert objects other ``pikepdf.Pdf`` is now
  deprecated. Previously, we accepted ``pikepdf.Dictionary`` that had its ``/Type``
  set to ``/Page``. Now, one must wrap these dictionaries in ``pikepdf.Page()``.
- Added type hints that ``pikepdf.Object`` can be implicitly converted to float
  and int.

v8.9.0
======

- Overhauled documentation. Previously the documentation could only be generated in
  an environment where pikepdf was compiled and installed, since generating the final
  result depended on executing pikepdf. Now, these dynamic features are removed and
  the documentation is static. All documentation that was defined in C++ has been
  pulled out and defined in Python stub files instead, which means compiled binaries
  are no longer needed to access documentation. This change simplifies the generation of
  documentation and makes it easier for IDEs to look up function signatures.
- Similarly, typing is now defined only in Python stub files.

v8.8.0
======

- Added new ``pikepdf.canvas`` module with rudimentary content stream creation
  functions.

v8.7.1
======

- Fixed ``pikepdf.Matrix.rotated()`` so it now rotates in the advertised direction.

v8.7.0
======

- ``pikepdf.PdfMatrix`` is now deprecated, in favor of ``pikepdf.Matrix``. The former,
  unfortunately, implemented some operations backwards compared to the PDF reference
  manual. The new class fixes these issues, and adds more functionality, promoting
  transformation matrix to first class objects. ``PdfMatrix`` is now deprecated and
  will be removed in the next major release.
- Improve behavior around truthiness of ``pikepdf.Name``.

v8.6.0
======

- Implemented Page.artbox and Page.bleedbox to access these page dimension boxes.

v8.5.3
======

- Fixed exception on certain ``PdfImage.__repr__`` when the image's mode was invalid.
- Fixed some minor issues that caused code coverage to miss some covered lines.
- Removed some unused code.

v8.5.2
======

- Rebuilt wheels with libqpdf 11.6.3, which solves a potential data loss issue,
  albeit in rare circumstances. See `QPDF issue #1050 <https://github.com/qpdf/qpdf/issues/1050>`_.
- Fixed unclear return values of pikepdf._core.set/get* functions. The set functions
  now return the current value.
- Fixed minor typing issues.

v8.5.1
======

- Added building of Python 3.12 aarch64 images.
- Added building of musllinux_1_2 aarch64 images.
- Tweaked exception handler of ``atomic_overwrite``.

v8.5.0
======

- We now require Pillow 10.0.1, due a serious security vulnerability in all earlier
  versions of that dependency. The vulnerability concerns WebP images, which are
  likely not involved in PDF processing, but we have updated the dependency anyway
  as a precaution. As a consequence, we no longer build binary wheels for PyPy 3.8.
  CPython 3.8 is still supported on all platforms.
- The embedded files/attachments API now supports describing the relationship of the
  attached file (AFRelationship).

v8.4.1
======

- Fixed an issue with a monochrome that decoded with colors inverted. :issue:`517`

v8.4.0
======

- Added support for musllinux_1_2 (Alpine Linux 3.16) on x64.

v8.3.2
======

- Added _core.pyi typing hints, which were missing from wheels.

v8.3.1
======

- Fixed saving file opened from BytesIO object on Windows. :issue:`510`

v8.3.0
======

- Mark Python 3.12 as supported and release wheels for it.

v8.2.3
======

- Added a build test for Python 3.12 pre-release versions.
- Marked a test as xfail that currently fails on Python 3.12.

v8.2.2
======

- Added docs/ directory back to source distribution. :issue:`503`

v8.2.1
======

- Fixed a build issue where pikepdf would install its C++ source files into the
  site-packages directory. :issue:`447`

v8.2.0
======

- Removed uses of deprecated function datetime.utcnow(). :issue:`499`
- Adjusted timeline of potentially flaky hypothesis test.
- Various documentation fixes. Thanks @m-holger.
- PyPy 3.10 is now supported on some platforms.
- PyPy 3.8 support will be dropped in the next major release.

v8.1.1
======

- Fixed a Unicode test that randomly fails on Windows.

v8.1.0
======

- Not released due to build failure.
- Fixed sdist, which was mysteriously missing some files that were previously included. :issue:`490`
- Some documentation and README updates to improve visibility of release notes. :issue:`488`
- Fixed issue where an output file could be corrupted if the process was interrupted while writing. :issue:`462`

v8.0.0
======

- master branch renamed to main.
- QPDF 11.5.0 is now required.
- Some other Python dependencies have been updated.
- Dropped setuptools-scm in favor of a manually set version number and script
  to update it. This change was necessary to support delegating part of the build
  to Cirrus CI.
- Adjusted stream preview (with ``__repr__``) so it does not attempt to decompress
  very long streams.
- Fixed error when attempting to convert XMP metadata to DocumentInfo when the
  author was omitted.
- Added a method to add items to the document table of contents.
- Previously, we built all Apple Silicon (aarch64) wheels as a manual step,
  causing errors and delays in their release compared to other wheels. We now
  build them automatically on Cirrus CI.
- Changed to building manylinux-aarch64 wheels on Cirrus CI.
- Since Pillow (Python imaging library), a major dependency, has dropped support
  for 32-bit wheels on Windows and Linux, we have done the same. You can still build
  32-bit versions from source.
- Some documentation changes and improvements. Thanks @m-holger.
