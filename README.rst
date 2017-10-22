pikepdf
=======

**pikepdf** is a Python library allowing creation, manipulation and repair of
PDF files. It is provides a wrapper around `QPDF <https://github.com/qpdf/qpdf>`_.

Python + QPDF = "py" + "qpdf" = "pyqpdf", which looks like a dyslexia test. Say it
out loud, and it sounds like "pikepdf".

**This is in early development. Expect breakage.**

Python 3.5 and 3.6 are fully supported.

Python 2.7 and earlier versions of Python 3 are not currently supported but 
is probably not difficult to achieve. Pull requests are welcome.

This library is similar to PyPDF2 and pdfrw – it provides low level access to PDF
features and allows editing and content transformation of existing PDFs. If you
don't need to read existing PDFs and just want to produce PDF output, reportlab
or wkhtmltopdf might be more suitable.

Installation
------------

pikepdf requires qpdf version 7.0 or higher.

**On Unix (Linux, macOS)**

A C++11 compliant compiler is required, which includes most recent versions of
GCC and clang.

-  clone this repository
-  ``pip install ./pikepdf``

**On Windows (Requires Visual Studio 2015)**

-  For Python 3.5:

    -  clone this repository
    -  ``pip install ./pikepdf``

-  For earlier versions of Python, including Python 2.7:

pikepdf requires a C++11 compliant compiler (i.e. Visual Studio 2015 on
Windows). Running a regular ``pip install`` command will detect the
version of the compiler used to build Python and attempt to build the
extension with it. We must force the use of Visual Studio 2015.

::
    - clone this repository
    - `"%VS140COMNTOOLS%\..\..\VC\vcvarsall.bat" x64`
    - `set DISTUTILS_USE_SDK=1`
    - `set MSSdk=1`
    - `pip install ./python_example`

Note that this requires the user building ``python_example`` to have
registry edition rights on the machine, to be able to run the
``vcvarsall.bat`` script.

Windows runtime requirements
----------------------------

On Windows, the Visual C++ 2015 redistributable packages are a runtime
requirement for this project. It can be found
`here <https://www.microsoft.com/en-us/download/details.aspx?id=48145>`__.

Building the documentation
--------------------------

Documentation for the example project is generated using Sphinx. Sphinx
has the ability to automatically inspect the signatures and
documentation strings in the extension module to generate beautiful
documentation in a variety formats. The following command generates
HTML-based reference documentation; for other formats please refer to
the Sphinx manual:

-  ``cd pikepdf/docs``
-  ``make html``


License
-------

pikepdf is provided under the `Mozilla Public License 2.0 <https://www.mozilla.org/en-US/MPL/2.0/>`_
license (MPL) that can be found in the LICENSE file. By using, distributing, or
contributing to this project, you agree to the terms and conditions of this license.

`Informally <https://www.mozilla.org/en-US/MPL/2.0/FAQ/>`_, MPL 2.0 is a not a "viral" license.
It may be combined with other work, including commercial software. However, you must disclose your modifications
to pikepdf in source code form. In other works, fork this repository on Github or elsewhere and commit your 
contributions there, and you've satisfied the license.

The ``tests/resources/copyright`` file describes licensing terms for the test
suite and the provenance of test resources.
