<!-- SPDX-FileCopyrightText: 2022 James R. Barlow -->
<!-- SPDX-License-Identifier: MPL-2.0 -->

# pikepdf

**Read, write, repair, and transform PDFs in Python -- powered by qpdf.**

[![Build Status](https://github.com/pikepdf/pikepdf/actions/workflows/build.yml/badge.svg)](https://github.com/pikepdf/pikepdf/actions/workflows/build.yml) [![PyPI](https://img.shields.io/pypi/v/pikepdf.svg)](https://pypi.org/project/pikepdf/) ![PyPI - Python Version](https://img.shields.io/pypi/pyversions/pikepdf)  ![PyPI - License](https://img.shields.io/pypi/l/pikepdf) ![PyPI - Downloads](https://img.shields.io/pypi/dm/pikepdf)  [![codecov](https://codecov.io/gh/pikepdf/pikepdf/branch/main/graph/badge.svg?token=8FJ755317J)](https://codecov.io/gh/pikepdf/pikepdf)

pikepdf is based on [qpdf](https://github.com/qpdf/qpdf), a mature, actively maintained C++ library for PDF manipulation and repair.

Python + qpdf = "py" + "qpdf" = "pyqpdf", which looks like a dyslexia test. Say it out loud, and it sounds like "pikepdf".

```python
import pikepdf

# Open a PDF -- pikepdf (via qpdf) automatically repairs structural damage
with pikepdf.Pdf.open('input.pdf') as pdf:
    num_pages = len(pdf.pages)
    del pdf.pages[-1]
    pdf.save('output.pdf')
```

## Installation

```bash
pip install pikepdf
```

Binary wheels are available for all common platforms -- Linux, macOS, and Windows on both x86-64 and ARM64/Apple Silicon -- including free-threaded (no-GIL) CPython 3.14. No compiler required.

For building from source, see [installation](https://pikepdf.readthedocs.io/en/latest/source_build.html). Commercial support is available.

## What Can pikepdf Do?

### Manipulate pages

Merge, split, rotate, and rearrange pages across PDFs.

```python
from pikepdf import Pdf

# Merge multiple PDFs
with Pdf.new() as merged:
    for filename in ['first.pdf', 'second.pdf', 'third.pdf']:
        src = Pdf.open(filename)
        merged.pages.extend(src.pages)
    merged.save('merged.pdf')
```

```python
# Rotate all pages in a document
with Pdf.open('input.pdf') as pdf:
    for page in pdf.pages:
        page.rotate(180, relative=True)
    pdf.save('rotated.pdf')
```

### Edit metadata

Read and write XMP metadata and DocumentInfo, with automatic synchronization between the two.

```python
import pikepdf

with pikepdf.open('report.pdf') as pdf:
    with pdf.open_metadata() as meta:
        meta['dc:title'] = 'Quarterly Report'
        meta['dc:creator'] = ['Author Name']
    pdf.save('updated.pdf')
```

### Extract images

Extract images losslessly from PDFs -- without re-encoding JPEGs or other compressed formats.

```python
from pikepdf import Pdf, PdfImage

with Pdf.open('document.pdf') as pdf:
    for page in pdf.pages:
        for name, raw_image in page.images.items():
            image = PdfImage(raw_image)
            image.extract_to(fileprefix='output')
```

### Encrypt and decrypt

Open password-protected PDFs and save with encryption (AES-256, AES-128, or RC4).

```python
import pikepdf

# Open an encrypted PDF
with pikepdf.open('protected.pdf', password='secret') as pdf:
    pdf.save('decrypted.pdf')

# Save with encryption
with pikepdf.open('input.pdf') as pdf:
    pdf.save('encrypted.pdf', encryption=pikepdf.Encryption(
        user='readpassword', owner='adminpassword'
    ))

# Remove encryption if user password is not set
with pikepdf.open('protected.pdf') as pdf:
    pdf.save('decrypted.pdf', encryption=False)
```

(Digital signature-based encryption is not currently supported.)

### Linearize to improve browser performance

Create "fast web view" PDFs optimized for streaming delivery.

```python
with pikepdf.open('input.pdf') as pdf:
    pdf.save('web_optimized.pdf', linearize=True)
```

### Access PDF objects directly

Use a Pythonic API that mirrors the PDF specification -- dictionaries, arrays, streams, and names map directly to Python types.

```python
from pikepdf import Pdf, Name

with Pdf.open('input.pdf') as pdf:
    page = pdf.pages[0]
    page.MediaBox               # e.g. [0, 0, 612, 792]
    page.Resources.XObject      # image and form XObjects on this page
    page.Rotate = 90            # set page rotation directly
```

### Use qpdf's Job API

Access qpdf's full command-line capabilities programmatically from Python.

```python
from pikepdf import Job

# Check a PDF for errors
Job(['pikepdf', '--check', 'document.pdf']).run()

# Or use qpdf's JSON job interface
Job({'inputFile': 'input.pdf', 'outputFile': 'output.pdf', 'linearize': ''}).run()
```

## Key Features

- **Built on qpdf** -- backed by a mature, battle-tested C++ PDF library
- **Automatic PDF repair** -- silently fixes many types of PDF damage on open
- **PDF/A compliance** -- modify PDFs without breaking PDF/A conformance
- **XMP metadata editing** -- full read/write support for XMP and DocumentInfo
- **Encryption support** -- open and save password-protected PDFs (AES-256, AES-128, RC4)
- **Linearization** -- create "fast web view" PDFs for efficient streaming
- **Pythonic API** -- dictionary-style access to PDF objects, list-style page access
- **Lossless image extraction** -- extract and replace images without re-encoding
- **Content stream inspection** -- parse and manipulate page content at the operator level
- **Object-level manipulation** -- work directly with PDF objects per the specification
- **Jupyter integration** -- render PDF and page previews inline in notebooks
- **Binary wheels everywhere** -- pre-built for Linux, macOS, Windows (x86-64 and ARM64), including free-threaded CPython 3.14
- **Liberal license** -- MPL-2.0, compatible with most open and closed source projects

## When to Use pikepdf

pikepdf is a great fit when you need to:

- Repair, sanitize, or normalize damaged or malformed PDFs
- Merge, split, rotate, crop, or rearrange pages
- Edit PDF metadata (XMP, DocumentInfo) programmatically
- Build tools or libraries that operate on existing PDFs
- Preserve PDF/A or other standard compliance while modifying documents
- Work with encrypted PDFs
- Perform low-level PDF surgery (object and stream manipulation)
- Optimize PDFs for web delivery (linearization)

pikepdf is probably not what you want if you need to:

- Generate PDFs from HTML or templates -- consider [weasyprint](https://weasyprint.org/) or [reportlab](https://www.reportlab.com/)
- Render PDFs to images -- consider [PyMuPDF](https://pymupdf.readthedocs.io/) or [pypdfium2](https://github.com/pypdfium2-team/pypdfium2)
- Extract text or tables from PDFs -- consider [pdfminer.six](https://github.com/pdfminer/pdfminer.six) or [pdfplumber](https://github.com/jsvine/pdfplumber)

## PDF Libraries in Python

Python has several PDF libraries, each with different strengths. [pypdf](https://pypdf.readthedocs.io/) is pure Python and well-suited for straightforward PDF tasks without compiled dependencies. [pypdfium](https://pypdfium2.readthedocs.io/) for permissively licensed PDF rendering.
 [PyMuPDF](https://pymupdf.readthedocs.io/) offers comprehensive rendering and text extraction. pikepdf focuses on correctness, repair, and low-level manipulation through qpdf, under the permissive MPL-2.0 license.

## Testimonials

> I decided to try writing a quick Python program with pikepdf to automate [something] and it "just worked". --Jay Berkenbilt, creator of qpdf

> "Thanks for creating a great pdf library, I tested out several and this is the one that was best able to work with whatever I threw at it." --@cfcurtis

## Used By

* [OCRmyPDF](https://github.com/ocrmypdf/OCRmyPDF) uses pikepdf to graft OCR text layers onto existing PDFs, to examine the contents of input PDFs, and to optimize PDFs.

* [PDF Arranger](https://github.com/jeromerobert/pdfarranger) is a small Python application that provides a graphical user interface to rotate, crop and rearrange PDFs.

* [PDFStitcher](https://github.com/cfcurtis/sewingutils) is a utility for stitching PDF pages into a single document (i.e. N-up or page imposition).

## Documentation

Full documentation is available at [pikepdf.readthedocs.io](https://pikepdf.readthedocs.io/en/latest/). For the latest changes, see the [release notes](https://pikepdf.readthedocs.io/en/latest/releasenotes/index.html).

## Contributing

Contributions are welcome! If you'd like to make a contribution, see the [Contributing Guidelines](https://pikepdf.readthedocs.io/en/latest/references/contributing.html)

## License

pikepdf is licensed under the [Mozilla Public License 2.0](https://www.mozilla.org/en-US/MPL/2.0/) license (MPL-2.0) that can be found in the LICENSE file. By using, distributing, or contributing to this project, you agree to the terms and conditions of this license. MPL 2.0 permits you to combine the software with other work, including commercial and closed source software, but asks you to publish source-level modifications you make to pikepdf itself.

Some components of the project may be under other license agreements, as indicated in their SPDX license header or the [`REUSE.toml`](REUSE.toml) file.
