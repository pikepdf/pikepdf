# v4.5.0

- Fixed gcc linker error with linking to a source-compiled version of qpdf. Thanks @jerkenbilt.
- Fixed dead/obsolete link to old QPDF manual. Thanks @m-holger.
- Rebuild binary wheels against qpdf 10.5.0. Note 10.6.0 has been released but
  requires further changes so does not work yet.
- Removed some workarounds to support now-unsupported versions of pybind11.
- Adjusted hypothesis test settings so it does not randomly fail on PyPy.
- Mention vector vs raster images in documentation.
- JBIG2 decoding is now more tightly integrated. In particular, we can now decode
  more types of JBIG2 image and they can be decoded using either the object or
  image interface.
- Switch to tomli for TOML parsing.
- Refactor image tests to use hypothesis more effectively and use more random issues,
  fixing many errors along the way.

# v4.4.1

- Fixed two instances of a Python object being copied without the GIL held.
  May have caused some instability. Thanks @rwgk.

# v4.4.0

- Further improvements to handling of 2- and 4-bit per component images. Major
  refactoring of relevant code and improved testing.

# v4.3.1

- Mark pybind11 2.9 as supported. Thanks @QuLogic.

# v4.3.0

- Improved support for images with bits per component set to values between 2 and 7
  inclusive.
- Additional types of runtime errors produced by libqpdf are now resolved to
  `DataDecodingError` for improved error message clarity.
- Improved typing and documentation for several modules.
- Replaced all internal uses of deprecated standard library module distutils
  with the third party packaging library. This was all for version number checking.
- Maintainers: python3-packaging is now required for installation.

# v4.2.0

- Fixed incorrect default rectangle handling in `Page.add_overlay` and
  `Page.add_underlay`. Thanks @sjahu. {issue}`277`.
- Fixed `Page.add_overlay` not scaling to larger target sizes automatically.
  Thanks @bordaigorl. {issue}`276`.
- `pikepdf._core.ObjectHelper` is now registered as a base class from which other
  helper classes are derived such as `pikepdf.Page`.
- Prevented implicit conversion of ObjectHelper to Object through their inclusion
  as for example, parameters to a `pikepdf.Array`. This functionality was never
  intended, and was a side effect of certain ObjectHelper subclasses defining an
  iterable interface that made their conversion possible. {issue}`282`

# v4.1.0

- Declared support for pybind11 2.8.x.
- Wheels are now built against libqpdf 10.4.0.
- Wheels are now built for macOS Apple Silicon and Python 3.10.

# v4.0.2

- Fixed equality and copy operators for `pikepdf.Page`. {issue}`271`
- Fixed equality test on `pikepdf.Stream` objects - objects that are not identical
  but have equal data now compare as equal.
- Deprecated the use of `copy_foreign` for copying `pikepdf.Page`.

# v4.0.1

- Fixed documentation build reproducibility. (Thanks to Chris Lamb and Sean Whitton.)
- Fixed issue where file attachments not located in the current working directory
  would be created with a directory name.
- Removed some references to Python 3.6.
- Added some fixes to typing hints from @cherryblossom000.

# v4.0.0

## Breaking changes

- Python 3.10 is supported.
- Dropped support for Python 3.6, since it is reaching end of life soon. We will
  backport critical fixes to pikepdf 3.x until Python 3.6 reaches end of life in
  December 2021.
- We now require C++17 and generate wheels for manylinux2014 Linux targets. We had
  to drop support for manylinux2010, our previous target, since some of our
  dependencies like Pillow are no longer supporting manylinux2010.
