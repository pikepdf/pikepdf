.. _page-copying:

Copying and updating pages
**************************

You can rearrange or duplicate pages within a PDF, with an important caveat:

.. warning::

    ``pdf.pages[0] = pdf.pages[42]`` will create a shallow copy of
    ``pdf.pages[42]``, unlike the usual behavior in Python.

Assigning one page to another within the same PDF will create a shallow copy of
the source page. This does differ from the usual Python semantics, where
assigning a list element to another element in the same list would merely create
two references to an identical object. (Normally after setting ``list[0] =
list[1]``, ``list[0] is list[1]``.) We break this convention with the shallow
copy, and only guarantee ``page[0] == page[1]``.)

There is one important reason we have to do it this way: suppose that there
was a table of contents entry that points to ``pdf.pages[42]``. After we set
``pages[0]`` to be the same, where should the table of contents entry point?
We leave it pointed at ``pdf.pages[42]``.

What if there was a table of contents entry that referenced ``pages[0]``?
(In PDFs, the table of contents references a page object, not a page number.)
Is that entry still valid after reassignment? As the library, we don't know.
As the application developer, you have to decide. (pikepdf does not currently
have support code for managing table of contents objects, but you can
manipulate them.)

Updating a page in place
========================

Use :meth:`pikepdf.Object.emplace` to emplace one PDF page over top of another
while preserving all references to the original page. ``emplace()`` sets all
of the keys and values of the pages to be equal.
