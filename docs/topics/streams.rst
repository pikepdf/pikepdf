Stream objects
==============

A :class:`pikepdf.Stream` object works like a PDF dictionary with some encoded
bytes attached. The dictionary is metadata that describes how the stream is
encoded. PDF can, and regularly does, use a variety of encoding filters. A
stream can be encoded with one or more filters. Images are a type of stream
object.

This is not the same type of object as Python's file-like I/O objects, which are
sometimes called streams.

Most of the interesting content in a PDF (images and content streams) are
inside stream objects.

Because the PDF specification unfortunately defines several terms that involve the
word *stream*, let's attempt to clarify:

.. figure:: /images/28fish.jpg
  :figwidth: 30%
  :align: right
  :alt: Image of many species of fish

  When it comes to taxonomy, software developers have it easy.

stream object
  A PDF object that contains binary data and a metadata dictionary that describes
  it, represented as :class:`pikepdf.Stream`, a subclass of :class:`pikepdf.Object`.
  In HTML this is equivalent to a ``<object>`` tag with attributes and data.

object stream
  A stream object (not a typo, an object stream really is a type of stream
  object) in a PDF that contains a number of other objects in a
  PDF, grouped together for better compression. In pikepdf there is an option
  to save PDFs with this feature enabled to improve compression. Otherwise,
  this is just a detail about how PDF files are encoded. When object streams
  are present, pikepdf automatically decompresses them as necessary; no special
  steps are needed to access a PDF that contains object streams.

content stream
  A stream object that contains some instructions to draw graphics
  and text on a page, or inside a Form XObject, and in some other situations.
  In HTML this is equivalent to the HTML file itself. Content streams only draw
  one page (or canvas, for a Form XObject). Each page needs its own content stream
  to draw its contents.

Form XObject
  A group of images, text and drawing commands that can be rendered elsewhere
  in a PDF as a group. This is often used when a group of objects are needed
  at different scales or on multiple pages. In HTML this is like an ``<svg>``.
  It is not a fillable PDF form (although a fillable PDF form could involve
  Form XObjects).

(Python) stream
  A stream is another name for a file object or file-like object, as described
  in the Python :mod:`io` module.

Reading stream objects
----------------------

Fortunately, :meth:`pikepdf.Stream.read_bytes` will apply all filters
and decode the uncompressed bytes, or throw an error if this is not possible.
:meth:`pikepdf.Stream.read_raw_bytes` provides access to the compressed bytes.

Three types of stream object are particularly noteworthy: content streams,
which describe the order of drawing operators; images; and XMP metadata.
pikepdf provides helper functions for working with these types of streams.

Reading stream objects as a Python I/O streams
----------------------------------------------

You were warned about terminology.

To preserve our remaining sanity, you cannot access a
stream object as a file-like object directly.

To efficiently access a ``pikepdf.Stream`` as a Python file object, you may do:

.. code-block:: python

  pdf.pages[0].Contents.page_contents_coalesce()
  filelike_object = BytesIO(pdf.pages[0].Contents.get_stream_buffer())
