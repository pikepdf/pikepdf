Name trees
**********

A name trees is a compound data structure in a PDFs, composed from primitive data
types, namely PDF dictionaries and arrays. pikepdf provides an interface that
significantly simplifies this complex data structure, making it as simple as
manipulating any Python dictionary.

In many cases, the |pdfrm| specifies that some information is stored in a name
tree. To access and manipulate those objects, use :class:`pikepdf.NameTree`.

Some objects that are stored in name trees include the objects in
``Pdf.Root.Names``:

* ``Dests``: named destinations
* ``URLS``: URLs
* ``JavaScript``: embedded PDF JavaScript
* ``Pages``: named pages
* ``IDS``: digital identifiers

Attached files (or embedded files) are managed in a name tree, but pikepdf
provides an interface specifically for managing them. Use that instead.

.. doctest::

    >>> from pikepdf import Pdf, Page, NameTree

    >>> pdf = Pdf.open('../tests/resources/outlines.pdf')

    >>> nt = NameTree(pdf.Root.Names.Dests)

    >>> print([k for k in nt.keys()])
    ['0', '1', '2', '3', '4', '5', '6', '7', '8']

    >>> nt['2'][0].objgen, nt['2'][1], nt['2'][2]
    ((3, 0), pikepdf.Name("/XYZ"), Decimal('89.29'))
