Working with PDF Streams
========================

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

Of course, it would be far more convenient to use the pikepdf
:ref:`metadata` interface than manual parse this XML object. It just
so happens this is a human readable object found in most PDFs.

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
