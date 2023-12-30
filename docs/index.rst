pikepdf Documentation
=====================

.. figure:: /images/pike.png
   :align: right
   :alt: A northern pike
   :figwidth: 30%

   A northern pike, or *esox lucius*.

**pikepdf** is a Python library allowing creation, manipulation and repair of
PDFs. It provides a Pythonic wrapper around the C++ PDF content transformation
library, `QPDF <https://github.com/qpdf/qpdf>`_.

Python + QPDF = "py" + "qpdf" = "pyqpdf", which looks like a dyslexia test and
is no fun to type. But say "pyqpdf" out loud, and it sounds like "pikepdf".

At a glance
-----------

pikepdf is a library intended for developers who want to create, manipulate, parse,
repair, and abuse the PDF format. It supports reading and write PDFs, including
creating from scratch. Thanks to QPDF, it supports linearizing PDFs and access
to encrypted PDFs.

.. code-block:: python

   # Rotate all pages in a file by 180 degrees
   import pikepdf

   with pikepdf.Pdf.open('test.pdf') as my_pdf:
       for page in my_pdf.pages:
           page.rotate(180, relative=True)
       my_pdf.save('test-rotated.pdf')

It is a low level library that requires knowledge of PDF internals and some
familiarity with the `PDF specification
<https://opensource.adobe.com/dc-acrobat-sdk-docs/standards/pdfstandards/pdf/PDF32000_2008.pdf>`_.
It does not provide a user interface of its own.

pikepdf would help you build apps that do things like:

.. figure:: /images/pike-cartoon.png
   :align: right
   :alt: A cartoon sketch of a pike
   :figwidth: 30%

   Pike fish are tough, hard-fighting, aggressive predators.

* :ref:`Copy pages <copyother>` from one PDF into another
* :ref:`Split <splitpdf>` and :ref:`merge <mergepdf>` PDFs
* Extract content from a PDF such as :ref:`images <extract_image>`
* Replace content, such as :ref:`replacing an image <replace_image>` without
  altering the rest of the file
* Repair, reformat or :meth:`linearize <pikepdf.Pdf.save>` PDFs
* Change the size of pages and reposition content
* Optimize PDFs similar to Acrobat's features by downsampling images,
  deduplicating
* Calculate how much to charge for a scanning project based on the materials
  scanned
* Alter a PDF to meet a target specification such as PDF/A or PDF/X
* Add or modify PDF :ref:`metadata <accessmetadata>`
* Add, remove, extract, and modify PDF :ref:`attachments <attachments>`
  (i.e. embedded files)
* Create well-formed but invalid PDFs for testing purposes

What it cannot do:

.. figure:: /images/pikemen.jpg
   :align: right
   :alt: A square of pikemen, carrying pikes
   :figwidth: 30%

   Pikemen bracing for a calvary charge, carrying pikes.

.. _PyMuPDF: https://github.com/pymupdf/PyMuPDF
.. _MuPDF: https://github.com/ArtifexSoftware/mupdf
.. _pypdfium2: https://github.com/pypdfium2-team/pypdfium2
.. _python-poppler: https://github.com/cbrunet/python-poppler
.. _Ghostscript: https://github.com/ArtifexSoftware/ghostpdl

* Rasterize PDF pages for display (that is, produce an image that shows what
  a PDF page looks like at a particular resolution/zoom level) – use
  `PyMuPDF`_, `pypdfium2`_, `python-poppler`_ or `Ghostscript`_ instead
* Convert from PDF to other similar paper capture formats like epub, XPS, DjVu,
  Postscript – use `MuPDF`_ or `PyMuPDF`_
* Print to paper

If you only want to generate PDFs and not read or modify them, consider
reportlab (a "write-only" PDF generator).

Requirements
~~~~~~~~~~~~

pikepdf currently requires **Python 3.8+**. pikepdf 1.x supports Python 3.5.
pikepdf 2.x and 3.x support Python 3.6; pikepdf 4.x through 6.x support Python
3.7. Python 2.7 has never been supported.

Similar libraries
~~~~~~~~~~~~~~~~~

Unlike similar Python libraries such as pypdf, pikepdf is not pure
Python. These libraries were designed prior to Python wheels which has made Python
extension libraries much easier to work with. By leveraging the existing mature
code base of QPDF, despite being new, pikepdf is already more capable than both
in many respects – for example, it can read compress object streams, repair
damaged PDFs in many cases, and linearize PDFs. Unlike those libraries, it's not
pure Python: it is impure and proud of it.

PyMuPDF is a PDF library with impressive capabilities. However, its AGPL license
is much more restrictive than pikepdf, and its dependency on static libraries
makes it difficult to include in open source Linux or BSD distributions.

In use
~~~~~~

pikepdf is used by the same author's `OCRmyPDF
<https://github.com/jbarlow83/OCRmyPDF>`_ to inspect input PDFs, graft the
generated OCR layers on to page content, and output PDFs. Its code contains several
practical examples, particular in ``pdfinfo.py``, ``graft.py``, and
``optimize.py``. pikepdf is also used in its test suite.

.. toctree::
    :maxdepth: 2
    :caption: Introduction
    :name: intro_toc

    installation
    tutorial

.. toctree::
    :maxdepth: 1
    :caption: Release notes

    releasenotes/index.rst

.. toctree::
    :maxdepth: 2
    :caption: Topics
    :name: topics_toc

    topics/pages
    topics/page
    topics/objects
    topics/streams
    topics/content_streams
    topics/images
    topics/overlays
    topics/encoding
    topics/metadata
    topics/outlines
    topics/nametrees
    topics/attachments
    topics/pagelayout
    topics/security

.. toctree::
    :maxdepth: 2
    :caption: API
    :name: api_toc

    api/main
    api/models
    api/filters
    api/exceptions
    api/settings

.. toctree::
    :maxdepth: 2
    :caption: Reference
    :name: reference_toc

    references/arch
    references/build
    references/contributing
    references/debugging
    references/resources
