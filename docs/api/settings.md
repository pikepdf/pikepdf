# Settings

Some of pikepdf's global parameters can be tuned.

```{eval-rst}
.. autoapifunction:: pikepdf.settings.get_decimal_precision
```

```{eval-rst}
.. autoapifunction:: pikepdf.settings.set_decimal_precision
```

```{eval-rst}
.. autoapifunction:: pikepdf.settings.set_flate_compression_level
```

## qpdf limits

qpdf applies global limits that protect against malicious or badly damaged
PDFs, such as the maximum nesting depth when parsing objects, or the maximum
memory used to decode a stream. These limits apply to the whole process.

```{eval-rst}
.. autoapifunction:: pikepdf.settings.get_qpdf_limits
```

```{eval-rst}
.. autoapifunction:: pikepdf.settings.set_qpdf_limits
```

```{eval-rst}
.. autoapifunction:: pikepdf.settings.disable_qpdf_default_limits
```

```{eval-rst}
.. autoapifunction:: pikepdf.settings.qpdf_limit_errors
```
