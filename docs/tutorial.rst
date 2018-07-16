Tutorial
********

**Opening and saving**

In contrast to better known PDF libraries, pikepdf uses a single object to
represent a PDF, whether reading, writing or merging. We have cleverly named
this :class:`pikepdf.Pdf`.

.. code-block:: python

   from pikepdf import Pdf
   new_pdf = Pdf.new()
   sample_pdf = Pdf.open('sample.pdf')
   sample_pdf.save('sample2.pdf')

You may of course use ``from pikepdf import Pdf as ...`` if the short class
name conflicts or ``from pikepdf import Pdf as PDF`` if you prefer uppercase.

:func:`pikepdf.open` is a shorthand for ``Pdf.open``.

The PDF class API follows the example of the widely-used
`Pillow image library <https://pillow.readthedocs.io/en/latest/>`_. For clarity
there is no default constructor since the arguments used for creation and
opening are different. ``Pdf.open()`` also accepts seekable streams as input,
and ``Pdf.save()`` accepts streams as output.

**Topics**

This tutorial begins on the assumption that working with pages - splitting
and merging, saving and loading, is the most basic thing users want to do.
(The ``qpdf`` commandline tool, on which pikepdf is based, also does an
excellent job of file level PDF handling.) What pikepdf does is make qpdf's
powerful API more accessible.

.. toctree::
  :maxdepth: 1

  tutorial/pages
  tutorial/page
  tutorial/streams
  tutorial/metadata
