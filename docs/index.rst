pikepdf Documentation
=====================

.. figure:: /images/pike.jpg
   :align: right
   :alt: A northern pike
   :figwidth: 30%

   A northern pike, or *esox lucius*. [#img1]_

**pikepdf** is a Python library allowing creation, manipulation and repair of
PDFs. It provides a Pythonic wrapper around the C++ PDF content transformation
library, `QPDF <https://github.com/qpdf/qpdf>`_.

Python + QPDF = "py" + "qpdf" = "pyqpdf", which looks like a dyslexia test and
is no fun to type. But say "pyqpdf" out loud, and it sounds like "pikepdf".

At a glance
-----------

pikepdf is a library intended developers who want to create, manipulate, parse,
repair, and abuse the PDF format. It supports reading and write PDFs, including
creating from scratch. Thanks to QPDF, it supports linearizing PDFs and access
to encrypted PDFs.

.. code-block:: python

   # Rotate all pages in a file by 180 degrees
   import pikepdf
   my_pdf = pikepdf.Pdf.open('test.pdf')
   for page in my_pdf.pages:
      page.Rotate = 180
   my_pdf.save('test-rotated.pdf')

It is a low level library that requires knowledge of PDF internals and some
familiarity with the PDF specification [#pdfrm]_. If you just want to write
content as PDF something like reportlab may be more suitable.

pikepdf would help you build apps that do things like:

* Copy pages from one PDF into another
* Split and merge PDFs
* Extract content from a PDF such as text or images
* Replace content, such as replacing an image without altering the rest of the
  file
* Repair, reformat or linearize PDFs
* Change the size of pages and reposition content
* Optimize PDFs similar to Acrobat's features by downsampling images,
  deduplicating
* Calculate how much to charge for a scanning project based on the materials
  scanned
* Alter a PDF to meet a target specification such as PDF/A or PDF/X
* Create deliberately malformed PDFs for testing purposes

**This is experimental. Some features are missing.**

What it cannot and never will do:

* Rasterize PDF pages for display (that is, produce an image that shows what
  a PDF page looks like at a particular resolution/zoom level) – use
  Ghostscript instead
* Convert from PDF to other similar print formats like epub, XPS, DjVu,
  Postscript – use MuPDF
* Print

Architecture
------------

pikepdf currently requires **Python 3.5+**. As this is a new library there are no
plans to support Python 2.7 or older versions in the 3.x family, but pull
requests to backport would be considered.

The library uses `pybind11 <https://github.com/pybind/pybind11>`_ to bind the
C++ interface of QPDF. pybind11 was selected after evaluating Cython, CFFI and
SWIG as possible solutions. 

In addition to bindings pikepdf includes its support code, mainly to present
a clean Pythonic interface to a C++.

Unlike similar Python libraries such as PyPDF2 and pdfrw, pikepdf is not pure
Python. Both were designed prior to Python wheels which has made Python
extension libraries much easier to work with. By leveraging the existing mature
code base of QPDF, despite being new, pikepdf is already more capable than
both in some respects – for example, it can read compress object streams, 
repair damaged PDFs in many cases, and linearize PDFs. Unlike those libraries, 
it's not pure Python: it is impure and proud of it.

It's almost certainly faster than the pure Python libraries at loading and saving
PDFs.

A C++14 capable compiler is recommended to build from source, but C++11 works.


Contents:

.. toctree::
   :maxdepth: 2

   tutorial
   pikepdf

.. rubric:: References

.. [#img1] `Public domain image <https://en.wikipedia.org/wiki/File:Esox_lucius1.jpg>`_.

.. [#pdfrm] `PDF 32000-1:2008 <https://www.adobe.com/content/dam/Adobe/en/devnet/pdf/pdfs/PDF32000_2008.pdf>`_.