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
opening are different. To make a new empty PDF, use ``Pdf.new()`` not ``Pdf()``.

``Pdf.open()`` also accepts seekable streams as input, and ``Pdf.save()`` accepts
streams as output. :class:`pathlib.Path` objects are fully supported anywhere
pikepdf accepts a filename.

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
notebook. This makes easier it to test visual changes.

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
that the keys can only be **names**, and the values can only be PDF types, including
other dictionaries.

PDF dictionaries are represented as :class:`pikepdf.Dictionary`, and names
are of type :class:`pikepdf.Name`. A page is just a dictionary with a certain
required keys and a reference from the document's "page tree". (pikepdf manages
the page tree for you.)

.. ipython::

    In [1]: from pikepdf import Pdf

    In [1]: example = Pdf.open('../tests/resources/congress.pdf')

    In [1]: page1 = example.pages[0]

repr() output
-------------

Let's example the page's ``repr()`` output:

.. ipython::

    In [1]: repr(page1)

The angle brackets in the output indicate that this object cannot be constructed
with a Python expression because it contains a reference. When angle brackets
are omitted from the ``repr()`` of a pikepdf object, then the object can be
replicated with a Python expression, such as ``eval(repr(x)) == x``. Pages
typically have indirect references to themselves and other pages, so they
cannot be represented as an expression.

Item and attribute notation
---------------------------

Dictionary keys may be looked up using attributes (``page1.MediaBox``) or
keys (``page1['/MediaBox']``).

.. ipython::

    In [1]: page1.MediaBox      # preferred notation for standard PDF names

    In [1]: page1['/MediaBox']  # also works

By convention, pikepdf uses attribute notation for standard names (the names
that are normally part of a dictionary, according to the PDF Reference Manual),
and item notation for names that may not always appear. For example, the images
belong to a page always appear at ``page.Resources.XObject`` but the name
of images is arbitrarily chosen by whatever software generates the PDF (``/Im0``,
in this case). (Whenever expressed as strings, names begin with ``/``.)

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

.. figure:: /images/save-pike.jpg
   :align: right
   :alt: Sign that reads "Help the pike survive"
   :figwidth: 40%

   Saving pike.

Naturally, you can save your changes with :meth:`pikepdf.Pdf.save`.
``filename`` can be a :class:`pathlib.Path`, which we accept everywhere.

.. ipython::
    :verbatim:

    In [1]: pdf.save('output.pdf')

You may save a file multiple times, and you may continue modifying it after
saving. For example, you could create an unencrypted version of document, then
apply a watermark, and create an encrypted version.

.. note::

    You may not overwrite the input file (or whatever Python object provides the
    data) when saving or at any other time. pikepdf assumes it will have
    exclusive access to the input file or input data you give it to, until
    ``pdf.close()`` is called.

Saving secure PDFs
^^^^^^^^^^^^^^^^^^

To save an encrypted (password protected) PDF, use a :class:`pikepdf.Encryption`
object to specify the encryption settings. By default, pikepdf selects the
strongest security handler and algorithm (AES-256), but allows full access to
modify file contents. A :class:`pikepdf.Permissions` object can be used to
specify restrictions.

.. ipython::
    :verbatim:

    In [1]: no_extracting = pikepdf.Permissions(extract=False)

    In [1]: pdf.save('encrypted.pdf', encryption=pikepdf.Encryption(
       ...:      user="user password", owner="owner password", allow=no_extracting
       ...: ))

As in all PDFs, if a user password is set, it will not be possible to
open the PDF without the password. If the owner password is set, changes will
not be permitted with the owner password. If the user password is an empty
string and an owner password is set, the PDF can be viewed by anyone with the
user (or owner) password. PDF viewers only enforce ``pikepdf.Permissions``
restrictions when a PDF is opened with the user password, since the owner may
change anything.

pikepdf does not and cannot enforce the restrictions in ``pikepdf.Permissions``
if you open a file with the user password. Someone with either the user or
owner password can access all the contents of PDF. If you are developing an
application, however, you should consider enforcing the restrictions.

For widest compatibility, passwords should be ASCII, since the PDF reference
manual is unclear about how non-ASCII passwords are supposed to be encoded.
See the documentation on ``Pdf.save()`` for more details.

Next steps
----------

Have a look at pikepdf topics that interest you, or jump to our detailed API
reference...
