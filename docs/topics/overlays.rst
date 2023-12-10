.. _overlays:

Overlays, underlays, watermarks, n-up
=====================================

You can use pikepdf to overlay pages or other content on top of other pages.

This might be used to do watermarks (typically an underlay, drawn before everything
else), n-up (compositing multiple individual pages on a large page, such as converting
slides from a presentation to 4-up for reading and printing).

If you are looking to merge pages from different PDFs, see :ref:`mergepdf`.

In this example we use :meth:`pikepdf.Page.add_overlay` to draw a thumbnail of
of the second page onto the first page.

.. code-block:: python

    >>> from pikepdf import Pdf, Page, Rectangle

    >>> pdf = Pdf.open(...)

    >>> destination_page = Page(pdf.pages[0])

    >>> thumbnail = Page(pdf.pages[1])

    >>> destination_page.add_overlay(thumbnail, Rectangle(0, 0, 300, 300))

    >>> pdf.save("page1_with_page2_thumbnail.pdf")

The :class:`pikepdf.Rectangle` specifies the position on the target page into which
the other page can be drawn. The object will be drawn centered in a way that
fills as much space as possible while preserving aspect ratio.

Use :meth:`pikepdf.Page.add_underlay` instead if you want content drawn underneath.
It is possible content drawn this way will be overdrawn by other objects.

Use :attr:`pikepdf.Page.trimbox` to get a page's dimensions.

``add_overlay`` will copy content across ``Pdf`` objects as needed, and can copy
other pages or other Form XObjects.

``add_overlay`` also preserves aspect ratio.
Use :meth:`pikepdf.Page.as_form_xobject` and
:meth:`pikepdf.Page.calc_form_xobject_placement` if you want more precise control
over placement.

Composition works using Form XObjects, which is how PDF captures of a group of
related objects for drawing. Some very basic PDF software may not support them,
or may fail to detect images contained within.

When perform n-up composition, it will work better to create your composition
within the existing document, rather than in a new document. Transforming the
existing document will ensure that metadata, annotations and hyperlinks are
preserved. For example, to convert 16 slides to 4×4-up pages for printing,
add four pages onto the end of the file, draw the slides onto the target pages,
and then delete the slides.

By default, ``add_overlay`` encapsulates the existing content stream in a way
that ensures the transformation matrix is first reset, since this behavior
aligns with user expectations. This adds a ``q/Q`` pair to (push/pop graphics
stack) to existing content streams. To disable this (usually desired) behavior
use ``push_stack=False``.
