# Exceptions

Every exception pikepdf raises on its own behalf derives from
{class}`pikepdf.PikepdfError`, and every warning it issues derives from
{class}`pikepdf.PikepdfWarning`.

```text
PikepdfError
├── PdfError                              the document is defective
│   ├── DataDecodingError                 a stream will not decode
│   ├── PdfParsingError                   a content stream will not parse
│   └── ReferenceCycleError
├── PasswordError                         the document is fine; the password is not
├── DependencyError                       a third-party tool is missing
├── OutlineStructureError
├── ForeignObjectError                    ┐
├── DeletedObjectError                    ├ the caller misused the API
├── JobUsageError                         ┘
├── UnsupportedImageTypeError
├── InvalidPdfImageError
├── ImageDecompressionError
├── NotExtractableError
│   └── HifiPrintImageNotTranscodableError
└── DecompressionBombError                (also a PIL.Image.DecompressionBombError)

PikepdfWarning
├── PageCopyWarning
├── XmpTypeWarning                        an XMP value has the wrong type
└── DecompressionBombWarning              (also a PIL.Image.DecompressionBombWarning)
```

To handle a damaged or unreadable document, catch {class}`pikepdf.PdfError`: it
covers both malformed file structure and streams that will not decode.
{class}`pikepdf.PasswordError` is deliberately *not* a `PdfError`, so that code
which reports "wrong password" separately from "broken file" can order

```python
try:
    ...
except pikepdf.PdfError:
    ...      # the file is damaged
except pikepdf.PasswordError:
    ...      # the file is fine, we need a password
```

without the first handler swallowing the second.

:::{note}
`except PikepdfError` does **not** catch everything that can escape a pikepdf
call. pikepdf raises the ordinary built-in exceptions where they are the natural
choice — `ValueError`, `TypeError`, `KeyError`, `IndexError` and
`NotImplementedError` for invalid arguments or unsupported input, and the
`OSError` family (including `FileNotFoundError`) for file access. Image
extraction may also raise exceptions from Pillow. `PikepdfError` means
"pikepdf-specific error", not "any error from pikepdf".
:::

## Roots

```{eval-rst}
.. autoapiexception:: pikepdf.exceptions.PikepdfError
```

```{eval-rst}
.. autoapiexception:: pikepdf.exceptions.PikepdfWarning
```

## Document errors

```{eval-rst}
.. autoapiexception:: pikepdf.exceptions.PdfError
```

```{eval-rst}
.. autoapiexception:: pikepdf.exceptions.DataDecodingError
```

```{eval-rst}
.. autoapiexception:: pikepdf.exceptions.PdfParsingError
```

```{eval-rst}
.. autoapiexception:: pikepdf.exceptions.ReferenceCycleError
```

```{eval-rst}
.. autoapiexception:: pikepdf.exceptions.OutlineStructureError
```

## Encryption

```{eval-rst}
.. autoapiexception:: pikepdf.exceptions.PasswordError
```

## API misuse

```{eval-rst}
.. autoapiexception:: pikepdf.exceptions.ForeignObjectError
```

```{eval-rst}
.. autoapiexception:: pikepdf.exceptions.DeletedObjectError
```

```{eval-rst}
.. autoapiexception:: pikepdf.exceptions.JobUsageError
```

## Environment

```{eval-rst}
.. autoapiexception:: pikepdf.exceptions.DependencyError
```

## Image errors

```{eval-rst}
.. autoapiexception:: pikepdf.exceptions.UnsupportedImageTypeError
```

```{eval-rst}
.. autoapiexception:: pikepdf.exceptions.InvalidPdfImageError
```

```{eval-rst}
.. autoapiexception:: pikepdf.exceptions.ImageDecompressionError
```

```{eval-rst}
.. autoapiexception:: pikepdf.exceptions.NotExtractableError
```

```{eval-rst}
.. autoapiexception:: pikepdf.exceptions.HifiPrintImageNotTranscodableError
```

```{eval-rst}
.. py:exception:: pikepdf.DecompressionBombError

   Bases: :py:exc:`pikepdf.PikepdfError`, :py:exc:`PIL.Image.DecompressionBombError`

   Raised by image extraction when an image's pixel count exceeds twice
   :py:attr:`pikepdf.PdfImage.MAX_IMAGE_PIXELS`, indicating a possible
   decompression-bomb (memory exhaustion) attack. Subclasses Pillow's
   exception of the same name, so handlers written for Pillow also catch it.

   This class is created lazily on first access so that importing pikepdf does
   not import Pillow.
```

## Warnings

```{eval-rst}
.. autoapiexception:: pikepdf.exceptions.PageCopyWarning
```

```{eval-rst}
.. autoapiexception:: pikepdf.exceptions.XmpTypeWarning
```

```{eval-rst}
.. py:exception:: pikepdf.DecompressionBombWarning

   Bases: :py:exc:`pikepdf.PikepdfWarning`, :py:exc:`PIL.Image.DecompressionBombWarning`

   Emitted by image extraction when an image's pixel count exceeds
   :py:attr:`pikepdf.PdfImage.MAX_IMAGE_PIXELS` (but is not large enough to
   raise :py:exc:`pikepdf.DecompressionBombError`). Subclasses Pillow's warning
   of the same name.
```
