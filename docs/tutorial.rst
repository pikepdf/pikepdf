.. _tutorial:

Tutorial
********

.. figure:: images/pike-cartoon.png
       :figwidth: 30%
       :align: right

This brief tutorial should give you an introduction and orientation to pikepdf's
paradigm and syntax. From there, we refer to you various topics.

Opening and saving PDFs
-----------------------

In contrast to better known PDF libraries, pikepdf uses a single object to
represent a PDF, whether reading, writing or merging. We have cleverly named
this :class:`pikepdf.Pdf`. In this documentation, a ``Pdf`` is a class that
allows manipulate the PDF, meaning the file.

.. code-block:: python

   from pikepdf import Pdf
   new_pdf = Pdf.new()
   with Pdf.open('sample.pdf') as pdf:
       pdf.save('output.pdf')

You may of course use ``from pikepdf import Pdf as ...`` if the short class
name conflicts or ``from pikepdf import Pdf as PDF`` if you prefer uppercase.

:func:`pikepdf.open` is a shorthand for :meth:`pikepdf.Pdf.open`.

The PDF class API follows the example of the widely-used
`Pillow image library <https://pillow.readthedocs.io/en/latest/>`_. For clarity
there is no default constructor since the arguments used for creation and
opening are different. ``Pdf.open()`` also accepts seekable streams as input,
and ``Pdf.save()`` accepts streams as output.

Inspecting pages
----------------

Working with pages is fundamental to PDFs. pikepdf presents the pages in a PDF
through the :attr:`pikepdf.Pdf.pages` property, which follows the ``list``
protocol. As such page numbers begin at 0.

Let’s open a simple PDF that contains four pages.

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

    In [1]: pdf.pages[0]
    Out[1]: « In Jupyter you would see an image of the PDF page here »

You can also examine individual pages, which we’ll explore in the next
section. Suffice to say that you can access pages by indexing them and
slicing them.

.. ipython::
    :verbatim:

    In [1]: pdf.pages[0]
    Out[1]: « In Jupyter you would see an image of the PDF page here »

.. ipython::

    In [1]: pdf.pages[-1].MediaBox

.. note::

    :meth:`pikepdf.Pdf.open` can open almost all types of encrypted PDF! Just
    provide the ``password=`` keyword argument.

Deleting pages
--------------

Removing pages is easy too.

.. ipython::

    In [1]: del pdf.pages[1:3]  # Remove pages 2-3 labeled "second page" and "third page"

.. ipython::

    In [1]: len(pdf.pages)

Saving changes
--------------

Naturally, you can save your changes with :meth:`pikepdf.Pdf.save`.
``filename`` can be a :class:`pathlib.Path`, which we accept everywhere. (Saving
is commented out to avoid upsetting the documentation generator.)

.. ipython::
    :verbatim:

    In [1]: pdf.save('output.pdf')

You may save a file multiple times, and you may continue modifying it after
saving.

Next steps
----------

Have a look at pikepdf topics that interest you, or jump to our detailed API
reference...
