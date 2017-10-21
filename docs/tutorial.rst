Tutorial
========

In contrast to better known PDF libraries, pikepdf uses a single object to 
represent a PDF, whether, reading, writing or merging. We have cleverly named
this :class:`pikepdf.PDF`.

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
opening are different.

Manipulating pages
------------------

pikepdf presents the pages in a PDF through the ``Pdf.pages`` property, which
follows (most of) the ``list`` protocol.

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

.. note::

   Because of technical limitations in underlying libraries, pikepdf keeps the
   original PDF from which a page from open, even if the reference to the PDF
   is garbage collected. In the first example above, because ``report`` is
   borrowing pages from ``appendix``, ``appendix`` will be kept alive until
   ``report`` goes out of scope.

.. warning::

   It is technically possible, but not recommended, to manipulate pages via 
   the PDF /Root object. The reason it is not recommended is that PDFs 
   optionally can have a hierarchical tree of page information that may become
   inconsistent if not manipulated properly. It is far easier to use ``.pages``
   and let pikepdf (actually, libqpdf) maintain the internal structures.


Inspecting the PDF Root object
------------------------------

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

Like every PDF, the /Root object is a PDF dictionary that describes where
the rest of the PDF content is. The angle brackets indicate that this
complex object cannot be built as a Python expression.

How many pages are in this PDF? You can access items using attribute 
notation...

.. code-block:: python

   >>> example.Root.Pages.Count
   1

or dictionary lookup notation...

.. code-block:: python

   >>> example.Root['/Pages']['/Count']
   1

Attribute notation is convenient, but not robust if elements are missing.
For elements that are not always present, you can even use ``.get()`` on
the PDF dictionary to specify a fallback.

In general a PDF dictionary's keys must be strings beginning with "/"
followed by a capital letter. When you access an attribute with a name
beginning with a capital letter, pikepdf will check the dictionary for
that key. For the rare PDF keys that don't follow this convention, you
must use standard dictionary notation.


PDF Stream objects
------------------

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

You could explore that XML packet further using the standard library's 
``xml.etree.ElementTree`` or your XML parser of choice.


