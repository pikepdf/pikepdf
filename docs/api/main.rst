Main objects
************

.. autoclass:: pikepdf.Pdf
    :members:

.. function:: pikepdf.open

    Alias for :meth:`pikepdf.Pdf.open`.

.. function:: pikepdf.new

    Alias for :meth:`pikepdf.Pdf.new`.

.. class:: pikepdf.ObjectStreamMode

    Options for saving streams within PDFs, which are more a compact
    way of saving certain types of data that was added in PDF 1.5. All
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
    :noindex:

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

Common PDF data structures
==========================

.. autoclass:: pikepdf.Matrix
    :members:
    :special-members: __init__, __matmul__, __array__

.. autoclass:: pikepdf.Rectangle
    :members:

Content stream elements
=======================

.. autoclass:: pikepdf.ContentStreamInstruction
    :members:

    Represents one complete instruction inside a content stream.

.. autoclass:: pikepdf.ContentStreamInlineImage
    :members:

    Represents an instruction to draw an inline image inside a content
    stream.

    pikepdf consolidates the BI-ID-EI sequence of operators, as appears in a PDF to
    declare an inline image, and replaces them with a single virtual content stream
    instruction with the operator "INLINE IMAGE".

Internal objects
================

These objects are returned by other pikepdf objects. They are part of the API,
but not intended to be created explicitly.

.. autoclass:: pikepdf._core.PageList
    :members:

    A ``list``-like object enumerating a range of pages in a :class:`pikepdf.Pdf`.
    It may be all of the pages or a subset.

.. autoclass:: pikepdf._core._ObjectList
    :members:

    A ``list``-like object containing multiple ``pikepdf.Object``.

.. class:: pikepdf.ObjectType

    Enumeration of object types. These values are used to implement
    pikepdf's instance type checking. In the vast majority of cases it is more
    pythonic to use ``isinstance(obj, pikepdf.Stream)`` or ``issubclass``.

    These values are low-level and documented for completeness. They are exposed
    through :attr:`pikepdf.Object._type_code`.

    .. attribute:: uninitialized

        An uninitialized object. If this appears, it is probably a bug.

    .. attribute:: reserved

        A temporary object used in creating circular references. Should not appear
        in most cases.

    .. attribute:: null

        A PDF null. In most cases, nulls are automatically converted to ``None``,
        so this should not appear.

    .. attribute:: boolean

        A PDF boolean. In most cases, booleans are automatically converted to
        ``bool``, so this should not appear.

    .. attribute:: integer

        A PDF integer. In most cases, integers are automatically converted to
        ``int``, so this should not appear. Unlike Python integers, PDF integers
        are 32-bit signed integers.

    .. attribute:: real

        A PDF real. In most cases, reals are automatically convert to
        :class:`decimal.Decimal`.

    .. attribute:: string

        A PDF string, meaning the object is a ``pikepdf.String``.

    .. attribute:: name_

        A PDF name, meaning the object is a ``pikepdf.Name``.

    .. attribute:: array

        A PDF array, meaning the object is a ``pikepdf.Array``.

    .. attribute:: dictionary

        A PDF dictionary, meaning the object is a ``pikepdf.Dictionary``.

    .. attribute:: stream

        A PDF stream, meaning the object is a ``pikepdf.Stream`` (and it also
        has a dictionary).

    .. attribute:: operator

        A PDF operator, meaning the object is a ``pikepdf.Operator``.

    .. attribute:: inlineimage

        A PDF inline image, meaning the object is the data stream of an inline
        image. It would be necessary to combine this with the implicit
        dictionary to interpret the image correctly. pikepdf automatically
        packages inline images into a more useful class, so this will not
        generally appear.

Jobs
====

.. autoclass:: pikepdf.Job
    :members:
    :special-members: __init__