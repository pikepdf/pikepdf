Tutorial
========

In contrast to better known PDF libraries, pikepdf uses a single object to 
represent a PDF, whether, reading, writing or merging. We have cleverly named
this :class:`pikepdf.PDF`.

.. code-block:: python

   from pikepdf import PDF
   new_pdf = PDF.new()
   sample_pdf = PDF.open('sample.pdf')
   sample_pdf.save('sample2.pdf')

You may of course use ``from pikepdf import PDF as ...`` if the short class 
name conflicts.

The PDF class API follows the example of the widely-used 
`Pillow image library <https://pillow.readthedocs.io/en/4.2.x/>`_. For clarity
there is no default constructor since the arguments used for creation and
opening are different.

Inspecting the root object
--------------------------

Open a PDF and see what is inside the root object.

.. code-block:: python

   >>> example = PDF.open('tests/resources/sandwich.pdf')
   >>> example.root
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

Like every PDF, the root object is a PDF dictionary that describes where
the rest of the PDF content is. The angle brackets indicate that this
complex object cannot be built as a Python expression.

How many pages are in this PDF? You can access items using attribute 
notation...

.. code-block:: python

   >>> example.root.Pages.Count
   1

or dictionary lookup notation...

.. code-block:: python

   >>> example.root['/Pages']['/Count']
   1

Attribute notation is convenient, but not robust if elements are missing.
For elements that are not always present, you can even use ``.get()`` on
the PDF dictionary to specify a fallback.

In general a PDF dictionary's keys must be strings beginning with "/"
followed by a capital letter. When you access an attribute with a name
beginning with a capital letter, pikepdf will check the dictionary for
that key. For the rare PDF keys that don't follow this convention, you
must use standard dictionary notation.

Retrieving pages
----------------

The Root object provides data on the overall document, and it exposes pages.
However, sometimes PDFs organize their pages in a complex hierarchy. Because
this isn't always present, code that manipulates pages through the Root
object will be fragile.

Instead, use the :attr:`pikepdf.PDF.pages` accessor.

.. code-block:: python

   >>> example.pages[0]


PDF Stream objects
------------------

Let's read the metadata, which the PDF helpful tells us is coded in XML,
and is a :class:`pikepdf.Object.Stream`. A ``Stream`` is a PDF construct
that works like a dictionary with a binary string attached.

.. code-block:: python

   >>> raw = example.root.Metadata.read_stream_data()
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


