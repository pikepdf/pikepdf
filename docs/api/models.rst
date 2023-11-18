Support models
**************

Support models are abstracts over "raw" objects within a Pdf. For example, a page
in a PDF is a Dictionary with set to ``/Type`` of ``/Page``. The Dictionary in
that case is the "raw" object. Upon establishing what type of object it is, we
can wrap it with a support model that adds features to ensure consistency with
the PDF specification.

In version 2.x, did not apply support models to "raw" objects automatically.
Version 3.x automatically applies support models to ``/Page`` objects.

.. autoapiclass:: pikepdf.ObjectHelper
    :members:

.. autoapiclass:: pikepdf.Page
    :members:
    :inherited-members:

.. autoapiclass:: pikepdf.PdfMatrix
    :members:
    :special-members: __init__, __matmul__, __array__

.. autoapiclass:: pikepdf.PdfImage
    :inherited-members:

.. autoapiclass:: pikepdf.PdfInlineImage

.. autoapiclass:: pikepdf.models.PdfMetadata
    :members:

.. autoapiclass:: pikepdf.models.Encryption
    :members:

.. autoapiclass:: pikepdf.models.Outline
    :members:

.. autoapiclass:: pikepdf.models.OutlineItem
    :members:

.. autoapiclass:: pikepdf.Permissions
    :members:

.. autoapiclass:: pikepdf.models.EncryptionMethod
    :members:

.. autoapiclass:: pikepdf.models.EncryptionInfo
    :members:

.. autoapiclass:: pikepdf.Annotation
    :members:

.. autoapiclass:: pikepdf._core.Attachments
    :members:

.. autoapiclass:: pikepdf.AttachedFileSpec
    :members:
    :inherited-members:
    :special-members: __init__

.. autoapiclass:: pikepdf._core.AttachedFile
    :members:

.. autoapiclass:: pikepdf.NameTree
    :members:

.. autoapiclass:: pikepdf.NumberTree
    :members:

.. automodule:: pikepdf.canvas
    :members:
