.. _docassembly:

PDF split, merge, and document assembly
***************************************

This section discusses working with PDF pages: splitting, merging, copying,
deleting. We're treating pages as a unit, rather than working with the content of
individual pages.

Let’s continue with ``fourpages.pdf`` from the :ref:`tutorial`.

.. ipython::

    In [1]: from pikepdf import Pdf

    In [2]: pdf = Pdf.open('../tests/resources/fourpages.pdf')

.. _splitpdf:

Split a PDF into one page PDFs
------------------------------

All we need is a new PDF to hold the destination page.

.. ipython::
    :verbatim:

    In [1]: pdf = Pdf.open('../tests/resources/fourpages.pdf')

    In [5]: for n, page in enumerate(pdf.pages):
       ...:     dst = Pdf.new()
       ...:     dst.pages.append(page)
       ...:     dst.save('{:02d}.pdf'.format(n))

.. note::

    This example will transfer data associated with each page, so
    that every page stands on its own. It will *not* transfer some metadata
    associated with the PDF as a whole, such the list of bookmarks.

.. _mergepdf:

Merge (concatenate) PDF from several PDFs
-----------------------------------------

We create an empty ``Pdf`` which will be the container for all the others.

.. ipython::
    :verbatim:

    In [1]: from glob import glob

    In [1]: pdf = Pdf.new()

    In [1]: for file in glob('*.pdf'):
       ...:     src = Pdf.open(file)
       ...:     pdf.pages.extend(src.pages)

    In [1]: pdf.save('merged.pdf')

This code sample is enough to merge most PDFs, but there are some things it
does not do that a more sophisicated function might do. One could call
:meth:`pikepdf.Pdf.remove_unreferenced_resources` to remove unreferenced
resources. It may also be necessary to chose the most recent version of all
source PDFs. Here is a more sophisticated example:

.. ipython::
    :verbatim:

    In [1]: from glob import glob

    In [1]: pdf = Pdf.new()

    In [1]: version = pdf.pdf_version

    In [1]: for file in glob('*.pdf'):
       ...:     src = Pdf.open(file)
       ...:     version = max(version, src.pdf_version)
       ...:     pdf.pages.extend(src.pages)

    In [1]: pdf.remove_unreferenced_resources()

    In [1]: pdf.save('merged.pdf', min_version=version)

This improved example would still leave metadata blank. It's up to you
to decide how to combine metadata from multiple PDFs.

Reversing the order of pages
----------------------------

Suppose the file was scanned backwards. We can easily reverse it in
place - maybe it was scanned backwards, a common problem with automatic
document scanners.

.. ipython::

    In [1]: pdf.pages.reverse()

.. ipython::

    In [1]: pdf

Pretty nice, isn’t it? But the pages in this file already were in correct
order, so let’s put them back.

.. ipython::

    In [1]: pdf.pages.reverse()

.. _copyother:

Copying pages from other PDFs
-----------------------------

Now, let’s add some content from another file. Because ``pdf.pages`` behaves
like a list, we can use ``pages.extend()`` on another file's pages.

.. ipython::

    In [1]: pdf = Pdf.open('../tests/resources/fourpages.pdf')

    In [1]: appendix = Pdf.open('../tests/resources/sandwich.pdf')

    In [2]: pdf.pages.extend(appendix.pages)

We can use ``pages.insert()`` to insert into one of more pages into a specific
position, bumping everything else ahead.

Copying pages between ``Pdf`` objects will create a shallow copy of the source
page within the target ``Pdf``, rather than the typical Python behavior of
creating a reference. As such, modifying ``pdf.pages[-1]`` will not affect
``appendix.pages[0]``. (Normally, assigning objects between Python lists creates
a reference, so that the two objects are identical, ``list[0] is list[1]``.)

.. ipython::

    In [3]: graph = Pdf.open('../tests/resources/graph.pdf')

    In [4]: pdf.pages.insert(1, graph.pages[0])

    In [5]: len(pdf.pages)

We can also replace specific pages with assignment (or slicing).

.. ipython::

    In [1]: congress = Pdf.open('../tests/resources/congress.pdf')

    In [1]: pdf.pages[2].objgen

    In [1]: pdf.pages[2] = congress.pages[0]

    In [1]: pdf.pages[2].objgen

The method above will break any indirect references (such as table of contents
entries and hyperlinks) within ``pdf`` to ``pdf.pages[2]``. Perhaps that is the
behavior you want, if the replacement means those references are no longer
valid. This is shown by the change in :attr:`pikepdf.Object.objgen`.

Emplacing pages
~~~~~~~~~~~~~~~

To preserve indirect references, use :meth:`pikepdf.Object.emplace`,
which will (conceptually) delete all of the content of target and replace it
with the content of source, thus preserving indirect references to the page.
(Think of this as demolishing the interior of a house, but keeping it at the
same address.)

.. ipython::

    In [1]: pdf = Pdf.open('../tests/resources/fourpages.pdf')

    In [1]: congress = Pdf.open('../tests/resources/congress.pdf')

    In [1]: pdf.pages[2].objgen

    In [1]: pdf.pages.append(congress.pages[0])  # Transfer page to new pdf

    In [1]: pdf.pages[2].emplace(pdf.pages[-1])

    In [1]: del pdf.pages[-1]  # Remove donor page

    In [1]: pdf.pages[2].objgen

Copying pages within a PDF
--------------------------

As you may have guessed, we can assign pages to copy them within a ``Pdf``:

.. ipython::

    In [1]: pdf = Pdf.open('../tests/resources/fourpages.pdf')

    In [1]: pdf.pages[3] = pdf.pages[0]  # The last shall be made first

As above, copying a page creates a shallow copy rather than a Python object
reference.

Also as above :meth:`pikepdf.Object.emplace` can be used to create a copy that
preserves the functionality of indirect references within the PDF.

Using counting numbers
----------------------

Because PDF pages are usually numbered in counting numbers (1, 2, 3…),
pikepdf provides a convenience accessor ``.p()`` that uses counting
numbers:

.. ipython::
    :verbatim:

    In [1]: pdf.pages.p(1)        # The first page in the document

    In [1]: pdf.pages[0]          # Also the first page in the document

    In [1]: pdf.pages.remove(p=1)   # Remove first page in the document

To avoid confusion, the ``.p()`` accessor does not accept Python slices,
and ``.p(0)`` raises an exception. It is also not possible to delete using it.

PDFs may define their own numbering scheme or different numberings for
different sections, such as using Roman numerals for an introductory section.
``.pages`` does not look up this information.

Pages information from Root
---------------------------

.. warning::

    It's possible to obtain page information through :attr:`pikepdf.Pdf.Root`
    object but **not recommended**. (In PDF parlance, this is the ``/Root``
    object).

    The internal consistency of the various ``/Page`` and ``/Pages`` is not
    guaranteed when accessed in this manner, and in some PDFs the data structure
    for these is fairly complex. Use the ``.pages`` interface.
