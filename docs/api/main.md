# Main objects

```{eval-rst}
.. autoapiclass:: pikepdf.Pdf
    :members:
```

```{eval-rst}
.. function:: pikepdf.open

    Alias for :meth:`pikepdf.Pdf.open`.
```

```{eval-rst}
.. function:: pikepdf.new

    Alias for :meth:`pikepdf.Pdf.new`.
```

## Access modes

```{eval-rst}
.. autoapiclass:: pikepdf.ObjectStreamMode
    :members:
```

```{eval-rst}
.. autoapiclass:: pikepdf.StreamDecodeLevel
    :members:
```

```{eval-rst}
.. autoapiclass:: pikepdf.Encryption
    :members:
```

## Object construction

```{eval-rst}
.. autoapiclass:: pikepdf.Object
    :members:
    :special-members:
```

```{eval-rst}
.. autoapiclass:: pikepdf.Name
    :members: random
    :special-members: __new__
```

```{eval-rst}
.. autoapiclass:: pikepdf.String
    :members: __new__
```

```{eval-rst}
.. autoapiclass:: pikepdf.Array
    :members: __new__
```

```{eval-rst}
.. autoapiclass:: pikepdf.Dictionary
    :members: __new__
```

```{eval-rst}
.. autoapiclass:: pikepdf.Stream
    :members: __new__
```

```{eval-rst}
.. autoapiclass:: pikepdf.Operator
    :members: __new__
```

## Common PDF data structures

```{eval-rst}
.. autoapiclass:: pikepdf.Matrix
    :members:
    :special-members: __init__, __matmul__, __array__
```

```{eval-rst}
.. autoapiclass:: pikepdf.Rectangle
    :members:
    :special-members: __init__, __and__
```

## Content stream elements

```{eval-rst}
.. autoapiclass:: pikepdf.ContentStreamInstruction
    :members:
```

```{eval-rst}
.. autoapiclass:: pikepdf.ContentStreamInlineImage
    :members:
```

## Internal objects

These objects are returned by other pikepdf objects. They are part of the API,
but not intended to be created explicitly.

```{eval-rst}
.. autoapiclass:: pikepdf._core.PageList
    :members:
```

```{eval-rst}
.. autoapiclass:: pikepdf._core._ObjectList
    :members:
```

```{eval-rst}
.. autoapiclass:: pikepdf.ObjectType
    :members:
```

## Jobs

```{eval-rst}
.. autoapiclass:: pikepdf.Job
    :members:
    :special-members: __init__
```
