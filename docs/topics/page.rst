.. _work_with_pages:

Working with pages
==================

.. ipython::

  In [1]: import pikepdf

  In [1]: page1.MediaBox

  In [1]: pikepdf.Array([ 0, 0, 200, 304 ])

The page's ``/Contents`` key contains instructions for drawing the page content.
Also attached to this page is a ``/Resources`` dictionary, which contains a
single XObject image. The image is compressed with the ``/DCTDecode`` filter,
meaning it is encoded with the :abbr:`DCT (discrete cosine transform)`, so it is
a JPEG. [#]_

.. [#] Not all JPEGs can be inserted verbatim.

Page helpers
------------

pikepdf provides a helper class, :class:`pikepdf.Page`, which provides
higher-level functions to manipulate pages than the standard page dictionary
used in the previous examples.

.. ipython::

    In [1]: from pikepdf import Pdf, Page

    In [1]: example = Pdf.open('../tests/resources/congress.pdf')

    In [1]: pageobj1 = example.pages[0]

    In [1]: page = Page(pageobj1)

Power features are available, such as capturing a page as a Form XObject. A
Form XObject groups all of the content on a page together, so that it can be
stamped on other pages.

.. ipython::

    In [1]: formxobj = page.as_form_xobject()

    In [1]: formxobj
