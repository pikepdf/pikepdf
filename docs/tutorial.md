(tutorial)=

# Tutorial

:::{figure} images/pike-cartoon.png
:align: right
:figwidth: 30%
:::

This brief tutorial should give you an introduction and orientation to pikepdf's
paradigm and syntax. From there, we refer to you various topics.

## Opening and saving PDFs

In contrast to better known PDF libraries, pikepdf uses a single object to
represent a PDF, whether reading, writing or merging. We have cleverly named
this {class}`pikepdf.Pdf`. In this documentation, a `Pdf` is a class that
allows manipulating the PDF, meaning the "file" (whether it exists in memory or on
a file system).

```python
from pikepdf import Pdf

with Pdf.open('sample.pdf') as pdf:
    pdf.save('output.pdf')
```

You may of course use `from pikepdf import Pdf as ...` if the short class
name conflicts or `from pikepdf import Pdf as PDF` if you prefer uppercase.

{func}`pikepdf.open` is a shorthand for {meth}`pikepdf.Pdf.open`.

The PDF class API follows the example of the widely-used
[Pillow image library](https://pillow.readthedocs.io/en/latest/). For clarity
there is no default constructor since the arguments used for creation and
opening are different. To make a new empty PDF, use {func}`Pdf.new()` not `Pdf()`.

`Pdf.open()` also accepts seekable streams as input, and {meth}`pikepdf.Pdf.save()` accepts
streams as output. {class}`pathlib.Path` objects are fully supported wherever
pikepdf accepts a filename.

## Creating PDFs

Using {meth}`pikepdf.Pdf.new`, you can create a new PDF from scratch. pikepdf
is not primarily a PDF generation library - you may find other libraries easier
to use for that purpose. However, pikepdf does provide a few useful functions
for creating PDFs.

```python
from pikepdf import Pdf

pdf = Pdf.new()
pdf.add_blank_page()
pdf.save('blank_page.pdf')
```

## Inspecting pages

Manipulating pages is fundamental to PDFs. pikepdf presents the pages in a PDF
through the {attr}`pikepdf.Pdf.pages` property, which follows the `list`
protocol. As such page numbers begin at 0.

Let’s open a simple PDF that contains four pages.

```{eval-rst}
.. doctest::

    >>> from pikepdf import Pdf

    >>> pdf = Pdf.open('../tests/resources/fourpages.pdf')
```

How many pages?

```{eval-rst}
.. doctest::

    >>> len(pdf.pages)
    4
```

pikepdf integrates with IPython and Jupyter's rich object APIs so that you can
view PDFs, PDF pages, or images within PDF in a IPython window or Jupyter
notebook. This makes it easier to test visual changes.

```python
>>> pdf
« In Jupyter you would see the PDF here »

>>> pdf.pages[0]
« In Jupyter you would see an image of the PDF page here »
```

You can also examine individual pages, which we’ll explore in the next
section. Suffice to say that you can access pages by indexing them and
slicing them.

```python
>>> pdf.pages[0]
« In Jupyter you would see an image of the PDF page here »
```

:::{note}
{meth}`pikepdf.Pdf.open` can open almost all types of encrypted PDF! Just
provide the `password=` keyword argument.
:::

For more details on document assembly, see
{ref}`PDF split, merge and document assembly <docassembly>`.

## PDF dictionaries

In PDFs, the main data structure is the **dictionary**, a key-value data
structure much like a Python `dict` or `attrdict`. The major difference is
that the keys can only be **names**, and the values can only be PDF types, including
other dictionaries.

PDF dictionaries are represented as {class}`pikepdf.Dictionary` objects, and names
are of type {class}`pikepdf.Name`.

```{eval-rst}
.. doctest::

    >>> from pikepdf import Pdf

    >>> example = Pdf.open('../tests/resources/congress.pdf')

    >>> example.Root  # Show the document's root dictionary
    pikepdf.Dictionary(Type="/Catalog")({
      "/Pages": {
        "/Count": 1,
        "/Kids": [ <Pdf.pages.from_objgen(4,0)> ],
        "/Type": "/Pages"
      },
      "/Type": "/Catalog"
    })
```

## Page dictionaries

A page in a PDF is just a dictionary with certain required keys that is
referenced by the PDF's "page tree". (pikepdf manages the page tree for you,
and wraps page dictionaries to provide special functions
that help with managing pages.) A {class}`pikepdf.Page` is a wrapper around a PDF
page dictionary that provides many useful functions for working on pages.

```{eval-rst}
.. doctest::

    >>> from pikepdf import Pdf

    >>> example = Pdf.open('../tests/resources/congress.pdf')

    >>> page1 = example.pages[0]

    >>> obj_page1 = page1.obj

    >>> obj_page1
    <pikepdf.Dictionary(Type="/Page")({
      "/Contents": pikepdf.Stream(owner=<...>, data=b'q\n200.0000 0 0 304.0'..., {
        "/Length": 50
      }),
      "/MediaBox": [ 0, 0, 200, 304 ],
      "/Parent": <reference to /Pages>,
      "/Resources": {
        "/XObject": {
          "/Im0": pikepdf.Stream(owner=<...>, data=<...>, {
            "/BitsPerComponent": 8,
            "/ColorSpace": "/DeviceRGB",
            "/Filter": [ "/DCTDecode" ],
            "/Height": 1520,
            "/Length": 192956,
            "/Subtype": "/Image",
            "/Type": "/XObject",
            "/Width": 1000
          })
        }
      },
      "/Type": "/Page"
    })>
```

## repr() output

Let's observe the page's `repr()` output:

```{eval-rst}
.. doctest::

    >>> repr(page1)
    '<pikepdf.Page({\n  "/Contents": pikepdf.Stream(owner=<...>, data=b\'q\\n200.0000 0 0 304.0\'..., {\n    "/Length": 50\n  }),\n  "/MediaBox": [ 0, 0, 200, 304 ],\n  "/Parent": <reference to /Pages>,\n  "/Resources": {\n    "/XObject": {\n      "/Im0": pikepdf.Stream(owner=<...>, data=<...>, {\n        "/BitsPerComponent": 8,\n        "/ColorSpace": "/DeviceRGB",\n        "/Filter": [ "/DCTDecode" ],\n        "/Height": 1520,\n        "/Length": 192956,\n        "/Subtype": "/Image",\n        "/Type": "/XObject",\n        "/Width": 1000\n      })\n    }\n  },\n  "/Type": "/Page"\n})>'
```

The angle brackets in the output indicate that this object cannot be constructed
with a Python expression because it contains a reference. When angle brackets
are omitted from the `repr()` of a pikepdf object, then the object can be
replicated with a Python expression, such as `eval(repr(x)) == x`. Pages
typically have indirect references to themselves and other pages, so they
cannot be represented as an expression.

## Item and attribute notation

Dictionary keys may be looked up using attributes (`page1.Type`) or
keys (`page1['/Type']`).

```{eval-rst}
.. doctest::

    >>> page1.Type      # preferred notation for standard PDF names
    pikepdf.Name("/Page")

    >>> page1['/Type']  # also works
    pikepdf.Name("/Page")
```

By convention, pikepdf uses attribute notation for standard names (the names
that are normally part of a dictionary, according to the {{ pdfrm }}),
and item notation for names that may not always appear. For example, the images
belong to a page always appear at `page.Resources.XObject` but the names
of images are arbitrarily chosen by whatever software generates the PDF (`/Im0`,
in this case). (Whenever expressed as strings, names begin with `/`.)

```python
>>> page1.Resources.XObject['/Im0']
```

Item notation here would be quite cumbersome:
`['/Resources']['/XObject]['/Im0']` (not recommended).

Attribute notation is convenient, but not robust if elements are missing. For
elements that are not always present, you can use `.get()`, which behaves like
`dict.get()` in core Python. A library such as [glom](https://github.com/mahmoud/glom) might help when working with complex
structured data that is not always present.

(For now, we'll set aside what a page's `Resources.XObject`
are for. See {ref}`Working with pages <work_with_pages>` for details.)

## Deleting pages

Removing pages is easy too.

```{eval-rst}
.. doctest::

    >>> del pdf.pages[1:3]  # Remove pages 2-3 labeled "second page" and "third page"
```

```{eval-rst}
.. doctest::

    >>> len(pdf.pages)
    2
```

## Saving changes

:::{figure} /images/save-pike.jpg
:align: right
:alt: Sign that reads "Help the pike survive"
:figwidth: 40%

Saving pike.
:::

Naturally, you can save your changes with {meth}`pikepdf.Pdf.save`.
`filename` can be a {class}`pathlib.Path`, which we accept everywhere.

```python
>>> pdf.save('output.pdf')
```

You may save a file multiple times, and you may continue modifying it after
saving. For example, you could create an unencrypted version of document, then
apply a watermark, and create an encrypted version.

:::{note}
You may not overwrite the input file (or whatever Python object provides the
data) when saving or at any other time. pikepdf assumes it will have
exclusive access to the input file or input data you give it to, until
`pdf.close()` is called.
:::

### Saving secure PDFs

To save an encrypted (password protected) PDF, use a {class}`pikepdf.Encryption`
object to specify the encryption settings. By default, pikepdf selects the
strongest security handler and algorithm (AES-256), but allows full access to
modify file contents. A {class}`pikepdf.Permissions` object can be used to
specify restrictions.

```python
>>> no_extracting = pikepdf.Permissions(extract=False)

>>> pdf.save('encrypted.pdf', encryption=pikepdf.Encryption(
...      user="user password", owner="owner password", allow=no_extracting
... ))
```

Refer to our {ref}`security documentation <security>` for more information on
user/owner passwords and PDF permissions.

### Running qpdf through Jobs

pikepdf can access all of the features of the qpdf command line program, and
can even execute qpdf-like command lines.

```python
>>> from pikepdf import Job

>>> Job(['pikepdf', '--check', '../tests/resources/fourpages.pdf'])
```

You can also specify jobs in qpdf Job JSON:

```python
>>> job_json = {'inputFile': '../tests/resources/fourpages.pdf', 'check': ''}

>>> Job(job_json).run()
```

## Next steps

Have a look at pikepdf topics that interest you, or jump to our detailed API
reference...
