v6.0.0
======

- pikepdf 6.0.0 was released to align with backward incompatible changes in qpdf 11.
- Remove deprecated APIs. Mostly these were public APIs that had no business being
  public.
    - Several functions in pikepdf.jbig2
    - Some helper functions in pikepdf.models.image
    - The property PdfImage.is_inline. (Use isinstance PdfInlineImage instead.)
    - Attempting to copy pages using the ``.copy_foreign`` method now raises an
      exception. Use The ``Pdf.pages`` interface to copy pages.

