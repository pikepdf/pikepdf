Support models
**************

Support models are abstracts over "raw" objects within a Pdf. For example, a page
in a PDF is a Dictionary with set to ``/Type`` of ``/Page``. The Dictionary in
that case is the "raw" object. Upon establishing what type of object it is, we
can wrap it with a support model that adds features to ensure consistency with
the PDF specification.

pikepdf does not currently apply support models to "raw" objects automatically,
but might do so in a future release (this would break backward compatibility).

.. autoclass:: pikepdf.Page
    :members:

    Support model wrapper around a raw page dictionary object.

    To initialize a ``Page`` support model:

    .. code-block:: python

        from pikepdf import Pdf, Page

        Pdf = open(...)
        page_support_model = Page(pdf.pages[0])

.. autoclass:: pikepdf.PdfMatrix
    :members:

    .. attribute:: a

    .. attribute:: b

    .. attribute:: c

    .. attribute:: d

    .. attribute:: e

    .. attribute:: f

        Return one of the six "active values" of the affine matrix. ``e`` and ``f``
        correspond to x- and y-axis translation respectively. The other four
        letters are a 2×2 matrix that can express rotation, scaling and skewing;
        ``a=1 b=0 c=0 d=1`` is the identity matrix.

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

        The AES-based algorithm was used as described in the |pdfrm|.

    .. attribute:: aesv3

        An improved version of the AES-based algorithm was used as described in the
        :doc:`Adobe Supplement to the ISO 32000 </references/resources>`, requiring
        PDF 1.7 extension level 3. This algorithm still uses AES, but allows both
        AES-128 and AES-256, and improves how the key is derived from the password.

.. autoclass:: pikepdf.models.EncryptionInfo
    :members:

.. autoclass:: pikepdf.Annotation
    :members:

    Describes an annotation in a PDF, such as a comment, underline, copy editing marks,
    interactive widgets, redactions, 3D objects, sound and video clips.

    See the |pdfrm| section 12.5.6 for the full list of annotation types
    and definition of terminology.

    .. versionadded:: 2.12
