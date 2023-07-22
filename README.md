<!-- SPDX-FileCopyrightText: 2022 James R. Barlow -->
<!-- SPDX-License-Identifier: MPL-2.0 -->

pikepdf
=======

**pikepdf** is a Python library for reading and writing PDF files.

[![Build Status](https://github.com/pikepdf/pikepdf/actions/workflows/build.yml/badge.svg)](https://github.com/pikepdf/pikepdf/actions/workflows/build.yml) [![PyPI](https://img.shields.io/pypi/v/pikepdf.svg)](https://pypi.org/project/pikepdf/) ![PyPI - Python Version](https://img.shields.io/pypi/pyversions/pikepdf) ![PyPy](https://img.shields.io/badge/PyPy-3.8%20|%203.9-blue) ![PyPI - License](https://img.shields.io/pypi/l/pikepdf) ![PyPI - Downloads](https://img.shields.io/pypi/dm/pikepdf)  [![codecov](https://codecov.io/gh/pikepdf/pikepdf/branch/main/graph/badge.svg?token=8FJ755317J)](https://codecov.io/gh/pikepdf/pikepdf)

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

pikepdf is [documented](https://pikepdf.readthedocs.io/en/latest/index.html) and actively maintained. Binary wheels are available for all common platforms, both x86-64 and ARM64/Apple Silicon. For information on the latest changes, see the [release notes](https://pikepdf.readthedocs.io/en/latest/releasenotes/index.html).

Commercial support is available.

Features
--------

This library is similar to pypdf (formerly PyPDF2) - it provides low level access to PDF features and allows editing and content transformation of existing PDFs. Some knowledge of the PDF specification may be helpful. It does not have the capability to render a PDF to image.

| **Feature**                                                         | **pikepdf**                                 | **pypdf** (PyPDF2)                        |
| ------------------------------------------------------------------- | ------------------------------------------- | ----------------------------------------- |
| Editing, manipulation and transformation of existing PDFs           | ✔                                           | ✔                                         |
| Based on an existing, mature PDF library                            | QPDF                                        | ✘                                         |
| Implementation                                                      | C++ and Python                              | Python                                    |
| PDF versions supported                                              | 1.1 to 1.7                                  | 1.1 to 1.7                                |
| Save and load password protected (encrypted) PDFs                   | ✔ (except public key)                       | ✔ (except public key)                     |
| Creates linearized ("fast web view") PDFs                           | ✔                                           | ✘                                         |
| Test suite coverage                                                 | ![codecov][codecov]                         | ![codecovpypdf2][codecovpypdf]            |
| Creates PDFs that pass PDF validation tests                         | ✔                                           | ✘                                         |
| Modifies PDF/A without breaking PDF/A compliance                    | ✔                                           | ✘                                         |
| PDF XMP metadata editing                                            | ✔                                           | read-only                                 |
| Integrates with Jupyter and IPython notebooks for rapid development | ✔                                           | ✘                                         |

[codecov]: https://codecov.io/gh/pikepdf/pikepdf/branch/main/graph/badge.svg?token=8FJ755317J

[codecovpypdf]: https://codecov.io/gh/py-pdf/pypdf/branch/main/graph/badge.svg?token=id42cGNZ5Z

Testimonials
------------

> I decided to try writing a quick Python program with pikepdf to automate [something] and it "just worked". –Jay Berkenbilt, creator of QPDF

> "Thanks for creating a great pdf library, I tested out several and this is the one that was best able to work with whatever I threw at it." –@cfcurtis

In Production
-------------

* [OCRmyPDF](https://github.com/ocrmypdf/OCRmyPDF) uses pikepdf to graft OCR text layers onto existing PDFs, to examine the contents of input PDFs, and to optimize PDFs.

* [PDF Arranger](https://github.com/jeromerobert/pdfarranger) is a small Python application that provides a graphical user interface to rotate, crop and rearrange PDFs.

* [PDFStitcher](https://github.com/cfcurtis/sewingutils) is a utility for stitching PDF pages into a single document (i.e. N-up or page imposition).

License
-------

pikepdf is licensed under the [Mozilla Public License 2.0](https://www.mozilla.org/en-US/MPL/2.0/) license (MPL-2.0) that can be found in the LICENSE file. By using, distributing, or contributing to this project, you agree to the terms and conditions of this license. MPL 2.0 permits you to combine the software with other work, including commercial and closed source software, but asks you to publish source-level modifications you make to pikepdf itself.

Some components of the project may be under other license agreements, as indicated in their SPDX license header or the [`.dep5/reuse`](REUSE) file.