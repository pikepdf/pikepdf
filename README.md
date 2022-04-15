pikepdf
=======

**pikepdf** is a Python library for reading and writing PDF files.

[![Build Status](https://github.com/pikepdf/pikepdf/actions/workflows/build_wheels.yml/badge.svg)](https://github.com/pikepdf/pikepdf/actions/workflows/build_wheels.yml) [![PyPI](https://img.shields.io/pypi/v/pikepdf.svg)](https://pypi.org/project/pikepdf/) ![PyPI - Python Version](https://img.shields.io/pypi/pyversions/pikepdf) ![PyPy](https://img.shields.io/badge/PyPy-3.7-blue) [![Language grade: Python](https://img.shields.io/lgtm/grade/python/g/pikepdf/pikepdf.svg?logo=lgtm&logoWidth=18)](https://lgtm.com/projects/g/pikepdf/pikepdf/context:python) [![Language grade: C/C++](https://img.shields.io/lgtm/grade/cpp/g/pikepdf/pikepdf.svg?logo=lgtm&logoWidth=18)](https://lgtm.com/projects/g/pikepdf/pikepdf/context:cpp) ![PyPI - License](https://img.shields.io/pypi/l/pikepdf) ![PyPI - Downloads](https://img.shields.io/pypi/dm/pikepdf)  [![codecov](https://codecov.io/gh/pikepdf/pikepdf/branch/master/graph/badge.svg?token=8FJ755317J)](https://codecov.io/gh/pikepdf/pikepdf)

pikepdf is based on [QPDF](https://github.com/qpdf/qpdf), a powerful PDF manipulation and repair library.

Python + QPDF = "py" + "qpdf" = "pyqpdf", which looks like a dyslexia test. Say it out loud, and it sounds like "pikepdf".

```python
# Elegant, Pythonic API
with pikepdf.open('input.pdf') as pdf:
    num_pages = len(pdf.pages)
    del pdf.pages[-1]
    pdf.save('output.pdf')
```

**To install:**

```bash
pip install pikepdf
```

For users who want to build from source, see [installation](https://pikepdf.readthedocs.io/en/latest/index.html).

pikepdf is [documented](https://pikepdf.readthedocs.io/en/latest/index.html) and actively maintained. Commercial support is available. We support just about everything
x86-64, including PyPy, and Apple Silicon on a best effort basis.

Features
--------

This library is similar to PyPDF2 and pdfrw - it provides low level access to PDF features and allows editing and content transformation of existing PDFs. Some knowledge of the PDF specification may be helpful. It does not have the capability to render a PDF to image.

| **Feature**                                                         | **pikepdf**                                 | **PyPDF2**                                | **pdfrw**                               |
| ------------------------------------------------------------------- | ------------------------------------------- | ----------------------------------------- | --------------------------------------- |
| Editing, manipulation and transformation of existing PDFs           | ✔                                           | ✔                                         | ✔                                       |
| Based on an existing, mature PDF library                            | QPDF                                        | ✘                                         | ✘                                       |
| Implementation                                                      | C++ and Python                              | Python                                    | Python                                  |
| PDF versions supported                                              | 1.1 to 1.7                                  | 1.3?                                      | 1.7                                     |
| Python versions supported                                           | 3.7-3.10 [^1]                                    | 2.7-3.10                                   | 2.6-3.6                                 |
| Save and load password protected (encrypted) PDFs                   | ✔ (except public key)                       | ✘ (Only obsolete RC4)                     | ✘ (not at all)                          |
| Save and load PDF compressed object streams (PDF 1.5)               | ✔                                           | ✘                                         | ✘                                       |
| Creates linearized ("fast web view") PDFs                           | ✔                                           | ✘                                         | ✘                                       |
| Actively maintained                                                 | ![pikepdf commit activity][pikepdf-commits] | ![PyPDF2 commit activity][pypdf2-commits] | ![pdfrw commit activity][pdfrw-commits] |
| Test suite coverage                                                 | ![codecov][codecov]                         | ![pypdf2-codecov][pypdf2-codecov]         | unknown                                 |
| Creates PDFs that pass PDF validation tests                         | ✔                                           | ✘                                         | ?                                       |
| Modifies PDF/A without breaking PDF/A compliance                    | ✔                                           | ✘                                         | ?                                       |
| Automatically repairs PDFs with internal errors                     | ✔                                           | ✘                                         | ✘                                       |
| PDF XMP metadata editing                                            | ✔                                           | read-only                                 | ✘                                       |
| Documentation                                                       | ✔                                           | ✔                                        | ✔                                       |
| Integrates with Jupyter and IPython notebooks for rapid development | ✔                                           | ✘                                         | ✘                                       |

[^1]: pikepdf 3.x and older support Python 3.6.

[pikepdf-commits]: https://img.shields.io/github/commit-activity/y/pikepdf/pikepdf.svg

[pypdf2-commits]: https://img.shields.io/github/commit-activity/y/py-pdf/PyPDF2.svg

[pdfrw-commits]: https://img.shields.io/github/commit-activity/y/pmaupin/pdfrw.svg

[codecov]: https://codecov.io/gh/pikepdf/pikepdf/branch/master/graph/badge.svg?token=8FJ755317J

[pypdf2-codecov]: https://codecov.io/gh/py-pdf/PyPDF2/branch/main/graph/badge.svg

Testimonials
------------

> I decided to try writing a quick Python program with pikepdf to automate [something] and it "just worked". –Jay Berkenbilt, creator of QPDF

> "Thanks for creating a great pdf library, I tested out several and this is the one that was best able to work with whatever I threw at it." –@cfcurtis

In Production
-------------

* [OCRmyPDF](https://github.com/jbarlow83/OCRmyPDF) uses pikepdf to graft OCR text layers onto existing PDFs, to examine the contents of input PDFs, and to optimize PDFs.

* [pdfarranger](https://github.com/jeromerobert/pdfarranger) is a small Python application that provides a graphical user interface to rotate, crop and rearrange PDFs.

* [PDFStitcher](https://github.com/cfcurtis/sewingutils) is a utility for stitching PDF pages into a single document (i.e. N-up or page imposition).

License
-------

pikepdf is provided under the [Mozilla Public License 2.0](https://www.mozilla.org/en-US/MPL/2.0/) license (MPL) that can be found in the LICENSE file. By using, distributing, or contributing to this project, you agree to the terms and conditions of this license.

[Informally](https://www.mozilla.org/en-US/MPL/2.0/FAQ/), MPL 2.0 is a not a "viral" license. It may be combined with other work, including commercial software. However, you must disclose your modifications *to pikepdf* in source code form. In other works, fork this repository on GitHub or elsewhere and commit your contributions there, and you've satisfied your obligations. MPL 2.0 is compatible with the GPL and LGPL - see the [guidelines](https://www.mozilla.org/en-US/MPL/2.0/combining-mpl-and-gpl/) for notes on use in GPL.

The [`debian/copyright`](/debian/copyright) file describes licensing terms for the test suite and the provenance of test resources.
