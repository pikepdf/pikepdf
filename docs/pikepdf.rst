pikepdf API Reference
*********************

Primary objects
===============

.. autoclass:: pikepdf.Pdf
    :members:

.. autofunction:: pikepdf.open

.. autoclass:: pikepdf.Object
    :members:

.. autoclass:: pikepdf.String

.. autoclass:: pikepdf.Array

.. autoclass:: pikepdf.Dictionary

.. autoclass:: pikepdf.Stream

.. autoclass:: pikepdf.Operator

.. autoexception:: pikepdf.PdfError

.. autoexception:: pikepdf.PasswordError


Support models
==============

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
