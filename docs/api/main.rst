Main objects
************

.. autoclass:: pikepdf.Pdf
    :members:

.. autofunction:: pikepdf.open

.. autofunction:: pikepdf.new

.. class:: pikepdf.ObjectStreamMode

    Options for saving streams within PDFs, which are more a compact
    way of saving certains types of data that was added in PDF 1.5. All
    modern PDF viewers support object streams, but some third party tools
    and libraries cannot read them.

    .. attribute:: disable

        Disable the use of object streams. If any object streams exist in the
        file, remove them when the file is saved.

    .. attribute:: preserve

        Preserve any existing object streams in the original file. This is
        the default behavior.

    .. attribute:: generate

        Generate object streams.

.. class:: pikepdf.StreamDecodeLevel

    Options for decoding streams within PDFs.

    .. attribute:: none

        Do not attempt to apply any filters. Streams
        remain as they appear in the original file. Note that
        uncompressed streams may still be compressed on output. You can
        disable that by saving with ``.save(..., compress_streams=False)``.

    .. attribute:: generalized

        This is the default. libqpdf will apply
        LZWDecode, ASCII85Decode, ASCIIHexDecode, and FlateDecode
        filters on the input. When saved with
        ``compress_streams=True``, the default, the effect of this
        is that streams filtered with these older and less efficient
        filters will be recompressed with the Flate filter. As a
        special case, if a stream is already compressed with
        FlateDecode and ``compress_streams=True``, the original
        compressed data will be preserved.

    .. attribute:: specialized

        In addition to uncompressing the
        generalized compression formats, supported non-lossy
        compression will also be be decoded. At present, this includes
        the RunLengthDecode filter.

    .. attribute:: all

        In addition to generalized and non-lossy
        specialized filters, supported lossy compression filters will
        be applied. At present, this includes DCTDecode (JPEG)
        compression. Note that compressing the resulting data with
        DCTDecode again will accumulate loss, so avoid multiple
        compression and decompression cycles. This is mostly useful for
        (low-level) retrieving image data; see :class:`pikepdf.PdfImage` for
        the preferred method.

.. autoclass:: pikepdf.Encryption

.. autoexception:: pikepdf.PdfError

.. autoexception:: pikepdf.PasswordError

Object construction
===================

.. autoclass:: pikepdf.Object
    :members:

.. autoclass:: pikepdf.Name
    :members: __new__

.. autoclass:: pikepdf.String
    :members: __new__

.. autoclass:: pikepdf.Array
    :members: __new__

.. autoclass:: pikepdf.Dictionary
    :members: __new__

.. autoclass:: pikepdf.Stream
    :members: __new__

.. autoclass:: pikepdf.Operator
    :members:

Internal objects
================

These objects are returned by other pikepdf objects. They are part of the API,
but not intended to be created explicitly.

.. autoclass:: pikepdf._qpdf.PageList
    :members:

    A ``list``-like object enumerating all pages in a :class:`pikepdf.Pdf`.
