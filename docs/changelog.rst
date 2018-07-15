.. _changelog:

Changelog
#########

pikepdf releases use the `semantic versioning <http://semver.org>`_ policy.

Since 1.0 has not been released, this means **breaking changes can occur at any time** and the **public API is not yet stable**. For the moment a minor version change is known to be breaking, and a patch level change shouldn't be breaking.

v0.3.0
======

Breaking
--------

* Modified ``Object.write`` method signature to require ``filter`` and ``decode_parms`` as keyword arguments
* Implement automatic type conversion from the PDF Null type to ``None``
* Removed ``Object.unparse_resolved`` in favor of ``Object.unparse(resolved=True)``
* libqpdf 8.0.2 is now required at minimum

Updates
-------

* Improved IPython/Jupyter interface to directly export temporary PDFs
* Updated to qpdf 8.1.0 in wheels
* Added Python 3.7 support for Windows
* Added a number of missing options from QPDF to ``Pdf.open`` and ``Pdf.save``
* Added ability to delete a slice of pages
* Began using Jupyter notebooks for documentation

v0.2.2
======

* Added Python 3.7 support to build and test (not yet available for Windows, due to lack of availability on Appveyor)
* Removed setter API from ``PdfImage`` because it never worked anyway
* Improved handling of ``PdfImage`` with trivial palettes

v0.2.1
======

* ``Object.check_owner`` renamed to ``Object.is_owned_by``
* ``Object.objgen`` and ``Object.get_object_id`` are now public functions
* Major internal reorganization with ``pikepdf.models`` becoming the submodule that holds support code to ease access to PDF objects as opposed to wrapping QPDF.

v0.2.0
======

* Implemented automatic type conversion for ``int``, ``bool`` and ``Decimal``, eliminating the ``pikepdf.{Integer,Boolean,Real}`` types. Removed a lot of associated numerical code.

Everything before v0.2.0 can be considered too old to document.
