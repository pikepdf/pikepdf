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
