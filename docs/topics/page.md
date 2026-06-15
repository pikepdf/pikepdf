(work_with_pages)=

# Working with pages

This section details with how to view and edit the contents of a page.

pikepdf is not an ideal tool for producing new PDFs from scratch -- and there are
many good tools for that, as mentioned elsewhere. pikepdf is better at inspecting,
editing and transforming existing PDFs.

`pikepdf.Page` objects can be thought of a subclass of `pikepdf.Dictionary`. Since
pages are important, they are special objects, and the `Pdf.pages` API will only
accept or return pikepdf.Page.

```{eval-rst}
.. doctest::

    >>> from pikepdf import Pdf, Page

    >>> example = Pdf.open('../tests/resources/congress.pdf')

    >>> page1 = example.pages[0]

    >>> page1
    <pikepdf.Page({
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

The page's `/Contents` key contains instructions for drawing the page content.
This is a {doc}`content stream <streams>`, which is a stream object
that follows special rules.

Also attached to this page is a `/Resources` dictionary, which contains a
single XObject image. The image is compressed with the `/DCTDecode` filter,
meaning it is encoded with the {abbr}`DCT (discrete cosine transform)`, so it is
a JPEG. pikepdf has special APIs for {doc}`working with images <images>`.

The `/MediaBox` describes the bounding box of the page in PDF pt units
(1/72" or 0.35 mm).

You *can* access the page dictionary data structure directly, but it's fairly
complicated. There are a number of rules, optional values and implied values.
To do so, you would access the `page1.obj` property, which returns the
underlying dictionary object that holds the page data.

:::{versionchanged} 9.0
The `Pdf.pages` API was made strict, and now accepts only pikepdf.Page
for its various functions. In most cases, if you intend to create a
Dictionary and use it as a page, all you need to do is be explicit:
`` `pikepdf.Page(pikepdf.Dictionary(Type=Name.Page)) ``
:::

:::{versionchanged} 8.x
The use of Python dictionary or pikepdf.Dictionary to represent pages
was deprecated.
:::

:::{versionchanged} 2.x
In pikepdf 2.x, the raw dictionary object was returned, and it was
necessary to manually wrap it with the support model:
`page = Page(pdf.pages[0])`. This is no longer necessary.
:::

## Page boxes

```{eval-rst}
.. doctest::

    >>> page1.trimbox
    pikepdf.Array([ 0, 0, 200, 304 ])
```

`Page` will resolve implicit information. For example, `page.trimbox`
will return an appropriate trim box for this page, which in this case is
equal to the media box. This happens even if the page does not define
a trim box.

### Prefer the managed accessors over raw dictionary keys

A page is described both by keys stored directly on its own dictionary and by
keys it *inherits* from the `/Pages` tree above it. The PDF specification allows
`/MediaBox`, `/CropBox`, `/Resources` and `/Rotate` to be set on an intermediate
node in the page tree and shared by every page beneath it -- so a page may have a
media box or a rotation even though its own dictionary contains no such key.

For this reason, prefer the managed accessors -- {attr}`~pikepdf.Page.mediabox`,
{attr}`~pikepdf.Page.cropbox`, {attr}`~pikepdf.Page.trimbox`,
{attr}`~pikepdf.Page.artbox`, {attr}`~pikepdf.Page.bleedbox` and
{attr}`~pikepdf.Page.rotation` -- over reaching into `page.obj` for the raw keys.
The managed accessors resolve inheritance, supply the specification's default
values, and normalize the result, so they are correct in cases where the raw key
is simply absent. Accessing `page.obj.MediaBox` or `page.Rotate` directly returns
only what is stored on the page itself and raises `AttributeError` when the value
is inherited rather than local.

## Page rotation

A page's rotation is the `/Rotate` entry: the number of degrees, in multiples of
90, by which the page is rotated clockwise when displayed or printed. Like the
page boxes, `/Rotate` is inheritable, so reading `page.Rotate` directly is
unreliable -- it returns only a rotation stored on the page itself.

Use the {attr}`~pikepdf.Page.rotation` property instead. It reports the
*effective* rotation, resolving an inherited `/Rotate` and normalizing the result
to the range `[0, 360)`, and returns `0` when no rotation is set:

```{eval-rst}
.. doctest::

    >>> page1.rotation
    0
```

Assigning to {attr}`~pikepdf.Page.rotation` sets the absolute rotation. To rotate
relative to the current value, use {meth}`~pikepdf.Page.rotate` with
``relative=True``:

```{eval-rst}
.. doctest::

    >>> page1.rotation = 90       # set absolute rotation
    >>> page1.rotation
    90
    >>> page1.rotate(90, relative=True)   # add another 90 degrees, clockwise
    >>> page1.rotation
    180
```

:::{note}
Avoid setting `page.Rotate` directly. A value such as ``page.Rotate = -90`` is
accepted but is not normalized, and some older versions of qpdf mishandled
non-normalized rotations when transforming pages (for example in
{meth}`~pikepdf.Page.add_overlay`). Assigning through
{attr}`~pikepdf.Page.rotation`, or rotating with {meth}`~pikepdf.Page.rotate`,
keeps the stored value well-formed.
:::
