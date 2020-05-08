pikepdf
=======

**pikepdf** is a Python library for reading and writing PDF files.

[![Build Status](https://dev.azure.com/jim0585/pikepdf/_apis/build/status/pikepdf.pikepdf?branchName=master)](https://dev.azure.com/jim0585/pikepdf/_build/latest?definitionId=1&branchName=master) [![PyPI](https://img.shields.io/pypi/v/pikepdf.svg)](https://pypi.org/project/pikepdf/) ![PyPI - Python Version](https://img.shields.io/pypi/pyversions/pikepdf) [![Language grade: Python](https://img.shields.io/lgtm/grade/python/g/pikepdf/pikepdf.svg?logo=lgtm&logoWidth=18)](https://lgtm.com/projects/g/pikepdf/pikepdf/context:python) [![Language grade: C/C++](https://img.shields.io/lgtm/grade/cpp/g/pikepdf/pikepdf.svg?logo=lgtm&logoWidth=18)](https://lgtm.com/projects/g/pikepdf/pikepdf/context:cpp)

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

pikepdf is [documented](https://pikepdf.readthedocs.io/en/latest/index.html) and actively maintained. Commercial support is available.

Features
--------

This library is similar to PyPDF2 and pdfrw - it provides low level access to PDF features and allows editing and content transformation of existing PDFs. Some knowledge of the PDF specification may be helpful. It does not have the capability to render a PDF to image.

| **Feature**                                                         | **pikepdf**                                 | **PyPDF2**                                | **pdfrw**                               |
| ------------------------------------------------------------------- | ------------------------------------------- | ----------------------------------------- | --------------------------------------- |
| Editing, manipulation and transformation of existing PDFs           | ✔                                           | ✔                                         | ✔                                       |
| Based on an existing, mature PDF library                            | QPDF                                        | ✘                                         | ✘                                       |
| Implementation                                                      | C++ and Python                              | Python                                    | Python                                  |
| PDF versions supported                                              | 1.1 to 1.7                                  | 1.3?                                      | 1.7                                     |
| Python versions supported                                           | 3.5-3.8                                     | 2.6-3.6                                   | 2.6-3.6                                 |
| Save and load password protected (encrypted) PDFs                   | ✔ (except public key)                       | ✘ (Only obsolete RC4)                     | ✘ (not at all)                          |
| Save and load PDF compressed object streams (PDF 1.5)               | ✔                                           | ✘                                         | ✘                                       |
| Creates linearized ("fast web view") PDFs                           | ✔                                           | ✘                                         | ✘                                       |
| Actively maintained                                                 | ![pikepdf commit activity][pikepdf-commits] | ![PyPDF2 commit activity][pypdf2-commits] | ![pdfrw commit activity][pdfrw-commits] |
| Test suite coverage                                                 | ~89%                                        | very low                                  | unknown                                 |
| Creates PDFs that pass PDF validation tests                         | ✔                                           | ✘                                         | ?                                       |
| Modifies PDF/A without breaking PDF/A compliance                    | ✔                                           | ✘                                         | ?                                       |
| Automatically repairs PDFs with internal errors                     | ✔                                           | ✘                                         | ✘                                       |
| PDF XMP metadata editing                                            | ✔                                           | read-only                                 | ✘                                       |
| Documentation                                                       | ✔                                           | ✘                                         | ✔                                       |
| Integrates with Jupyter and IPython notebooks for rapid development | ✔                                           | ✘                                         | ✘                                       |


[pikepdf-commits]: https://img.shields.io/github/commit-activity/y/pikepdf/pikepdf.svg

[pypdf2-commits]: https://img.shields.io/github/commit-activity/y/mstamy2/PyPDF2.svg

[pdfrw-commits]: https://img.shields.io/github/commit-activity/y/pmaupin/pdfrw.svg

In Production
-------------

* [OCRmyPDF](https://github.com/jbarlow83/OCRmyPDF) uses pikepdf to graft OCR text layers onto existing PDFs, to examine the contents of input PDFs, and to optimize PDFs.

* [pdfarranger](https://github.com/jeromerobert/pdfarranger) is a small Python application that provides a graphical user interface to rotate, crop and rearrange PDFs.

License
-------

pikepdf is provided under the [Mozilla Public License 2.0](https://www.mozilla.org/en-US/MPL/2.0/) license (MPL) that can be found in the LICENSE file. By using, distributing, or contributing to this project, you agree to the terms and conditions of this license.

[Informally](https://www.mozilla.org/en-US/MPL/2.0/FAQ/), MPL 2.0 is a not a "viral" license. It may be combined with other work, including commercial software. However, you must disclose your modifications *to pikepdf* in source code form. In other works, fork this repository on GitHub or elsewhere and commit your contributions there, and you've satisfied your obligations. MPL 2.0 is compatible with the GPL and LGPL - see the [guidelines](https://www.mozilla.org/en-US/MPL/2.0/combining-mpl-and-gpl/) for notes on use in GPL.

The [`debian/copyright`](/debian/copyright) file describes licensing terms for the test suite and the provenance of test resources.
