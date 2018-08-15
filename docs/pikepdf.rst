pikepdf API
***********

Primary objects
===============

.. autoclass:: pikepdf.Pdf
    :members:

.. autofunction:: pikepdf.open

.. autoclass:: pikepdf.ObjectStreamMode

    .. attribute:: disable

    .. attribute:: preserve

    .. attribute:: generate

.. autoclass:: pikepdf.StreamDataMode

    .. attribute:: uncompress

    .. attribute:: preserve

    .. attribute:: compress

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
