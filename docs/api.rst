pikepdf API
***********

Primary objects
===============

.. autoclass:: pikepdf.Pdf
    :members:

.. autofunction:: pikepdf.open

.. autoclass:: pikepdf.ObjectStreamMode

    Options for saving object streams within PDFs, which are more a compact
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

.. autoclass:: pikepdf.StreamDecodeLevel

    .. attribute:: none

        Do not attempt to apply any filters. Streams
        remain as they appear in the original file. Note that
        uncompressed streams may still be compressed on output. You can
        disable that by calling setCompressStreams(false).

    .. attribute:: generalized

        This is the default. libqpdf will apply
        LZWDecode, ASCII85Decode, ASCIIHexDecode, and FlateDecode
        filters on the input. When combined with
        setCompressStreams(true), which the default, the effect of this
        is that streams filtered with these older and less efficient
        filters will be recompressed with the Flate filter. As a
        special case, if a stream is already compressed with
        FlateDecode and setCompressStreams is enabled, the original
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
        retrieving image data.

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

Support models
==============

.. autofunction:: pikepdf.parse_content_stream

.. autoclass:: pikepdf.PdfMatrix
    :members:

    .. attribute:: a

    .. attribute:: b

    .. attribute:: c

    .. attribute:: d

    .. attribute:: e

    .. attribute:: f

        Return one of the six "active values" of the matrix.

.. autoclass:: pikepdf.PdfImage
    :members:

.. autoclass:: pikepdf.PdfInlineImage
    :members:

.. autoclass:: pikepdf.models.PdfMetadata
    :members:
