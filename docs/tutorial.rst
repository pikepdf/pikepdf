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

Manipulating pages is fundamental to PDFs. pikepdf presents the pages in a PDF
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

.. note::

    :meth:`pikepdf.Pdf.open` can open almost all types of encrypted PDF! Just
    provide the ``password=`` keyword argument.

For more details on document assembly, see
:ref:`PDF split, merge and document assembly <docassembly>`.

Pages are dictionaries
----------------------

In PDFs, the main data structure is the **dictionary**, a key-value data
structure much like a Python ``dict`` or ``attrdict``. The major difference is
that the keys can only be **names**, and can only be PDF types, including
other dictionaries.

PDF dictionaries are represented as :class:`pikepdf.Dictionary`, and names
are of type :class:`pikepdf.Name`. A page is just a dictionary with a few
required files and a reference from the document's "page tree". (pikepdf manages
the page tree for you.)

.. ipython::

    In [1]: from pikepdf import Pdf

    In [1]: example = Pdf.open('../tests/resources/congress.pdf')

    In [1]: page1 = example.pages[0]

repr() output
-------------

Let's example the page's ``repr()`` output:

.. ipython::

    In [1]: page1

The angle brackets in the output indicate that this object cannot be constructed
with a Python expression because it contains a reference. When angle brackets
are omitted from the ``repr()`` of a pikepdf object, then the object can be
replicated with a Python expression, such as ``eval(repr(x)) == x``. Pages
typically concern indirect references to themselves and other pages, so they
cannot be represented as an expression.

In Jupyter and IPython, pikepdf will instead attempt to display a preview of the PDF
page, assuming a PDF rendering backend is available.

Item and attribute notation
---------------------------

Dictionary keys may be looked up using attributes (``page1.MediaBox``) or
keys (``page1['/MediaBox']``).

.. ipython::

    In [1]: page1.MediaBox      # preferred notation for required names

    In [1]: page1['/MediaBox']  # also works

By convention, pikepdf uses attribute notation for standard names, and item
notation for names that are set by PDF developers. For example, the images
belong to a page always appear at ``page.Resources.XObject`` but the name
of images is set by the PDF creator:

.. ipython::
    :verbatim:

    In [1]: page1.Resources.XObject['/Im0']

Item notation here would be quite cumbersome:
``['/Resources']['/XObject]['/Im0']`` (not recommended).

Attribute notation is convenient, but not robust if elements are missing. For
elements that are not always present, you can use ``.get()``, which behaves like
``dict.get()`` in core Python.  A library such as `glom
<https://github.com/mahmoud/glom>`_ might help when working with complex
structured data that is not always present.

(For now, we'll set aside what a page's ``MediaBox`` and ``Resources.XObject``
are for. See :ref:`Working with pages <work_with_pages>` for details.)

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

To save an encrypted (password protected) PDF, use a :class:`pikepdf.Encryption`
object to specify the encryption settings. By default, pikepdf selects the strongest
security handler and algorithm (AES-256), but allows full access to modify file contents.
A :class:`pikepdf.Permissions` object can be used to specify restrictions.

.. ipython::
    :verbatim:

    In [1]: no_extracting = pikepdf.Permissions(extract=False)

    In [1]: pdf.save('encrypted.pdf', encryption=pikepdf.Encryption(
       ...:      user="user password", owner="owner password", allow=no_extracting
       ...: ))

Next steps
----------

Have a look at pikepdf topics that interest you, or jump to our detailed API
reference...
