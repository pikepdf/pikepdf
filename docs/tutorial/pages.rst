Manipulating pages
------------------

pikepdf presents the pages in a PDF through the ``Pdf.pages`` property,
which follows the ``list`` protocol. As such page numbers begin at 0.

Let’s look at a simple PDF that contains four pages.

.. ipython::

    In [1]: from pikepdf import Pdf

    In [2]: pdf = Pdf.open('../tests/resources/fourpages.pdf')

How many pages?

.. ipython::

    In [2]: len(pdf.pages)

Thanks to IPython’s rich Python object representations you can view the PDF
while you work on it if you execute this example in a Jupyter notebook. Click
the *View PDF* link below to view the file. **You can view the PDF after each
change you make.** If you’re reading this documentation online or as part of
distribution, you won’t see the rich representation.

.. ipython::
    :verbatim:

    In [1]: pdf
    Out[1]: View PDF

You can also examine individual pages, which we’ll explore in the next
section. Suffice to say that you can access pages by indexing them and
slicing them.

.. ipython::

    In [1]: pdf.pages[-1].MediaBox

Suppose the file was scanned backwards. We can easily reverse it in
place - maybe it was scanned backwards, a common problem with automatic
document scanners.

.. ipython::

    In [1]: pdf.pages.reverse()

.. ipython::

    In [1]: pdf

Pretty nice, isn’t it? Of course, the pages in this file are in correct
order, so let’s put them back.

.. ipython::

    In [1]: pdf.pages.reverse()

Removing and adding pages is easy too.

.. ipython::

    In [1]: del pdf.pages[1:3]  # Remove pages 2-3 labeled "second page" and "third page"

.. ipython::

    In [1]: pdf

We’ve trimmed down the file to its essential first and last page. Now,
let’s add some content from another file.

.. ipython::

    In [1]: appendix = Pdf.open('../tests/resources/sandwich.pdf')

    In [2]: pdf.pages.extend(appendix.pages)

    In [3]: graph = Pdf.open('../tests/resources/graph.pdf')

    In [4]: pdf.pages.insert(1, graph.pages[0])

    In [5]: len(pdf.pages)

Naturally, you can save your changes with ``.save(filename_or_stream)``.
``filename`` can be a :class:`pathlib.Path`, which we accept everywhere. (Saving
is commented out to avoid upsetting the documentation generator.)

.. ipython::
    :verbatim:

    In [1]: pdf.save('output.pdf')

Using counting numbers
~~~~~~~~~~~~~~~~~~~~~~

Because PDF pages are usually numbered in counting numbers (1, 2, 3…),
pikepdf provides a convenience accessor ``.p()`` that uses counting
numbers:

.. ipython::
    :verbatim:

    In [1]: pdf.pages.p(1)        # The first page in the document

    In [1]: pdf.pages[0]          # Also the first page in the document

    In [1]: del pdf.pages.p(1)    # This would delete the first page

To avoid confusion, the ``.p()`` accessor does not accept Python slices,
and ``.p(0)`` raises an exception.

PDFs may define their own numbering scheme or different numberings for
different sections. ``.pages`` does not look up this information.

.. note::

    Because of technical limitations in underlying libraries, pikepdf keeps the
    original PDF from which a page from open, even if the reference to the PDF
    is garbage collected.

.. warning::

    It's possible to obtain page information through the PDF ``/Root`` object as
    well, but not recommend. The internal consistency of the various ``/Page``
    and ``/Pages`` is not guaranteed when accessed in this manner, and in some
    PDFs the data structure for these is fairly complex. Use the ``.pages``
    interface.
