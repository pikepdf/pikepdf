# Support models

Support models are abstracts over "raw" objects within a Pdf. For example, a page
in a PDF is a Dictionary with set to `/Type` of `/Page`. The Dictionary in
that case is the "raw" object. Upon establishing what type of object it is, we
can wrap it with a support model that adds features to ensure consistency with
the PDF specification.

In version 2.x, did not apply support models to "raw" objects automatically.
Version 3.x automatically applies support models to `/Page` objects.

```{eval-rst}
.. autoapiclass:: pikepdf.ObjectHelper
    :members:
```

```{eval-rst}
.. autoapiclass:: pikepdf.Page
    :members:
    :inherited-members:
```

```{eval-rst}
.. autoapiclass:: pikepdf.PdfImage
    :inherited-members:
```

```{eval-rst}
.. autoapiclass:: pikepdf.PdfInlineImage
```

```{eval-rst}
.. autoapiclass:: pikepdf.models.PdfMetadata
    :members:
```

```{eval-rst}
.. autoapiclass:: pikepdf.models.Encryption
    :members:
```

```{eval-rst}
.. autoapiclass:: pikepdf.models.Outline
    :members:
```

```{eval-rst}
.. autoapiclass:: pikepdf.models.OutlineItem
    :members:
```

```{eval-rst}
.. autoapiclass:: pikepdf.Permissions
    :members:
```

```{eval-rst}
.. autoapiclass:: pikepdf.models.EncryptionMethod
    :members:
```

```{eval-rst}
.. autoapiclass:: pikepdf.models.EncryptionInfo
    :members:
```

```{eval-rst}
.. autoapiclass:: pikepdf.AcroForm
    :members:
```

```{eval-rst}
.. autoapiclass:: pikepdf.AcroFormField
    :members:
```

```{eval-rst}
.. autoapiclass:: pikepdf.Annotation
    :members:
```

```{eval-rst}
.. autoapiclass:: pikepdf._core.Attachments
    :members:
```

```{eval-rst}
.. autoapiclass:: pikepdf.AttachedFileSpec
    :members:
    :inherited-members:
    :special-members: __init__
```

```{eval-rst}
.. autoapiclass:: pikepdf._core.AttachedFile
    :members:
```

```{eval-rst}
.. autoapiclass:: pikepdf.NameTree
    :members:
```

```{eval-rst}
.. autoapiclass:: pikepdf.NumberTree
    :members:
```
