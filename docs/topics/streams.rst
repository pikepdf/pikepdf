Stream objects
==============

A :class:`pikepdf.Stream` object works like a PDF dictionary with some encoded
bytes attached. The dictionary is metadata that describes how the stream is
encoded. PDF can, and regularly does, use a variety of encoding filters. A
stream can be encoded with one or more filters. Images are a type of stream
object.

Most of the interesting content in a PDF (images and content streams) are
inside stream objects.

Because the PDF specification unfortunately defines several terms involve the
word stream, let's attempt to clarify:

.. figure:: /images/28fish.jpg
  :figwidth: 30%
  :align: right
  :alt: Image of many species of fish

  When it comes to taxonomy, software developers have it easy.

stream object
  A PDF object that contains binary data and a metadata dictionary to describes
  it, represented as :class:`pikepdf.Stream`. In HTML this is equivalent to
  a ``<object>`` tag with attributes and data.

object stream
  A stream object (not a typo, an object stream really is a type of stream
  object) in a PDF that contains a number of other objects in a
  PDF, grouped together for better compression. In pikepdf there is an option
  to save PDFs with this feature enabled to improve compression. Otherwise,
  this is just a detail about how PDF files are encoded.

content stream
  A stream object that contains some instructions to draw graphics
  and text on a page, or inside a Form XObject. In HTML this is equivalent to
  the HTML file itself. Content streams do not cross pages.

Form XObject
  A group of images, text and drawing commands that can be rendered elsewhere
  in a PDF as a group. This is often used when a group of objects are needed
  at different scales or multiple pages. In HTML this is like an ``<svg>``.
  It is not a fillable PDF form (although a fillable PDF form could involve
  Form XObjects).

Reading stream objects
----------------------

Fortunately, :meth:`pikepdf.Stream.read_bytes` will apply all filters
and decode the uncompressed bytes, or throw an error if this is not possible.
:meth:`pikepdf.Stream.read_raw_bytes` provides access to the compressed bytes.

Three types of stream object are particularly noteworthy: content streams,
which describe the order of drawing operators; images; and XMP metadata.
pikepdf provides helper functions for working with these types of streams.
