Tutorial
********

In contrast to better known PDF libraries, pikepdf uses a single object to 
represent a PDF, whether reading, writing or merging. We have cleverly named
this :class:`pikepdf.Pdf`.

.. code-block:: python

   from pikepdf import Pdf
   new_pdf = Pdf.new()
   sample_pdf = Pdf.open('sample.pdf')
   sample_pdf.save('sample2.pdf')

You may of course use ``from pikepdf import Pdf as ...`` if the short class 
name conflicts or ``from pikepdf import Pdf as PDF`` if you prefer uppercase.

The PDF class API follows the example of the widely-used 
`Pillow image library <https://pillow.readthedocs.io/en/4.2.x/>`_. For clarity
there is no default constructor since the arguments used for creation and
opening are different. ``Pdf.open()`` also accepts seekable streams as input,
and ``Pdf.save()`` accepts seekable streams as output.

Manipulating pages
==================

pikepdf presents the pages in a PDF through the ``Pdf.pages`` property, which
follows the ``list`` protocol. As such page numbers begin at 0.

.. code-block:: python

   # Add the appendix to the end of report 
   report = Pdf.open('report.pdf')
   appendix = Pdf.open('appendix.pdf')
   report.pages.extend(appendix.pages)
   
   # Replace page 50 (49th array index) with a rescan
   rescan_page50 = Pdf.open('page50.pdf')
   report.pages[49] = rescan_page50[0]
   report.save('report_complete.pdf')

.. code-block:: python

   # This document was scanned in reverse order; fix it
   backwards = Pdf.open('backwards.pdf')
   backwards.pages.reverse()
   backwards.save('correct-page-order.pdf')

.. code-block:: python

   # Slice the odd pages
   odd_pages = report.pages[::2]
   odd = Pdf.new()
   odd.extend(odd_pages)
   odd.save('just-odd-pages.pdf')

Because PDFs are usually numbered in counting numbers (1, 2, 3...), pikepdf
provides a convenience accessor that also uses counting numbers:

.. code-block:: python

   report.pages.p(1)       # The first page in the document
   report.pages[0]         # Also the first page in the document
   del report.pages.p(50)  # Drop page 50

To avoid confusion, the ``.p()`` accessor does not accept Python slices.

.. note::

   Because of technical limitations in underlying libraries, pikepdf keeps the
   original PDF from which a page from open, even if the reference to the PDF
   is garbage collected. In the first example above, because ``report`` is
   borrowing pages from ``appendix``, ``appendix`` will be kept alive until
   ``report`` goes out of scope.

.. warning::

   It's possible to obtain page information through the PDF ``/Root`` object as well,
   but not recommend. The internal consistency of the various ``/Page`` and ``/Pages``
   is not guaranteed when accessed in this manner, and in some PDFs the data
   structure for these is fairly cmoplex. Use the ``.pages`` interface.


Examining a page
================

.. code-block:: python

  >>> example = Pdf.open('tests/resources/congress.pdf')
  >>> page1 = example.pages[0]
  >>> page1
  <pikepdf.Object.Dictionary({
    "/Contents": pikepdf.Object.Stream(stream_dict={
        "/Length": 50
      }, data=<...>),
    "/MediaBox": [ 0, 0, 200, 304 ],
    "/Parent": <reference to /Pages>,
    "/Resources": {
      "/XObject": {
        "/Im0": pikepdf.Object.Stream(stream_dict={
            "/BitsPerComponent": 8,
            "/ColorSpace": "/DeviceRGB",
            "/Filter": [ "/DCTDecode" ],
            "/Height": 1520,
            "/Length": 192956,
            "/Subtype": "/Image",
            "/Type": "/XObject",
            "/Width": 1000
          }, data=<...>)
      }
    },
    "/Type": "/Page"
  })>

This is a PDF Dictionary of type ``/Page``. The dictionary follows most of the
mapping (Python ``dict``) protocol. Dictionary keys may be looked up using 
keys (``page1['/MediaBox']``) or attributes (``page1.MediaBox``). Consult
the PDF reference manual to determine which attributes are optional or required.

Attribute notation is convenient, but not robust if elements are missing.
For elements that are not always present, you can use ``.get()``, behaves like
``dict.get()`` in core Python.

In general a PDF dictionary's keys must be strings beginning with "/"
followed by a capital letter. When you access an attribute with a name
beginning with a capital letter, pikepdf will check the dictionary for
that key. For the rare PDF keys that don't follow this convention, you
must use standard dictionary notation.

The angle brackets in the output indicate that this object cannot be 
constructed with a Python expression because it contains indirect objects 
(possibly including a self-reference). When angle brackets are omitted from the 
``repr()`` of a pikepdf object, then the object can be replicated with a Python 
expression, that is ``eval(repr(x)) == x``.

In Jupyter and IPython, pikepdf will instead attempt to rasterize a preview of
the PDF page, if the "mupdf-tools" package is installed. Use ``repr(page)`` to 
see the contents.

For example, this page's MediaBox is a direct object.

.. code-block:: python

  >>> import pikepdf
  >>> page1.MediaBox
  pikepdf.Object.Array([ 0, 0, 200, 304 ])

  >>> pikepdf.Object.Array([ 0, 0, 200, 304 ])
  pikepdf.Object.Array([ 0, 0, 200, 304 ])

The page's ``/Contents`` key contains instructions for drawing the page content.
Also attached to this page is a ``/Resources`` dictionary, which contains a single
XObject image. The image is compressed with the ``/DCTDecode`` filter, meaning it is
encoded as a JPEG.

Viewing images
--------------

Let's see that JPEG. 

.. code-block:: python

  >>> from pikepdf import PdfImage
  >>> pdfimage = PdfImage(page1.Resources.XObject['/Im0'])
  >>> pdfimage.show()

One can also use the PdfImage wrapper to convert the image to a Python Pillow
image.

Jupyter and IPython will automatically show the graphically representation of
the image, as below:

.. code-block:: python
 
   In [1] : pdfimage
  Out [1] : [the image appears here]

.. note::

  This simple example PDF displays a single full page image. Some PDF creators
  will paint a page using multiple images, and features such as layers,
  transparency and image masks. Accessing the first image on a page is like an
  HTML parser that scans for the first ``<img src="">`` tag it finds. A lot
  more could be happening. There can be multiple images drawn multiple times 
  on a page, vector art, overdrawing, masking, and transparency. A set of resources
  can be grouped together in a "Form XObject" (not to be confused with a PDF Form),
  and drawn at all once. Images can be referenced by multiple pages.

Replacing an image
------------------

See ``test_image_access.py::test_image_replace``.

Inspecting the PDF Root object
==============================

Open a PDF and see what is inside the /Root object.

.. code-block:: python

   >>> example = Pdf.open('tests/resources/sandwich.pdf')
   >>> example.Root
   <pikepdf.Object.Dictionary({
    '/Metadata': pikepdf.Object.Stream(stream_dict={
        '/Length': 3308,
        '/Subtype': /XML,
        '/Type': /Metadata
    }, data=<...>),
    '/Pages': {
      '/Count': 1,
      '/Kids': [ {
        '/Contents': pikepdf.Object.Stream(stream_dict={
            '/Length': 44
          }, data=<...>),
        '/MediaBox': [ 0, 0, Decimal('545.2800'), Decimal('443.5200') ],
        '/Parent': <circular reference>,
        '/Resources': {
          '/XObject': {
            '/Im0': pikepdf.Object.Stream(stream_dict={
                '/BitsPerComponent': 8,
                '/ColorSpace': /DeviceRGB,
                '/Filter': [ /FlateDecode ],
                '/Height': 1848,
                '/Length': 291511,
                '/Subtype': /Image,
                '/Type': /XObject,
                '/Width': 2272
              }, data=<...>)
          }
        },
        '/Type': /Page
      } ],
      '/Type': /Pages
    },
    '/Type': /Catalog
  })>

The /Root object is a PDF dictionary that describes where
the rest of the PDF content is. 


PDF Stream objects
==================

Let's read the metadata, which the PDF helpful tells us is coded in XML,
and is a :class:`pikepdf.Object.Stream`. A ``Stream`` is a PDF construct
that works like a dictionary with a binary string attached.

.. code-block:: python

   >>> raw = example.Root.Metadata.read_stream_data()
   >>> type(raw)
   bytes
   >>> print(raw.decode())
   <?xpacket begin='﻿' id='W5M0MpCehiHzreSzNTczkc9d'?>
   <?adobe-xap-filters esc="CRLF"?>
   <x:xmpmeta xmlns:x='adobe:ns:meta/' x:xmptk='XMP toolkit 2.9.1-13, framework 1.6'>
   <rdf:RDF xmlns:rdf='http://www.w3.org/1999/02/22-rdf-syntax-ns#' xmlns:iX='http://ns.adobe.com/iX/1.0/'>
   <rdf:Description rdf:about='' xmlns:pdf='http://ns.adobe.com/pdf/1.3/' pdf:Producer='GPL Ghostscript 9.21'/>
   <rdf:Description rdf:about='' xmlns:xmp='http://ns.adobe.com/xap/1.0/'><xmp:ModifyDate>2017-09-11T13:27:48-07:00</xmp:ModifyDate>
   <xmp:CreateDate>2017-09-11T13:27:48-07:00</xmp:CreateDate>
   <xmp:CreatorTool>ocrmypdf 5.3.3 / Tesseract OCR-PDF 3.05.01</xmp:CreatorTool></rdf:Description>
   <rdf:Description rdf:about='' xmlns:xapMM='http://ns.adobe.com/xap/1.0/mm/' xapMM:DocumentID='uuid:39bce560-cf4c-11f2-0000-61a4fb67ccb7'/>
   <rdf:Description rdf:about='' xmlns:dc='http://purl.org/dc/elements/1.1/' dc:format='application/pdf'><dc:title><rdf:Alt><rdf:li xml:lang='x-default'>Untitled</rdf:li></rdf:Alt></dc:title></rdf:Description>
   <rdf:Description rdf:about='' xmlns:pdfaid='http://www.aiim.org/pdfa/ns/id/' pdfaid:part='2' pdfaid:conformance='B'/></rdf:RDF>
   </x:xmpmeta>
   <?xpacket end='w'?>

That lets us see a few facts about this file. It was created by OCRmyPDF
and Tesseract OCR's PDF generator. Ghostscript was used to convert it to
PDF-A (the ``xmlns:pdfaid`` tag).

You could explore that XML packet further using the ``defusedxml``.

.. warning::

  PDFs may contain viruses, and one place they can 'live' is inside XML objects.


