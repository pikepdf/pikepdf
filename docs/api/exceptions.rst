Exceptions
**********

.. autoexception:: pikepdf.PdfError

    General pikepdf-specific exception.

.. autoexception:: pikepdf.PasswordError

    Exception thrown when the supplied password is incorrect.

.. autoexception:: pikepdf.ForeignObjectError

    Exception thrown when a complex object was copied into a foreign PDF without
    using :meth:`Pdf.copy_foreign`.

.. autoexception:: pikepdf.OutlineStructureError

    Exception thrown when an ``/Outlines`` object violates constraints imposed
    by the |pdfrm|.

.. autoexception:: pikepdf.UnsupportedImageTypeError

    Exception thrown when attempting to manipulate a PDF image of a complex type
    that pikepdf does not currently support.

.. autoexception:: pikepdf.DataDecodingError

    Exception thrown when a stream object in a PDF is malformed and cannot be
    decoded.

.. autoexception:: pikepdf.DeletedObjectError

    Exception thrown when accessing a :class:`Object` that relies on a :class:`Pdf`
    that was deleted using the Python ``delete`` statement or collected by the
    Python garbage collector. To resolve this error, you must retain a reference
    to the Pdf for the whole time you may be accessing it.

    .. versionadded:: 7.0