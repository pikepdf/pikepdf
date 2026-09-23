(type-safety)=

# PDF type safety with explicit mode

> Explicit is better than implicit.
>
> — Tim Peters, *The Zen of Python* ({pep}`20`)

pikepdf is moving from *implicit* conversion, where values read from a PDF are
quietly turned into Python types, to *explicit* conversion, where they keep
their PDF type until you ask for a Python value. This page explains why, shows
what the difference looks like in real code, and sets out the timetable. For
the reference details of each API mentioned here, see
{ref}`Explicit conversion mode <explicit-conversion>` in the object model
topic.

## PDFs are weakly typed

Every object in a PDF has a type: boolean, integer, real, string, name, array,
dictionary, stream, or null. The file's syntax makes the type of each value
unambiguous: `1024` is an integer, `(1024)` is a string, `/1024` is a name.

The file format does not say what type a value *should* have. That knowledge
lives in the prose of the PDF specification, table by table: an image's
`/Width` must be an integer, a page's `/MediaBox` must be an array of four
numbers, and so on. There is no schema in the file and nothing that enforces
one. A program that reads a PDF only finds out whether `/Width` is an integer
when it looks.

pikepdf's development began in 2016, when Python type checking was still in
its infancy. Type hints had been standardized only the year before, mypy was
experimental, and most Python libraries, this one included, were designed
around duck typing. The natural choice then was to convert each PDF scalar to
the nearest Python type and let Python's dynamism do the rest. That choice has
aged poorly, for the reasons below.

## PDF types are not Python types

The "nearest Python type" for a PDF scalar is close to it, but not the same
thing.

**A PDF integer is not a Python `int`.** Python integers are unbounded. PDF
integers are bounded; qpdf, and so pikepdf, stores them as signed 64-bit
values. A PDF that contains an integer too large for that range cannot be
read as an integer at all:

```{eval-rst}
.. doctest::

    >>> pikepdf.Object.parse(b'99999999999999999999')
    Traceback (most recent call last):
        ...
    pikepdf._core.PdfError: parsed object (offset 0): treating object as null because of error during parsing: overflow/underflow converting 99999999999999999999 to 64-bit integer
```

Going the other way, a Python `int` outside that range cannot be stored in a
PDF:

```{eval-rst}
.. doctest::

    >>> pikepdf.Array([2**64])
    Traceback (most recent call last):
        ...
    OverflowError: value is out of range for a 64-bit PDF integer
```

**A PDF real is not a Python `float` or `Decimal`.** PDF reals are written
as plain decimal numbers with no exponent: `0.00001` is a real, and `1e-5` is
not a number at all. A Python `float` is a binary approximation that may not
equal the decimal digits in the file. {class}`~decimal.Decimal`, which pikepdf
uses to preserve those digits, can hold values such as `Decimal('1E-20')` that
no PDF real can express. When pikepdf writes such a value it has to round it
to a fixed number of decimal places, and a small enough value becomes `0`.

```{eval-rst}
.. doctest::

    >>> from decimal import Decimal
    >>> pikepdf.Array([Decimal('1E-20')]).unparse()
    b'[ 0 ]'
```

**A PDF string is not a Python `str`.** A PDF string is a sequence of bytes.
Some strings hold *text*, such as a document title or a form field value,
encoded in PDFDocEncoding or UTF-16 (or, in PDF 2.0, UTF-8). For those,
treating the string as a `str` is the right thing to do. Other strings hold
arbitrary binary data, such as a document's `/ID`, and have no meaningful text
decoding. A {class}`pikepdf.String` gives you either view: `str()` decodes it
as text and `bytes()` returns the raw data.

## Well-formed is not the same as valid

A PDF can be *well-formed*, meaning its syntax parses, and still be *invalid*,
meaning its contents break the rules of the specification. Consider an image
XObject whose `/Width`, which the specification requires to be an integer,
was written by some buggy software as a string, a real, or even a name:

```text
<< /Type /XObject /Subtype /Image /Width 1024   ... >>   % valid
<< /Type /XObject /Subtype /Image /Width (1024) ... >>   % a string
<< /Type /XObject /Subtype /Image /Width 1024.0 ... >>   % a real
<< /Type /XObject /Subtype /Image /Width /1024  ... >>   % a name
```

All four are perfectly good PDF syntax. qpdf is very good at repairing PDFs
that are *not* well-formed: broken cross-reference tables, wrong stream
lengths, missing `endobj` keywords. But it cannot repair validity. It has no
way to know that `(1024)` was meant to be `1024`, or whether a `/Width` of
`/1024` is a typo or garbage.

In practice, many PDFs in the wild have problems with their internal typing.
pikepdf is a low-level tool, and reading, inspecting and fixing invalid PDFs is
squarely within its job. So it must report what is actually in the file, not
what ought to be there, and code that uses it needs a clean way to tell the
two apart.

## The implicit way

In *implicit* conversion mode, the current default, pikepdf converts PDF
scalars to Python types as you read them: integers become `int`, booleans
become `bool`, reals become `Decimal`, and null becomes `None`. Strings, names,
arrays and dictionaries stay as pikepdf objects.

For a valid PDF this works well and reads naturally. Here is how to find the
width of the image named `/Im0` on a page:

```python
width = page.Resources.XObject.Im0.Width
```

This gives `1024` for a valid file. For the invalid ones above, it gives
`pikepdf.String("1024")`, `Decimal('1024.0')` or `pikepdf.Name("/1024")`, with
no error. The bug appears later, somewhere else: `range(width)` raises a
`TypeError`, `width * height` quietly produces a `Decimal`, and a `/Width`
of `true` passes `isinstance(width, int)` because `bool` is a subclass of
`int`.

The one-liner also assumes a lot about the file. Robust code has to ask:

- What if the page has no `/Resources` dictionary?
- What if the resources have no `/XObject` dictionary?
- What if there is no `/Im0`?
- What if `/Im0` is not a stream?
- What if it is a stream, but not an image (a form XObject, say)?
- What if the image has no `/Width`?
- What if `/Width` has the wrong type?

Answering all of those in implicit mode looks something like this:

```{eval-rst}
.. testsetup::

    from pikepdf import Pdf, Dictionary, Name, NamePath, Stream, String

    pdf = Pdf.new()
    pdf.add_blank_page()
    page = pdf.pages[0]
    image = Stream(
        pdf, b'\x00' * 1024, Type=Name.XObject, Subtype=Name.Image,
        Width=1024, Height=1, BitsPerComponent=8, ColorSpace=Name.DeviceGray,
    )
    page.Resources = Dictionary(XObject=Dictionary(Im0=image))

.. testcode::

    def image_width(page, name):
        resources = page.obj.get(Name.Resources)
        if not isinstance(resources, Dictionary):
            return None
        xobjects = resources.get(Name.XObject)
        if not isinstance(xobjects, Dictionary):
            return None
        image = xobjects.get(name)
        if not isinstance(image, Stream):
            return None
        if image.get(Name.Subtype) != Name.Image:
            return None
        width = image.get(Name.Width)
        if isinstance(width, bool) or not isinstance(width, int):
            return None
        return width

    print(image_width(page, Name.Im0))

.. testoutput::

    1024
```

All of that just to find out how wide an image is. Every check is needed, and
forgetting any one of them is a latent bug that only an unusual file will
reveal. Note the `isinstance(width, bool)` test, which is easy to forget.

Type checkers cannot help, either. pikepdf's type hints say that
`image.Width` returns a `pikepdf.Object`, since that is the only honest
answer when the value could be anything. In implicit mode it may actually be
an `int`, a `Decimal`, `None`, or an object, so a type checker that believes
the hints is wrong about common pikepdf code, and cannot spot the bugs above.

## The explicit way

In *explicit* conversion mode, reading a value from a PDF always gives you a
pikepdf object: {class}`pikepdf.Integer`, {class}`pikepdf.Boolean`,
{class}`pikepdf.Real`, `pikepdf.String`, and so on. You convert it to Python
when you need a Python value, and the conversion checks the type for you.

### Getting a value or a default

When a missing or wrong-typed value should just be treated as absent,
{attr}`Page.resources <pikepdf.Page.resources>`, a
{class}`~pikepdf.NamePath` and a typed getter such as
{meth}`~pikepdf.Object.get_int` answer the questions in the list above in one
line:

```{eval-rst}
.. doctest::

    >>> page.resources.get_int(NamePath.XObject.Im0.Width)
    1024
```

`page.resources` finds the page's resources even when they are inherited from
the page tree, and gives an empty dictionary if the page has none. From there,
if any step of the path is missing or is not a dictionary, or if the final
value is not an integer, you get the default, which is `None` unless you give
one:

```{eval-rst}
.. doctest::

    >>> image.Width = String('1024')
    >>> page.resources.get_int(NamePath.XObject.Im0.Width) is None
    True
    >>> page.resources.get_int(NamePath.XObject.Missing.Width, 0)
    0
```

The typed getters work the same in either conversion mode, so this line is
safe to use today. Two questions are left over. A page whose `/Resources` is
not a dictionary at all makes `page.resources` raise `TypeError`. And the
line does not check the image's `/Subtype`; add a check of
`NamePath.XObject.Im0.Subtype` if that matters to you.

### Retrieving or failing

When a malformed file should be an error, explicit mode and the `as_*`
accessors let you retrieve a value or fail with a precise message:

```{eval-rst}
.. doctest::

    >>> with pikepdf.explicit_conversion():
    ...     image = page.resources[NamePath.XObject.Im0]
    ...     image.Width.as_int()
    Traceback (most recent call last):
        ...
    TypeError: Expected integer, got string

    >>> with pikepdf.explicit_conversion():
    ...     page.resources[NamePath.XObject.Im1]
    Traceback (most recent call last):
        ...
    KeyError: 'Key /Im1 not found; traversed NamePath.XObject'
```

A bad file now fails at the point where the bad value was read, with a message
that says what was wrong, instead of somewhere downstream.

### Repairing

Because pikepdf is often used to fix broken files, the accessors and getters
accept `coerce=True`, which also accepts values stored with a "nearby" type:
for `as_int`, a real (truncated toward zero) or a numeric string. That makes a
repair straightforward:

```{eval-rst}
.. doctest::

    >>> with pikepdf.explicit_conversion():
    ...     width = image.get_int(Name.Width, coerce=True)
    ...     if width is not None and not isinstance(image.Width, pikepdf.Integer):
    ...         image.Width = width  # write back a proper integer
    ...     image.Width
    pikepdf.Integer(1024)
```

A value that cannot be coerced, such as the name `/1024`, still returns the
default (or raises `TypeError` if no default is given), so `coerce=True`
widens what is accepted without hiding garbage.

:::{tip}
These examples use image dimensions because they are easy to follow. For real
work with images, use {meth}`pikepdf.Page.get_images` and
{class}`pikepdf.PdfImage`, which walk the resources for you (including images
nested inside form XObjects) and raise `TypeError` for a malformed image
rather than returning a wrong answer:

```{eval-rst}
.. doctest::

    >>> image.Width = Name('/1024')
    >>> try:
    ...     pikepdf.PdfImage(image).width
    ... except TypeError as e:
    ...     print(e)
    Image /Width has a value of the wrong type: pikepdf.Name("/1024")
```
:::

## Implicit vs explicit

| Implicit mode | Explicit mode |
| --- | --- |
| PDF scalars are silently converted to Python types. | PDF scalars stay PDF objects until you convert them. |
| A wrong type in an invalid PDF passes through unnoticed and causes bugs elsewhere, so safe access needs complicated checks. | A wrong type is caught when the value is unboxed, and the `as_*` accessors and `get_*` getters make wrong types easy to handle. |
| Type checkers cannot tell what common pikepdf code returns. | Type checkers can read pikepdf code and spot bugs early. |
| Terse on the happy path. | A little more verbose on the happy path. |
| Verbose on the failure path. | Concise on the failure path. |

Explicit mode does not make everything more verbose. Arithmetic and
comparisons on `Integer` and `Real` work directly and give native Python
results, so `mediabox[2] - mediabox[0] > 100` needs no change, and raises
`TypeError` instead of giving a wrong answer if a coordinate is not a number.
See {ref}`Explicit conversion mode <explicit-conversion>` for the full
behavior.

## Three ways to use explicit mode

**Per document.** Pass `conversion_mode='explicit'` when opening or creating a
PDF. All objects read from that document are explicit, whichever thread reads
them, and no other document is affected. This is the right choice for a
library that handles PDFs on behalf of an application.

```python
pdf = pikepdf.open('input.pdf', conversion_mode='explicit')
new_pdf = pikepdf.new(conversion_mode='explicit')
pdf.conversion_mode = 'implicit'  # can be changed later
```

**Globally.** Set the default for the whole process. This suits applications,
scripts and test suites; a library should not change a global setting that
belongs to its host application.

```python
pikepdf.set_object_conversion_mode('explicit')
```

**For a block of code.** The {func}`pikepdf.explicit_conversion` and
{func}`pikepdf.implicit_conversion` context managers change the mode for the
current thread for the duration of a `with` block. They are useful for
migrating a code base one function at a time, or for calling old code that
still expects implicit mode.

```python
with pikepdf.explicit_conversion():
    width = image.Width.as_int()

with pikepdf.implicit_conversion():
    legacy_function(pdf)
```

When more than one applies, the context manager wins, then the per-document
mode, then the global default.

If your code must work in both modes during a transition, use the
mode-independent APIs: the `get_*` typed getters, {meth}`~pikepdf.Object.get_raw`,
the `as_*` accessors, and {func}`pikepdf.unbox`. The
{ref}`migration checklist <migrating-explicit>` lists the changes that
switching modes can silently break.

(type-safety-deprecation)=

## Deprecation schedule

Implicit mode is being phased out over three major releases:

| Version | Change |
| --- | --- |
| v11 | Implicit mode remains the default, but pikepdf issues a `DeprecationWarning` whenever an implicit conversion happens, with advice on how to fix the code that triggered it. |
| v12 | Explicit mode becomes the default. Implicit mode is still available, but you must opt in to it. |
| v13 | Implicit mode is removed. |

You do not need to wait for v11. The APIs described on this page are available
now, and code written with them works in both modes. A good first step is to
run your test suite with `pikepdf.set_object_conversion_mode('explicit')` in
effect and see what breaks.
