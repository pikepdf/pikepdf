.. _metadata:

PDF Metadata
============

PDF has two different types of metadata: XMP metadata, and DocumentInfo, which
is deprecated but still relevant. For backward compatibility, both should
contain the same content. pikepdf provides a convenient interface that
coordinates edits to both, but is limited to the most common metadata features.

XMP (Extensible Metadata Platform) Metadata is a metadata specification in XML
format that is used many formats other than PDF. For full information on XMP,
see Adobe's `XMP Developer Center <https://www.adobe.com/devnet/xmp.html>`_.
The `XMP Specification`_ also provides useful information.

pikepdf can read compound metadata quantities, but can only modify scalars. For
more complex changes consider using the ``python-xmp-toolkit`` library and its
libexempi dependency; but note that it is not capable of synchronizing changes
to the older DocumentInfo metadata.

.. _XMP Specification: https://wwwimages2.adobe.com/content/dam/acom/en/devnet/xmp/pdfs/XMP%20SDK%20Release%20cc-2016-08/XMPSpecificationPart1.pdf

Automatic metadata updates
--------------------------

By default pikepdf will create a XMP metadata block and set ``pdf:PDFVersion``
to a value that matches the PDF version declared elsewhere in the PDF, whenever
a PDF is saved. To suppress this behavior, save with
``pdf.save(..., fix_metadata_version=False)``.

Also by default, :meth:`Pdf.open_metadata()` will synchronize the XMP metadata
with the older document information dictionary. This behavior can also be
adjusted using keyword arguments.

.. _accessmetadata:

Accessing metadata
------------------

The XMP metadata stream is attached the PDF's root object, but to simplify
management of this, use :meth:`pikepdf.Pdf.open_metadata`. The returned
:class:`pikepdf.models.PdfMetadata` object may be used for reading, or entered
with a ``with`` block to modify and commit changes. If you use this interface,
pikepdf will synchronize changes to new and old metadata.

A PDF must still be saved after metadata is changed.

.. ipython::

  In [1]: pdf = pikepdf.open('../tests/resources/sandwich.pdf')

  In [2]: meta = pdf.open_metadata()

  In [3]: meta['xmp:CreatorTool']
  Out[3]: 'ocrmypdf 5.3.3 / Tesseract OCR-PDF 3.05.01'

If no XMP metadata exists, an empty XMP metadata container will be created.

Open metadata in a ``with`` block to open it for editing. When the block is
exited, changes are committed (updating XMP and the Document Info dictionary)
and attached to the PDF object. The PDF must still be saved. If an exception
occurs in the block, changes are discarded.

.. ipython::

  In [4]: with pdf.open_metadata() as meta:
     ...:     meta['dc:title'] = "Let's change the title"
     ...:

The list of available metadata fields may be found in the `XMP Specification`_.

Removing metadata items
-----------------------

Use ``del meta['dc:title']`` to delete a metadata entry. To remove all of the XMP
metadata, use ``del pdf.Root.Metadata``.

Checking PDF/A conformance
--------------------------

The metadata interface can also test if a file **claims** to be conformant
to the PDF/A specification.

.. ipython::

  In [9]: pdf = pikepdf.open('../tests/resources/veraPDF test suite 6-2-10-t02-pass-a.pdf')

  In [10]: meta = pdf.open_metadata()

  In [11]: meta.pdfa_status
  Out[11]: '1B'

.. note::

  Note that this property merely *tests* if the file claims to be conformant to
  the PDF/A standard. Use a tool such as veraPDF to verify conformance.

Notice for application developers
---------------------------------

If you are using pikepdf to create some kind of PDF application, you should
update the fields ``xmp:CreatorTool`` and ``pdf:Producer``. You could, for
example, set ``xmp:CreatorTool`` to your application's name and version, and
``pdf:Producer`` to pikepdf. Refer to Adobe's documentation to decide what
describes the circumstances.

This will help PDF developers identify the application that generated a
particular PDF and is valuable debugging information.

Low-level XMP metadata access
-----------------------------

You can read the raw XMP metadata if desired. For example, one could extract it and
edit it using the full featured ``python-xmp-toolkit`` library.

.. ipython::

   In [1]: xmp = pdf.root.Metadata.read_bytes()

   In [1]: type(xmp)
   Out[1]: bytes

   In [1]: print(xmp.decode())

Editing XMP with a generic XML library is probably not worth the trouble; the
semantics are fairly complex.

.. warning::

  Manually changes to XMP stream object will not be synchronized with live
  PdfMetadata object or the DocumentInfo block.

The Document Info dictionary
----------------------------

The Document Info block is an older, now deprecated object in which metadata
may be stored. The Document Info is not attached to the /Root object.
It may be accessed using the ``.docinfo`` property. If no Document Info exists,
touching the ``.docinfo`` will properly initialize an empty one.

Here is an example of a Document Info block.

.. ipython::

  In [12]: pdf = pikepdf.open('../tests/resources/sandwich.pdf')

  In [12]: pdf.docinfo
  Out[12]:
  pikepdf.Dictionary({
    "/CreationDate": "D:20170911132748-07'00'",
    "/Creator": "ocrmypdf 5.3.3 / Tesseract OCR-PDF 3.05.01",
    "/ModDate": "D:20170911132748-07'00'",
    "/Producer": "GPL Ghostscript 9.21"
  })

It is permitted in pikepdf to directly interact with Document Info as with
other PDF dictionaries. However, it is better to use ``.open_metadata()``
because that interface will apply changes to both XMP and Document Info in a
consistent manner.

You may copy from data from a Document Info object in the current PDF or another
PDF into XMP metadata using :meth:`~pikepdf.models.PdfMetadata.load_from_docinfo`.
