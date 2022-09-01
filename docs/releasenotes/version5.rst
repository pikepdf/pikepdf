v5.6.1
======

-  Made treatment of CCITT image photometry ignore ``BlackIs1``, since this seems
   more consistent with other programs.

v5.6.0
======

-  Improved support for extracting the contents of inline images.
-  Marked some "always should have been private" functions as deprecated with removal
   planned for v6, mainly in pikepdf.models.image.
-  Fixed all Python documentation style inconsistencies.

v5.5.0
======

-  Fixed undefined behavior on creating NameTree on direct object. Thanks @willangley.
-  Fixed sdist with coverage build.
-  Added support for specifying QPDF's library build directory, for compatibility
   with QPDF's transition to cmake.
-  ``QPDF_*`` environment variables will modify build paths even when ``CFLAGS`` is
   defined.
-  Fixed rare case where GIL was not held while discarding a certain exception.
-  Now using cibuildwheel 2.9.0.
-  Many typo fixes. Thanks @PabloAlexis611.

v5.4.2
======

-  Fixed ``Pages.__eq__`` not returning NotImplemented when it ought to.
-  Fixed possible problems with ``NameTree`` and ``NumberTree.__eq__`` operators.
-  Changed to SPDX license headers throughout.

v5.4.1
======

-  Chores. Fixed ReadTheDocs build, updated versions, fixed a test warning, improved
   coverage, modernized type annotations.

v5.4.0
======

-  New feature: ``pikepdf.Job`` bindings to QPDFJob API.
-  New feature: ``pikepdf.NumberTree`` to support manipulation of number trees,
   mainly for applying custom page labels.
-  Many improvements to ``pikepdf.NameTree`` including the ability to instantiate
   a new name tree.
-  Several memory leaks were fixed.
-  Rebuilt against pybind11 2.10.0.

v5.3.2
======

-  Build system requires changed to setuptools-scm 7.0.5, which includes a fix to
   an issue where pikepdf source distribution reported a version of "0.0" when installed.

v5.3.1
======

-  Fixed issue with parsing inline images, causing loss of data after
   inline images were encountered in a content stream. The issue only affects
   content streams parsed with ``parse_content_stream``; saved PDFs were not
   affected. :issue:`299`
-  Build system requires changed to setuptools-scm 7.0.3, and
   setuptools-scm-git-archive is now longer required.

v5.3.0
======

-  Binary wheels for Linux aarch64 are now being rolled automatically. 🎉
-  Refactor JBIG2 handling to make JBIG2 decoders more testable and pluggable.
-  Fixed some typing issues around ``ObjectHelper``.
-  Exposed some pikepdf settings that were attached to the private ``_qpdf`` module
   in a new ``pikepdf.settings`` module.

v5.2.0
======

-  Avoid a few versions of setuptools_scm that were found to cause build issues. :issue:`359`
-  Improved an unhelpful error message when attemping to save a file with invalid
   encryption settings. :issue:`341`
-  Added a workaround for XMP metadata blocks that are missing the expected namespace
   tag. :issue:`349`
-  Minor improvements to code coverage, type checking, and removed some deprecated
   private methods.

v5.1.5
======

-  Fixed removal of necessary package ``packaging``. Needed for import.

v5.1.4
======

-  Reorganized release notes so they are better presented in Sphinx documentation.
-  Remove all upper bound version constraints.
-  Replace documentation package sphinx-panels with sphinx-design. Downstream
   maintainers will need to adjust this in documentation.
-  Removed use of deprecated pkg_resources and replaced with importlib (and, where
   necessary for backward compatibility, importlib_metadata).
-  Fixed some broken links in the documentation and READMEs.

v5.1.3
======

-  Fixed issue with saving files that contained JBIG2 images with null DecodeParms.
   :issue:`317`
-  Use cibuildwheel 2.4.0 and update settings to publish PyPy 3.8 binary wheels for
   manylinux platforms.

v5.1.2
======

-  Fixed test suite failures with Pillow 9.1.0. :issue:`328`

v5.1.1
======

-  Fixes to pyproject.toml to support PEP-621 changes. :issue:`323`
-  Fixed assuming Homebrew was present on certain macOS systems; and more generally,
   turn off setup shims when it seems like a maintainer is involved. :issue:`322`

v5.1.0
======

-  Rebuild against QPDF 10.6.3.
-  Improvements to Makefile for Apple Silicon wheels.

v5.0.1
======

-  Fixed issue where Pdf.check() would report a failure if JBIG2 decoder was not
   installed and the PDF contains JBIG2 content.

v5.0.0
======

-  Some errors and inconsistencies are in the "pdfdoc" encoding provided by pikepdf
   have been corrected, in conjunction with fixes in libqpdf.
-  libqpdf 10.6.2 is required.
-  Previously, looking up the number of a page, given the page, required a linear
   search of all pages. We now use a newer QPDF API that allows quicker lookups.
