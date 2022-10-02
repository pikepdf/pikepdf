v6.1.0
======

- Rebuild wheels with qpdf 11.1.1. No new functionality.

v6.0.2
======

- Fixed large increase in binary wheel file size for manylinux wheels.
- Provide macOS and Linux wheels for Python 3.11.

v6.0.1
======

- Use qpdf 11.1.0, which fixes problems with building pikepdf on Windows.

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

