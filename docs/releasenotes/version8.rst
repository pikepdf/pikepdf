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
