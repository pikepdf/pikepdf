# Exceptions

```{eval-rst}
.. autoapiexception:: pikepdf.exceptions.PdfError
```

```{eval-rst}
.. autoapiexception:: pikepdf.exceptions.PasswordError
```

```{eval-rst}
.. autoapiexception:: pikepdf.exceptions.ForeignObjectError
```

```{eval-rst}
.. autoapiexception:: pikepdf.exceptions.OutlineStructureError
```

```{eval-rst}
.. autoapiexception:: pikepdf.exceptions.StructureTreeError
```

```{eval-rst}
.. autoapiexception:: pikepdf.exceptions.UnsupportedImageTypeError
```

```{eval-rst}
.. autoapiexception:: pikepdf.exceptions.HifiPrintImageNotTranscodableError
```

```{eval-rst}
.. autoapiexception:: pikepdf.exceptions.InvalidPdfImageError
```

```{eval-rst}
.. autoapiexception:: pikepdf.exceptions.DataDecodingError
```

```{eval-rst}
.. autoapiexception:: pikepdf.exceptions.DeletedObjectError
```

```{eval-rst}
.. autoapiexception:: pikepdf.exceptions.DependencyError
```

```{eval-rst}
.. autoapiexception:: pikepdf.exceptions.PdfParsingError
```

```{eval-rst}
.. autoapiexception:: pikepdf.exceptions.JobUsageError
```

```{eval-rst}
.. autoapiexception:: pikepdf.exceptions.ImageDecompressionError
```

```{eval-rst}
.. autoapiexception:: pikepdf.exceptions.FormCopyWarning
```

```{eval-rst}
.. py:exception:: pikepdf.DecompressionBombError

   Bases: :py:exc:`PIL.Image.DecompressionBombError`

   Raised by image extraction when an image's pixel count exceeds twice
   :py:attr:`pikepdf.PdfImage.MAX_IMAGE_PIXELS`, indicating a possible
   decompression-bomb (memory exhaustion) attack. Subclasses Pillow's
   exception of the same name, so handlers written for Pillow also catch it.

   This class is created lazily on first access so that importing pikepdf does
   not import Pillow.
```

```{eval-rst}
.. py:exception:: pikepdf.DecompressionBombWarning

   Bases: :py:exc:`PIL.Image.DecompressionBombWarning`

   Emitted by image extraction when an image's pixel count exceeds
   :py:attr:`pikepdf.PdfImage.MAX_IMAGE_PIXELS` (but is not large enough to
   raise :py:exc:`pikepdf.DecompressionBombError`). Subclasses Pillow's warning
   of the same name.
```
