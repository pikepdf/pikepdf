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

:func:`pikepdf.open` is a shorthand for ``Pdf.open``.

The PDF class API follows the example of the widely-used
`Pillow image library <https://pillow.readthedocs.io/en/latest/>`_. For clarity
there is no default constructor since the arguments used for creation and
opening are different. ``Pdf.open()`` also accepts seekable streams as input,
and ``Pdf.save()`` accepts streams as output.

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
   rescan_of_page50 = Pdf.open('page50.pdf')
   report.pages[49] = rescan_of_page50[0]
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

   It's possible to obtain page information through the PDF ``/Root`` object as
   well, but not recommend. The internal consistency of the various ``/Page``
   and ``/Pages`` is not guaranteed when accessed in this manner, and in some
   PDFs the data structure for these is fairly complex. Use the ``.pages``
   interface.


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

This is a PDF Dictionary of type ``/Page``, a key-value data structure much
like a Python ``dict`` or ``attrdict``. Dictionary keys may be looked up using
keys (``page1['/MediaBox']``) or attributes (``page1.MediaBox``).

The key of a PDF Dictionary is always of type :class:`pikepdf.Name` that is,
usually, an ASCII-encoded string beginning with "/" followed by a capital
letter. When you access an attribute with a name beginning with a capital
letter, pikepdf will check the dictionary for that key.

Attribute notation is convenient, but not robust if elements are missing.
For elements that are not always present, you can use ``.get()``, behaves like
``dict.get()`` in core Python.  A library such as
`glom <https://github.com/mahmoud/glom>`_ might help when working with complex
structured data that is not always present.

The angle brackets in the output indicate that this object cannot be
constructed with a Python expression because it contains a reference. When
angle brackets are omitted from the ``repr()`` of a pikepdf object, then the
object can be replicated with a Python expression, that is
``eval(repr(x)) == x``.

In Jupyter and IPython, pikepdf will instead attempt to rasterize a preview of
the PDF page, if the "mupdf-tools" package is installed. Use ``repr(page)`` to
see the contents.

For example, this page's MediaBox is a direct object. The MediaBox describes
the size of the page in PDF coordinates (1/72 inch multiplied by the value of
``/UserUnit``, if present).

.. code-block:: python

  >>> import pikepdf
  >>> page1.MediaBox
  pikepdf.Object.Array([ 0, 0, 200, 304 ])

  >>> pikepdf.Object.Array([ 0, 0, 200, 304 ])
  pikepdf.Object.Array([ 0, 0, 200, 304 ])

The page's ``/Contents`` key contains instructions for drawing the page content.
Also attached to this page is a ``/Resources`` dictionary, which contains a
single XObject image. The image is compressed with the ``/DCTDecode`` filter,
meaning it is encoded with a DCT file in the way JPEGs are. (But you can't
extract the bitstream and view it as a JPEG, because PDF strips the JFIF
header.)

.. note::

  ``/Im0`` is just a name some other software assigned to an image. Images
  can have any name.

Viewing images
--------------

pikepdf provides a helper class :class:`~pikepdf.PdfImage` for manipulating
PDF images.

.. code-block:: python

  >>> from pikepdf import PdfImage
  >>> pdfimage = PdfImage(page1.Resources.XObject['/Im0'])
  >>> pdfimage.show()

You can also inspect the properties of the image:

  >>> pdfimage.colorspace
  'RGB'

Extracting images
-----------------

Extracting images is straightforward. :meth:`~pikepdf.PdfImage.extract_to` will
extract images to streams, such as an open file. Where possible, ``extract_to``
writes compressed data directly to the stream without transcoding. The return
value is the file extension that was extracted.

.. code-block:: python

  >>> pdfimage.extract_to(stream=open('file.jpg', 'w'))

You can also retrieve the image as a Pillow image:

.. code-block:: python

  >>> pil = pdfimage.as_pil_image()

Jupyter and IPython will automatically show the graphically representation of
the image, as below:

.. code-block:: python

   In [1] : pdfimage
  Out [1] : [the image appears here]

.. note::

  This simple example PDF displays a single full page image. Some PDF creators
  will paint a page using multiple images, and features such as layers,
  transparency and image masks. Accessing the first image on a page is like an
  HTML parser that scans for the first ``<img src="">`` tag it finds. A lot more
  could be happening. There can be multiple images drawn multiple times on a
  page, vector art, overdrawing, masking, and transparency. A set of resources
  can be grouped together in a "Form XObject" (not to be confused with a PDF
  Form), and drawn at all once. Images can be referenced by multiple pages.

Replacing an image
------------------

See ``test_image_access.py::test_image_replace``.


PDF Stream objects
==================

A :class:`pikepdf.Stream` object works like a PDF dictionary with some encoded
bytes attached. The dictionary is metadata that describes how the stream is
encoded. PDF can, and regularly does, use a variety of encoding filters. A
stream can be encoded with one or more filters. Images are a type of stream
object.

Most of the interesting content in a PDF (images and content streams) are
inside page objects.

Because the PDF specification unfortunately defines several terms involve the
word stream, let's attempt to clarify:

stream object
  A PDF object that contains binary data and a metadata dictionary to describes
  it, represented as :class:`pikepdf.Stream`. In HTML this is equivalent to
  a ``<img>`` with inline image data.

object stream
  A stream object (not a typo, an object stream really is a type of stream
  object) in a PDF that contains a number of other objects in a
  PDF, grouped together for better compression. In pikepdf there is an option
  to save PDFs with this feature enabled to improve compression. Otherwise,
  this is just a detail about how PDF files are encoded.

content stream
  A stream object that contains some instructions to draw graphics
  and text on a page, or inside a Form XObject. In HTML this is equivalent to
  the HTML file itself. Content streams do not cross pages.

Form XObject
  A group of images, text and drawing commands that can be rendered elsewhere
  in a PDF as a group. This is often used when a group of objects are needed
  at different scales or multiple pages. In HTML this is like an ``<svg>``.

Reading stream objects
----------------------

Fortunately, :meth:`pikepdf.Stream.read_bytes` will apply all filters
and decode the uncompressed bytes, or throw an error if this is not possible.
:meth:`pikepdf.Stream.read_raw_bytes` provides access to the compressed bytes.

For example, we can read the XMP metadata, however it is encoded, from a PDF
with the following:

.. code-block:: python

   >>> xmp = example.root.Metadata.read_bytes()
   >>> type(xmp)
   bytes
   >>> print(xmp.decode())
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

.. note::

  The best way to manage XMP metadata is use a dedicated tool like the
  `python-xmp-toolkit <https://pypi.org/project/python-xmp-toolkit/>`_ library.
  pikepdf does not validate changes to XMP metadata.

Parsing content streams
-----------------------

When a stream object is a content stream, you probably want to parse the
content stream to interpret it.

pikepdf provides a C++ optimized content stream parser.

.. code-block:: python

  >>> pdf = pikepdf.open(input_pdf)
  >>> page = pdf.pages[0]
  >>> for operands, command in parse_content_stream(page):
  >>>     print(command)


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
