pikepdf API
***********

Main objects
============

.. autoclass:: pikepdf.Pdf
    :members:

.. autofunction:: pikepdf.open

.. class:: pikepdf.ObjectStreamMode

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

.. class:: pikepdf.StreamDecodeLevel

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

.. autoclass:: pikepdf.models.Encryption
    :members:

.. autoclass:: pikepdf.Permissions
    :members:

    .. attribute:: accessibility

        The owner of the PDF permission for screen readers and accessibility
        tools to access the PDF.

    .. attribute:: extract

        The owner of the PDF permission for software to extract content from a PDF.

    .. attribute:: modify_annotation

    .. attribute:: modify_assembly

    .. attribute:: modify_form

    .. attribute:: modify_other

        The owner of the PDF permission to modify various parts of a PDF.

    .. attribute:: print_lowres

    .. attribute:: print_highres

        The owner of the PDF permission to print at low or high resolution.

.. class:: pikepdf.models.EncryptionMethod

    Describes which encryption method was used on a particular part of a
    PDF. These values are returned by :class:`pikepdf.EncryptionInfo` but
    are not currently used to specify how encryption is requested.

    .. attribute:: none

        Data was not encrypted.

    .. attribute:: unknown

        An unknown algorithm was used.

    .. attribute:: rc4

        The RC4 encryption algorithm was used (obsolete).

    .. attribute:: aes

        The AES-based algorithm was used as described in the PDF 1.7 reference manual.

    .. attribute:: aesv3

        An improved version of the AES-based algorithm was used as described in the
        Adobe Supplement to the ISO 32000, requiring PDF 1.7 extension level 3. This
        algorithm still uses AES, but allows both AES-128 and AES-256, and improves how
        the key is derived from the password.

.. autoclass:: pikepdf.models.EncryptionInfo
    :members:

Internal objects
================

These objects are returned by other pikepdf objects. They are part of the API,
but not intended to be created explicitly.

.. autoclass:: pikepdf._qpdf.PageList
    :members:

    A ``list``-like object enumerating all pages in a :class:`pikepdf.Pdf`.
