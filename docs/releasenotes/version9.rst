v9.0.0
======

- Removed deprecated pikepdf.PdfMatrix. Use pikepdf.Matrix instead.
- Removed deprecated pikepdf._qpdf submodule.
- Pdf.pages no longer coerces PDF dictionaries to page objects. You must
  explicitly insert/add pikepdf.Page objects.
- pikepdf.Object.parse() no longer accepts string input; only bytes are allowed.
- macOS 12 is our minimum supported version for x86_64, and macos 14 is our
  minimum supported version for ARM64/Apple Silicon. v8 accidentally
  ended support for older versions at some point - this change is formalizing that.
  Efforts were made to continue support for older verions, but it is not sustainable.
- We now generate binary wheels for musllinux-aarch64 (Alpine ARM64).
