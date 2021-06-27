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

    Exception throw when an ``/Outlines`` object violates constraints imposed
    by the |pdfrm|.

.. autoexception:: pikepdf.UnsupportedImageTypeError

    Exception throw when attempting to manipulate a PDF image of a complex type
    that pikepdf does not currently support.
