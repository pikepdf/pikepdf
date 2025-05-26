# Form

The `pikepdf.form` module provides a high-level API for working with interactive forms, built on top of the lower-level `pikepdf.AcroForm` interface.

```{eval-rst}
.. autoapimodule:: pikepdf.form

.. autoapiclass:: pikepdf.form.Form
    :members:
```

## Form Fields

```{eval-rst}
.. autoapiclass:: pikepdf.form._FieldWrapper
    :members:
```

```{eval-rst}
.. autoapiclass:: pikepdf.form.TextField
    :members:
```

```{eval-rst}
.. autoapiclass:: pikepdf.form.CheckboxField
    :members:
```

```{eval-rst}
.. autoapiclass:: pikepdf.form.RadioButtonGroup
    :members:
```

```{eval-rst}
.. autoapiclass:: pikepdf.form.RadioButtonOption
    :members:
```

```{eval-rst}
.. autoapiclass:: pikepdf.form.PushbuttonField
    :members:
```

```{eval-rst}
.. autoapiclass:: pikepdf.form.ChoiceField
    :members:
```

```{eval-rst}
.. autoapiclass:: pikepdf.form.ChoiceFieldOption
    :members:
```

```{eval-rst}
.. autoapiclass:: pikepdf.form.SignatureField
    :members:
```

## Generating Appearance Streams

Merely setting the values of form fields is not sufficient. It is also necessary to
generate appearance streams for fields. These appearance streams define how the filled-out
field should actually look when viewed in a PDF reader.

Generating appearance streams can be very complex. Both of the classes below have limited
capacities, but should work for many use cases, and can be extended to meet your needs.

```{eval-rst}
.. autoapiclass:: pikepdf.form.AppearanceStreamGenerator
    :members:
```

```{eval-rst}
.. autoapiclass:: pikepdf.form.DefaultAppearanceStreamGenerator
    :members:
```

```{eval-rst}
.. autoapiclass:: pikepdf.form.ExtendedAppearanceStreamGenerator
    :members:


```
