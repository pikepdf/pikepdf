# PDF/A validation

The {mod}`pikepdf.pdfa` module prepares documents for PDF/A-1b, PDF/A-2b and
PDF/A-3b, checks them, and saves them with validation of the written bytes. It
needs the optional extra `pikepdf[pdfa]`. See {ref}`pdfa` for a discussion of
how to use it and what it does not cover.

```{eval-rst}
.. autoapimodule:: pikepdf.pdfa
```

## Functions

```{eval-rst}
.. autoapifunction:: pikepdf.pdfa.save
```

```{eval-rst}
.. autoapifunction:: pikepdf.pdfa.prepare
```

```{eval-rst}
.. autoapifunction:: pikepdf.pdfa.check
```

```{eval-rst}
.. autoapifunction:: pikepdf.pdfa.resolve_save_kwargs
```

```{eval-rst}
.. autoapifunction:: pikepdf.pdfa.validate_written
```

## Results

```{eval-rst}
.. autoapiclass:: pikepdf.pdfa.Report
    :members: verdict, passed, violations, unsupported, summary
```

```{eval-rst}
.. autoapiclass:: pikepdf.pdfa.Finding
```

```{eval-rst}
.. autoapiclass:: pikepdf.pdfa.PrepareResult
    :members: changed, describe
```

```{eval-rst}
.. autoapiclass:: pikepdf.pdfa.Flavour
    :members: PDFA_1B, PDFA_2B, PDFA_3B, part
```

```{eval-rst}
.. autoapiexception:: pikepdf.pdfa.PdfaError
```
