PDF Metadata
============

The primary metadata in a PDF is stored in an XMP (Extensible Metadata
Platform) Metadata stream, where XMP is a metadata specification in XML format.
For full information on XMP, see Adobe's `XMP Developer Center
<https://www.adobe.com/devnet/xmp.html>`_. It supercedes the older Document Info
dictionaries, which are removed in the PDF 2.0 specification. The XMP data entry
is optional and does not appear in all PDFs.

The `XMP Specification Part 1 <https://wwwimages2.adobe.com/content/dam/acom/en/devnet/xmp/pdfs/XMP%20SDK%20Release%20cc-2016-08/XMPSpecificationPart1.pdf>`_
also provides useful information.

pikepdf provides an interface to simplify viewing and making minor edits to XMP.
In particular, compound quantities may be read, but only scalar quantities can
be modified.

For more complex changes consider using the ``python-xmp-toolkit`` library and
its libexempi dependency; but note that it is not capable of synchronizing
changes to the older DocumentInfo metadata.

Inspecting the PDF Root object
------------------------------

Open a PDF and see what is inside the /Root object.

.. ipython::
  :verbatim:

   In [1]: example = Pdf.open('tests/resources/sandwich.pdf')

   In [2]: example.Root
   Out[2]:
   <pikepdf.Object.Dictionary({
    '/Metadata': pikepdf.Object.Stream(stream_dict={
        '/Length': 3308,
        '/Subtype': /XML,
        '/Type': /Metadata
    }, data=<...>),
    '/Pages': {
      ...details omitted...
    },
    '/Type': /Catalog
  })>

The /Root object is a PDF dictionary that describes where most of the rest of
the PDF content is. We can see that this PDF has a /Metadata object, instead
a stream object, which is not automatically extracted for us. pikepdf provides
an interface to manage this object, so it is not necessary to extract it.

.. _accessmetadata:

Accessing metadata
------------------

You may use :meth:`pikepdf.Pdf.open_metadata` to open the metadata for reading,
and enter a ``with``-block to modify and commit changes. The ``with`` block
is to synchronize changes with Document Info.

.. ipython::
  :verbatim:

  In [1]: pdf = pikepdf.open('tests/resources/sandwich.pdf')

  In [2]: meta = pdf.open_metadata()

  In [3]: meta['xmp:CreatorTool']
  Out[3]: 'ocrmypdf 5.3.3 / Tesseract OCR-PDF 3.05.01'

If no XMP metadata exists, an empty XMP metadata container will be created.

Open metadata in a ``with`` block to open it for editing. When the block is
exited, changes are committed (updating XMP and the Document Info dictionary)
and attached to the PDF object. The PDF must still be saved. If an exception
occurs in the block, changes are discarded.

.. ipython::
  :verbatim:

  In [4]: with pdf.open_metadata() as meta:
      ..:     meta['dc:title'] = "Let's change the title"
      ..:

Checking PDF/A conformance
--------------------------

The metadata interface can also test if a file **claims** to be conformant
to the PDF/A specification.

.. ipython::
  :verbatim:

  In [9]: pdf = pikepdf.open('tests/resources/veraPDF test suite 6-2-10-t02-pass-a.pdf')

  In [10]: meta = pdf.open_metadata()

  In [11]: meta.pdfa_status
  Out[11]: '1B'

.. note::

  Note that this property merely *tests* if the file claims to be conformant to
  the PDF/A standard. Use a tool such as veraPDF to verify conformance.

The Document Info dictionary
----------------------------

The Document Info block is an older, now deprecated object in which metadata
may be stored. If you use pikepdf's interface to modify metadata, it will
automatically modify the Document Info metadata to match changes to XMP,
where equivalent fields exist.

The Document Info is (confusingly) not attached to the /Root object.
It may be accessed using the ``.docinfo`` property. If no Document Info exists,
touching the ``.docinfo`` will properly initialize an empty one.

Here is an example of a Document Info block.

.. ipython::
  :verbatim:

  In [1]: pdf = Pdf.open('tests/resources/sandwich.pdf')

  In [2]: pdf.docinfo
  Out[2]:
  pikepdf.Dictionary({
    "/CreationDate": "D:20170911132748-07'00'",
    "/Creator": "ocrmypdf 5.3.3 / Tesseract OCR-PDF 3.05.01",
    "/ModDate": "D:20170911132748-07'00'",
    "/Producer": "GPL Ghostscript 9.21"
  })

It is permitted in pikepdf to directly interact with Document Info as with
other PDF dictionaries. However, it is better to use ``.open_metadata()``
because that make changes to both XMP and Document Info in a consistent manner.

You may copy from data from a Document Info object in the current PDF or another
PDF into XMP metadata using :meth:`pikepdf.models.PdfMetadata.load_from_docinfo`.
