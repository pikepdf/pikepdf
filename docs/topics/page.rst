.. _work_with_pages:

Working with pages
==================

This section details with how to view and edit the contents of a page.

pikepdf is not an ideal tool for producing new PDFs from scratch -- and there are
many good tools for that, as mentioned elsewhere. pikepdf is better at inspecting,
editing and transforming existing PDFs.

Page objects in PDFs are dictionaries.

.. ipython::

    In [1]: from pikepdf import Pdf, Page

    In [1]: example = Pdf.open('../tests/resources/congress.pdf')

    In [1]: pageobj1 = example.pages[0]

    In [1]: pageobj1

The page's ``/Contents`` key contains instructions for drawing the page content.
This is a :doc:`content stream <streams>`, which is a stream object
that follows special rules.

Also attached to this page is a ``/Resources`` dictionary, which contains a
single XObject image. The image is compressed with the ``/DCTDecode`` filter,
meaning it is encoded with the :abbr:`DCT (discrete cosine transform)`, so it is
a JPEG. pikepdf has special APIs for :doc:`working with images <images>`.

The ``/MediaBox`` describes the bounding box of the page in PDF pt units
(1/72" or 0.35 mm).

You *can* access the page dictionary data structure directly, but it's fairly
complicated. There are a number of rules, optional values and implied values.
It's easier to use page helpers, which ensure that the page is modified in a
semantically correct manner.

Page helpers
------------

pikepdf provides a helper class, :class:`pikepdf.Page`, which provides
higher-level functions to manipulate pages than the standard page dictionary
used in the previous examples.

Currently pikepdf does not automatically return helper classes. You must
initialize them. In a future release, it will return them automatically.

.. ipython::

    In [1]: from pikepdf import Pdf, Page

    In [1]: page = Page(pageobj1)

    In [1]: page.trimbox

One advantage of page helpers is that they resolve implicit information. For example,
``page.trimbox`` will return an appropriate trim box for this page, which in this
case is equal to the media box.
