Support models
**************

Support models are abstracts over "raw" objects within a Pdf. For example, a page
in a PDF is a Dictionary with set to ``/Type`` of ``/Page``. The Dictionary in
that case is the "raw" object. Upon establishing what type of object it is, we
can wrap it with a support model that adds features to ensure consistency with
the PDF specification.

pikepdf does not currently apply support models to "raw" objects automatically,
but might do so in a future release (this would break backward compatibility).

For example, to initialize a ``Page`` support model:

.. code-block:: python

    from pikepdf import Pdf, Page

    Pdf = open(...)
    page_support_model = Page(pdf.pages[0])

.. autoclass:: pikepdf.Page
    :members:

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

.. autoclass:: pikepdf.models.Outline
    :members:

.. autoclass:: pikepdf.models.OutlineItem
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
