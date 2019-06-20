Manipulating pages
------------------

pikepdf presents the pages in a PDF through the :attr:`pikepdf.Pdf.pages`
property, which follows the ``list`` protocol. As such page numbers begin at 0.

Since one of the most things people want to do is split and merge PDF pages,
we'll by exploring that.

Let’s look at a simple PDF that contains four pages.

.. ipython::

    In [1]: from pikepdf import Pdf

    In [2]: pdf = Pdf.open('../tests/resources/fourpages.pdf')

How many pages?

.. ipython::

    In [2]: len(pdf.pages)

pikepdf integrates with IPython and Jupyter's rich object APIs so that you can
view PDFs, PDF pages, or images within PDF in a IPython window or Jupyter
notebook. This makes it to test visual changes.

.. ipython::
    :verbatim:

    In [1]: pdf
    Out[1]: « In Jupyter you would see the PDF here »

You can also examine individual pages, which we’ll explore in the next
section. Suffice to say that you can access pages by indexing them and
slicing them.

.. ipython::

    In [1]: pdf.pages[-1].MediaBox

Reversing the order of pages
~~~~~~~~~~~~~~~~~~~~~~~~~~~~

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

Deleting pages
~~~~~~~~~~~~~~

Removing and adding pages is easy too.

.. ipython::

    In [1]: del pdf.pages[1:3]  # Remove pages 2-3 labeled "second page" and "third page"

.. ipython::

    In [1]: pdf

We’ve trimmed down the file to its essential first and last page.

.. _copyother:

Copying pages from other PDFs
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Now, let’s add some content from another file. Because ``pdf.pages`` behaves
like a list, we can use ``pages.extend()`` on another file's pages.

.. ipython::

    In [1]: pdf = Pdf.open('../tests/resources/fourpages.pdf')

    In [1]: appendix = Pdf.open('../tests/resources/sandwich.pdf')

    In [2]: pdf.pages.extend(appendix.pages)

We can use ``pages.insert()`` to insert into one of more pages into a specific
position, bumping everything else ahead.

.. ipython::

    In [3]: graph = Pdf.open('../tests/resources/graph.pdf')

    In [4]: pdf.pages.insert(1, graph.pages[0])

    In [5]: len(pdf.pages)

We can also replace specific pages with assignment (or slicing).

.. ipython::

    In [1]: congress = Pdf.open('../tests/resources/congress.pdf')

    In [1]: pdf.pages[2] = congress.pages[0]

.. note::

    Some interactive PDF features such as hyperlinks internal to the document
    may stop working when a page is copied from one file to another.


Copying pages within a PDF
~~~~~~~~~~~~~~~~~~~~~~~~~~

When a page is copied (assigned) to a different position within the same PDF,
the copy is constructed as a new page rather than a reference to the existing
one. This is different from standard Python behavior.

For a detailed explanation and workarounds, see :ref:`page-copying`.

Saving changes
~~~~~~~~~~~~~~

Naturally, you can save your changes with :meth:`pikepdf.Pdf.save`.
``filename`` can be a :class:`pathlib.Path`, which we accept everywhere. (Saving
is commented out to avoid upsetting the documentation generator.)

.. ipython::
    :verbatim:

    In [1]: pdf.save('output.pdf')

You may save a file multiple times, and you may continue modifying it after
saving.

Saving with encryption
~~~~~~~~~~~~~~~~~~~~~~

To save an encrypted (password protected) PDF, use a :class:`pikepdf.Encryption`
object to specify the encryption settings. By default, pikepdf selects the strongest
security handler and algorithm, but allows full access to modify file contents.
A :class:`pikepdf.Permissions` object can be used to specify restrictions.

.. ipython::
    :verbatim:

    In [1]: no_extracting = pikepdf.Permissions(extract=False)

    In [1]: pdf.save('output.pdf', encryption=pikepdf.Encryption(
       ...:      user="user password", owner="owner password", allow=no_extracting
       ...: ))

.. _splitpdf:

Split a PDF one page PDFs
~~~~~~~~~~~~~~~~~~~~~~~~~

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

Merging a PDF from several files
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

You might be able to guess.

.. ipython::
    :verbatim:

    In [1]: from glob import glob

    In [1]: pdf = Pdf.new()

    In [1]: for file in glob('*.pdf'):
       ...:     src = Pdf.open(file)
       ...:     pdf.pages.extend(src.pages)

    In [1]: pdf.save('merged.pdf')

.. note::

    This code sample does not deduplicate objects. The resulting file may be
    large if the source files have content in common.

Using counting numbers
~~~~~~~~~~~~~~~~~~~~~~

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

.. note::

    Because of technical limitations in underlying libraries, pikepdf keeps the
    source PDF open when a content is copied from it to another PDF, even when
    all Python variables pointing to the source are removed. If a PDF is being assembled from many sources, then
    all of those sources are held open in memory. This memory can be released
    by saving and re-opening the PDF.

.. warning::

    It's possible to obtain page information through the PDF ``/Root`` object as
    well, but not recommend. The internal consistency of the various ``/Page``
    and ``/Pages`` is not guaranteed when accessed in this manner, and in some
    PDFs the data structure for these is fairly complex. Use the ``.pages``
    interface.
