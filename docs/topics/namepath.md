(namepath)=

# Accessing nested objects with NamePath

PDF documents often have deeply nested structures. For example, to access a
font resource on a page, you might need to traverse through several levels
of dictionaries:

```python
>>> page.Resources.XObject['/Im0']  # Accessing an image
>>> pdf.Root.Pages.Kids[0].MediaBox  # Accessing a page's media box
```

While attribute notation works well for known keys, accessing optional or
deeply nested values can be cumbersome, especially when you need to handle
missing keys gracefully.

## The NamePath class

{class}`pikepdf.NamePath` provides ergonomic access to nested PDF structures
with a single operation and helpful error messages when traversal fails.

```{eval-rst}
.. doctest::

    >>> from pikepdf import Pdf, Dictionary, Array, Name, NamePath

    >>> pdf = Pdf.new()
    >>> pdf.Root.Resources = Dictionary(
    ...     Font=Dictionary(F1=Name.Helvetica),
    ...     XObject=Dictionary()
    ... )

    >>> # Access nested value with NamePath
    >>> pdf.Root[NamePath.Resources.Font.F1]
    pikepdf.Name("/Helvetica")
```

### Construction syntax

NamePath supports several construction styles:

```{eval-rst}
.. doctest::

    >>> # Shorthand syntax (most common)
    >>> path = NamePath.Resources.Font.F1
    >>> repr(path)
    'NamePath.Resources.Font.F1'

    >>> # With array indices
    >>> path = NamePath.Pages.Kids[0].MediaBox
    >>> repr(path)
    'NamePath.Pages.Kids[0].MediaBox'

    >>> # Canonical syntax (for non-Python-identifier names)
    >>> path = NamePath('/Resources', '/Weird-Name')
    >>> repr(path)
    'NamePath.Resources.Weird-Name'

    >>> # Using Name objects
    >>> path = NamePath(Name.Resources, Name.Font)
    >>> repr(path)
    'NamePath.Resources.Font'

    >>> # Chained construction
    >>> path = NamePath('/A')('/B').C[0]
    >>> repr(path)
    'NamePath.A.B.C[0]'
```

Calling a `NamePath` instance appends another name component, which is the
correct way to extend a canonical path built from non-identifier strings;
subscripting an instance with a string, as in `NamePath['/A']['/B']`, is
**not** valid (instance `__getitem__` only accepts an `int`, for array
indices). The equivalent canonical spelling is
`NamePath['/A']('/B').C[0]`, as shown above.

### Reading values

Use NamePath with the subscript operator to read nested values:

```{eval-rst}
.. doctest::

    >>> pdf = Pdf.new()
    >>> pdf.Root.Info = Dictionary(Title=pikepdf.String("My Document"))

    >>> pdf.Root[NamePath.Info.Title]
    pikepdf.String("My Document")
```

An empty NamePath returns the object itself:

```{eval-rst}
.. doctest::

    >>> pdf.Root[NamePath()]  # Returns pdf.Root
    pikepdf.Dictionary(...)
```

### Setting values

You can also set nested values with NamePath. The parent path must exist:

```{eval-rst}
.. doctest::

    >>> pdf = Pdf.new()
    >>> pdf.Root.Info = Dictionary()

    >>> pdf.Root[NamePath.Info.Author] = pikepdf.String("Alice")
    >>> pdf.Root.Info.Author
    pikepdf.String("Alice")
```

### Handling missing keys with get()

The {meth}`~pikepdf.Object.get` method works with NamePath and returns a
default value when the path doesn't exist or encounters type mismatches:

```{eval-rst}
.. doctest::

    >>> pdf = Pdf.new()

    >>> # Returns None when path doesn't exist
    >>> pdf.Root.get(NamePath.Missing.Path) is None
    True

    >>> # Returns custom default
    >>> pdf.Root.get(NamePath.Missing.Path, "not found")
    'not found'
```

This is especially useful when you're unsure if intermediate dictionaries exist:

```python
>>> # Safe access - returns default if any part of path is missing
>>> font = page.get(NamePath.Resources.Font.F1, None)
>>> if font is not None:
...     # Process the font
```

## Error messages

When a key is not found, NamePath provides contextual error messages showing
exactly where traversal failed:

```{eval-rst}
.. doctest::

    >>> pdf = Pdf.new()
    >>> pdf.Root.A = Dictionary(B=Dictionary())

    >>> pdf.Root[NamePath.A.B.C]
    Traceback (most recent call last):
        ...
    KeyError: 'Key /C not found; traversed NamePath.A.B'
```

Type mismatches are also reported clearly:

```{eval-rst}
.. doctest::

    >>> pdf.Root.X = 42  # Not a dictionary

    >>> pdf.Root[NamePath.X.Y]
    Traceback (most recent call last):
        ...
    TypeError: Expected Dictionary or Stream at NamePath.X, got integer
```

## Array index support

NamePath supports both positive and negative array indices:

```{eval-rst}
.. doctest::

    >>> pdf = Pdf.new()
    >>> pdf.Root.Items = Array([10, 20, 30])

    >>> int(pdf.Root[NamePath.Items[0]])
    10

    >>> int(pdf.Root[NamePath.Items[-1]])  # Last element
    30
```

## Traversing streams

NamePath can traverse through Stream objects, accessing their dictionary keys:

```{eval-rst}
.. doctest::

    >>> pdf = Pdf.new()
    >>> stream = pikepdf.Stream(pdf, b"test data", Filter=Name.FlateDecode)
    >>> pdf.Root.MyStream = stream

    >>> pdf.Root[NamePath.MyStream.Filter]
    pikepdf.Name("/FlateDecode")
```

## Membership, deletion, and iteration

:::{versionadded} 10.14
`in`, `del`, `__iter__`, `__eq__`/`__hash__`, and `isinstance` support for
`NamePath`.
:::

`path in obj` tests whether the path can be traversed to a value, the same
way `obj[path]` would succeed or raise:

```{eval-rst}
.. doctest::

    >>> pdf = Pdf.new()
    >>> pdf.Root.AcroForm = Dictionary(SigFlags=3)

    >>> NamePath.AcroForm.SigFlags in pdf.Root
    True
    >>> NamePath.AcroForm.Missing in pdf.Root
    False
```

An empty `NamePath` is always considered "in" any object, since it resolves
to the object itself.

`del obj[path]` deletes the final component of the path, once the parent
has been traversed to, the same way `del obj['/Key']` deletes a single key:

```{eval-rst}
.. doctest::

    >>> pdf.Root.AcroForm = Dictionary(SigFlags=3, Fields=Array())
    >>> del pdf.Root[NamePath.AcroForm.SigFlags]
    >>> NamePath.AcroForm.SigFlags in pdf.Root
    False
```

This works for array elements too — `del obj[NamePath.Items[0]]` removes
index 0 of the `Items` array, after traversing to `Items`.

A `NamePath` is iterable, yielding its individual components (`str` for a
name, `int` for an array index) in order:

```{eval-rst}
.. doctest::

    >>> list(NamePath.A.B[0])
    ['/A', '/B', 0]
```

Two `NamePath` instances compare equal, and hash equally, if they describe
the same sequence of components, so a `NamePath` can be used as a dict key
or stored in a `set`:

```{eval-rst}
.. doctest::

    >>> NamePath.A.B == NamePath.A.B
    True
    >>> {NamePath.A.B, NamePath.A.B}
    {NamePath.A.B}
```

`isinstance(path, pikepdf.NamePath)` now works for any `NamePath` instance,
which means `pikepdf.NamePath` can be used directly in type annotations for
a function that accepts either a `Name` or a path:

```python
def f(key: pikepdf.Name | pikepdf.NamePath):
    return obj.get(key)
```

## Comparison with alternatives

### Without NamePath

```python
# Verbose and error-prone
try:
    font = page.Resources.Font.F1
except (KeyError, AttributeError):
    font = None

# Or with multiple get() calls
resources = page.get(Name.Resources)
if resources:
    font_dict = resources.get(Name.Font)
    if font_dict:
        font = font_dict.get('/F1')
```

### With NamePath

```python
# Concise and safe
font = page.get(NamePath.Resources.Font.F1)
```

## When to use NamePath

NamePath is most useful when:

- Accessing deeply nested structures (3+ levels)
- The intermediate path may not exist
- You want clear error messages showing where traversal failed
- Working with optional PDF structures that may or may not be present

For simple, shallow access where you know keys exist, standard attribute
notation remains appropriate:

```python
>>> page.Type      # Standard attribute access
>>> page.Contents  # Direct key on the page
```

The inheritable page keys -- `/MediaBox`, `/CropBox`, `/Resources` and
`/Rotate` -- are better read through the managed accessors
({attr}`~pikepdf.Page.mediabox`, {attr}`~pikepdf.Page.cropbox`,
{attr}`~pikepdf.Page.resources` and {attr}`~pikepdf.Page.rotation`), which
resolve values inherited from the `/Pages` tree rather than returning only what
is stored on the page. See {ref}`Working with pages <work_with_pages>`.
