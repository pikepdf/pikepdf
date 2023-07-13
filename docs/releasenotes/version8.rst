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
- Some documentations changes and improvements. Thanks @m-holger.
