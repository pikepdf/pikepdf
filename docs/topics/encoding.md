# Character encoding

```{eval-rst}
.. epigraph::

    | There are three hard problems in computer science:
    | 1) Converting from PDF,
    | 2) Converting to PDF, and
    | 3) O̳̳̳̳̳̳̳̳̳̳̳̳̳̳̳̳̳Ҙ҉҉҉ʹʹ҉ʹ̨̨̨̨̨̨̨̨̃༃༃O̳̳̳̳̳̳̳̳̳̳̳̳̳̳̳̳̳Ҙ҉҉҉ʹʹ҉ʹ̨̨̨̨̨̨̨̨̃༃༃ʹʹ҉ʹ̨̨̨̨̨̨̨̨̃༃༃

    -- `Marseille Folog <https://twitter.com/fogus/status/1024657831084085248>`_
```

In most circumstances, pikepdf performs appropriate encodings and
decodings on its own, or returns {class}`pikepdf.String` if it is not clear
whether to present data as a string or binary data.

`str(pikepdf.String)` is performed by inspecting the binary data. If the
binary data begins with a UTF-16 byte order mark, then the data is
interpreted as UTF-16 and returned as a Python `str`. Otherwise, the data
is returned as a Python `str`, if the binary data will be interpreted as
PDFDocEncoding and decoded to `str`. Again, in most cases this is correct
behavior and will operate transparently.

Some functions are available in circumstances where it is necessary to force
a particular conversion.

## PDFDocEncoding

The PDF specification defines PDFDocEncoding, a character encoding used only
in PDFs. This encoding matches ASCII for code points 32 through 126 (0x20 to
0x7e). At all other code points, it is not ASCII and cannot be treated as
equivalent. If you look at a PDF in a binary file viewer (hex editor), a string
surrounded by parentheses such as `(Hello World)` is usually using
PDFDocEncoding.

When pikepdf is imported, it automatically registers `"pdfdoc"` as a codec
with the standard library, so that it may be used in string and byte
conversions.

```python
"•".encode('pdfdoc') == b'\x81'
```

Other Python PDF libraries may register their own `pdfdoc` codecs. Unfortunately,
the order of imports will determine which codec "wins" and gets mapped
to the `'pdfdoc'` string. Fortunately, these implementations should be
quite compatible with each other anyway since they do the same things.

pikepdf also registers `'pdfdoc_pikepdf'`, if you want to ensure use of
pikepdf's codec, i.e. `s.encode('pdfdoc_pikepdf')`.

:::{versionchanged} 5.0.0 Some issues with the conversion of obscure characters in PDFDocEncoding were fixed. Older versions of pikepdf may not convert PDFDocEncoding in all cases.
:::

## Other codecs

Two other codecs are commonly used in PDFs, but they are already part of the
standard library.

**WinAnsiEncoding** is identical Windows Code Page 1252, and may be converted
using the `"cp1252"` codec.

**MacRomanEncoding** may be converted using the `"macroman"` codec.
