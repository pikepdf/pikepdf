PDF Metadata
============

The primary metadata in a PDF is stored in an XMP (Extensible Metadata
Platform) Metadata stream, where XMP is a metadata specification in XML format.
For full information on XMP, see Adobe's `XMP Developer Center
<https://www.adobe.com/devnet/xmp.html>`_. It supercedes the older Document Info
dictionaries, which are removed in the PDF 2.0 specification. The XMP data entry
is optional and does not appear in all PDFs.

pikepdf provides an interface to ease managing XMP.

.. note::

  pikepdf's XMP interface currently relies on libexempi
  and the Python package python-xmp-toolkit. Both components are recommended
  dependencies. Windows is not currently well supported by either, so Windows
  users of pikepdf may not be able to make use of this feature.


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

Accessing metadata
------------------

You may use :meth:`pikepdf.Pdf.open_metadata` to open the metadata for reading,
and enter a ``with``-block to modify and commit changes. The ``with`` block
is to synchronize changes with Document Info.

.. ipython::
  :verbatim:

  In [1]: import pikepdf, libxmp

  In [2]: pdf = pikepdf.open('tests/resources/sandwich.pdf')

  In [3]: meta = pdf.open_metadata()

  In [4]: meta['xmp:CreatorTool']
  Out[4]: 'ocrmypdf 5.3.3 / Tesseract OCR-PDF 3.05.01'

If no XMP metadata exists, an empty object will be created.

Open metadata in a ``with`` block to open it for editing. When the block is
exited, changes are committed (updating XMP and the Document Info dictionary)
and attached to the PDF object. The PDF must still be saved. If an exception occurs in the block, changes are discarded.

.. ipython::
  :verbatim:

  In [9]: pdf = pikepdf.open('tests/resources/formxobject.pdf')

  In [10]: meta = pdf.open_metadata()

  In [11]: with pdf.open_metadata() as meta:
      ...:     meta['dc:title'] = "Let's change the title"
      ...:

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

  Note that this property merely tests if the file claims to be conformant to
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

  In [4]: example.docinfo
  Out[4]:
  pikepdf.Dictionary({
    "/CreationDate": "D:20170911132748-07'00'",
    "/Creator": "ocrmypdf 5.3.3 / Tesseract OCR-PDF 3.05.01",
    "/ModDate": "D:20170911132748-07'00'",
    "/Producer": "GPL Ghostscript 9.21"
  })

It is permitted in pikepdf to directly interact with Document Info as with
other PDF dictionaries.

You may copy from data from a Document Info object in the current PDF or another
PDF into XMP metadata.
