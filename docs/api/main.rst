Main objects
************

.. autoapiclass:: pikepdf.Pdf
    :members:

.. function:: pikepdf.open

    Alias for :meth:`pikepdf.Pdf.open`.

.. function:: pikepdf.new

    Alias for :meth:`pikepdf.Pdf.new`.

Access modes
============

.. autoapiclass:: pikepdf.ObjectStreamMode
    :members:

.. autoapiclass:: pikepdf.StreamDecodeLevel
    :members:

.. autoapiclass:: pikepdf.Encryption
    :noindex:

Object construction
===================

.. autoapiclass:: pikepdf.Object
    :members:

.. autoapiclass:: pikepdf.Name
    :members: __new__

.. autoapiclass:: pikepdf.String
    :members: __new__

.. autoapiclass:: pikepdf.Array
    :members: __new__

.. autoapiclass:: pikepdf.Dictionary
    :members: __new__

.. autoapiclass:: pikepdf.Stream
    :members: __new__

.. autoapiclass:: pikepdf.Operator
    :members:

Common PDF data structures
==========================

.. autoapiclass:: pikepdf.Matrix
    :members:
    :special-members: __init__, __matmul__, __array__

.. autoapiclass:: pikepdf.Rectangle
    :members:

Content stream elements
=======================

.. autoapiclass:: pikepdf.ContentStreamInstruction
    :members:

.. autoapiclass:: pikepdf.ContentStreamInlineImage
    :members:

Internal objects
================

These objects are returned by other pikepdf objects. They are part of the API,
but not intended to be created explicitly.

.. autoapiclass:: pikepdf._core.PageList
    :members:

.. autoapiclass:: pikepdf._core._ObjectList
    :members:

.. autoapiclass:: pikepdf.ObjectType
    :members:

Jobs
====

.. autoapiclass:: pikepdf.Job
    :members:
    :special-members: __init__