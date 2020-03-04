.. _outlines:

Outlines
========
Outlines (sometimes also called *bookmarks*) are shown in a the PDF viewer
aside of the page, allowing for navigation within the document.

Creating outlines
-----------------
Outlines can be created from scratch, e.g. when assembling a set of PDF files
into a single document.

.. ipython::
    :verbatim:

    In [1]: from glob import glob

    In [1]: from pikepdf import Pdf, Outlines, OutlinesItem

    In [1]: pdf = Pdf.new()

    In [1]: outlines = Outlines(pdf)

    In [1]: page_count = 0

    In [1]: for file in glob('*.pdf'):
       ...:     src = Pdf.open(file)
       ...:     oi = OutlinesItem(file, page_count)
       ...:     outlines.root.append(oi)
       ...:     page_count += len(src.pages)
       ...:     pdf.pages.extend(src.pages)

    In [1]: outlines.save()

    In [1]: pdf.save('merged.pdf')

Editing outlines
----------------
Existing outlines can be edited. Entries can be moved and renamed without affecting
the targets they refer to.

Destinations
------------
Destinations tell the PDF viewer where to go when navigating through outline items.
The simplest case is a reference to a page, together with the page location, e.g.
``Fit`` (default). However, named destinations can also be assigned.

The PDF specification allows for either use of a destination (``Dest`` attribute) or
an action (``A`` attribute), but not both on the same element. ``OutlinesItem`` elements
handle this as follows:

* When creating new outline entries passing in a page number or reference name,
  the ``Dest`` attribute is used.
* When editing an existing entry with an assigned action, it is left as-is, unless a
  ``destination`` is set. The latter is preferred if both are present.

.. ipython::
    :verbatim:

    In [1]: oi = OutlinesItem('First', get_page_destination(pdf, 0, 'FitB', top=1000))


Outlines structure
------------------
For nesting outlines, add items to ``root`` of the main element or the ``children`` list
of another ``OutlinesItem``.

.. ipython::
    :verbatim:

    In [1]: main_item = OutlinesItem('Main', 0)

    In [1]: outlines.root.append(main_item)

    In [1]: main_item.children.append(OutlinesItem('A', 1))
