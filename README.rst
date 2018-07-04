pikepdf
=======

**pikepdf** is a Python library for reading and writing PDF files.

.. |travis| image:: https://img.shields.io/travis/pikepdf/pikepdf/master.svg?label=Linux%2fmacOS%20build
   :target: https://travis-ci.org/pikepdf/pikepdf
   :alt: Travis CI build status (Linux and macOS)

.. |windows| image:: https://img.shields.io/appveyor/ci/jbarlow83/pikepdf/master.svg?label=Windows%20build
   :target: https://ci.appveyor.com/project/jbarlow83/pikepdf
   :alt: AppVeyor CI build status (Windows)

.. |pypi| image:: https://img.shields.io/pypi/v/pikepdf.svg
   :target: https://pypi.org/project/pikepdf/
   :alt: PyPI


|travis| |windows| |pypi|

pikepdf is based on `QPDF <https://github.com/qpdf/qpdf>`_, a powerful PDF
manipulation and repair library.

Python + QPDF = "py" + "qpdf" = "pyqpdf", which looks like a dyslexia test. Say it
out loud, and it sounds like "pikepdf".

Python 3.5, 3.6 and 3.7 are fully supported.

To install:

.. code-block:: bash

    pip install pikepdf

Features:

-   Editing, manipulation and transformation of existing PDFs
-   Based on the mature, proven QPDF C++ library
-   Reading and writing encrypted PDFs, with all encryption types except public key
-   Supports all PDF compression filters
-   Supports PDF 1.3 through 1.7
-   Can create "fast web view" (linearized) PDFs
-   Creates standards compliant PDFs that pass validation in other tools
-   Automatically repairs damaged PDFs, just like QPDF
-   Can manipulate PDF/A, PDF/X and other types without losing their metadata marker
-   Implements more of the PDF specification than existing Python PDF tools
-   For convenience, renders PDF pages or embedded PDF images in Jupyter notebooks and IPython

.. code-block:: python

    # Elegant, Pythonic API
    pdf = pikepdf.open('input.pdf')
    num_pages = len(pdf.pages)
    del pdf.pages[-1]
    pdf.save('output.pdf')


pikepdf is `documented <https://pikepdf.readthedocs.io/en/latest/index.html>`_
and actively maintained. Commercial support is available.

Feature comparison
------------------

This library is similar to PyPDF2 and pdfrw - it provides low level access to PDF
features and allows editing and content transformation of existing PDFs.  Some
knowledge of the PDF specification may be helpful.  It does not have the
capability to render a PDF to image.

Python 2.7 and earlier versions of Python 3 are not currently supported but
support is probably not difficult to achieve. Pull requests are welcome.


+--------------------------------------------------+-------------+-------------------------+--------------------------+
| **Feature**                                      | **pikepdf** | **PyPDF2**              | **pdfrw**                |
+--------------------------------------------------+-------------+-------------------------+--------------------------+
| PDF versions supported                           | 1.1 to 1.7  | 1.3?                    | 1.7                      |
+--------------------------------------------------+-------------+-------------------------+--------------------------+
| Implementation speed                             | Native C++  | Python                  | Python                   |
+--------------------------------------------------+-------------+-------------------------+--------------------------+
| Python versions supported                        | 3.5-3.7     | 2.6-3.6                 | 2.6-3.6                  |
+--------------------------------------------------+-------------+-------------------------+--------------------------+
| Supports password protected (encrypted) PDFs     | ✔           | Only obsolete RC4       | ✘                        |
+--------------------------------------------------+-------------+-------------------------+--------------------------+
| Save and load PDF compressed object streams      | ✔           | ✘                       | ✘                        |
+--------------------------------------------------+-------------+-------------------------+--------------------------+
| Creates linearized ("fast web view") PDFs        | ✔           | ✘                       | ✘                        |
+--------------------------------------------------+-------------+-------------------------+--------------------------+
| Actively maintained                              | ✔           | Latest release May 2016 | Latest release Sept 2017 |
+--------------------------------------------------+-------------+-------------------------+--------------------------+
| Test suite coverage                              | ~80%        | very low                | unknown                  |
+--------------------------------------------------+-------------+-------------------------+--------------------------+
| Modifies PDF/A without breaking PDF/A compliance | ✔           | ✘                       | ?                        |
+--------------------------------------------------+-------------+-------------------------+--------------------------+
| Automatically repairs PDFs with internal errors  | ✔           | ✘                       | ✘                        |
+--------------------------------------------------+-------------+-------------------------+--------------------------+
| Documentation                                    | ✔           | ✘                       | ✔                        |
+--------------------------------------------------+-------------+-------------------------+--------------------------+

License
-------

pikepdf is provided under the `Mozilla Public License 2.0 <https://www.mozilla.org/en-US/MPL/2.0/>`_
license (MPL) that can be found in the LICENSE file. By using, distributing, or
contributing to this project, you agree to the terms and conditions of this license.
We exclude Exhibit B, so pikepdf is compatible with secondary licenses.
At your option may additionally distribute pikepdf under a secondary license.

`Informally <https://www.mozilla.org/en-US/MPL/2.0/FAQ/>`_, MPL 2.0 is a not a "viral" license.
It may be combined with other work, including commercial software. However, you must disclose your modifications
*to pikepdf* in source code form. In other works, fork this repository on Github or elsewhere and commit your
contributions there, and you've satisfied the license.

The ``tests/resources/copyright`` file describes licensing terms for the test
suite and the provenance of test resources.
