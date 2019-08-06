Working with images
===================

Viewing images
--------------

pikepdf provides a helper class :class:`~pikepdf.PdfImage` for manipulating
PDF images.

.. ipython::

    In [1]: from pikepdf import Pdf, PdfImage

    In [1]: example = Pdf.open('../tests/resources/congress.pdf')

    In [1]: page1 = example.pages[0]

    In [1]: pdfimage = PdfImage(page1.Resources.XObject['/Im0'])

    In [1]: pdfimage
    Out[1]:

In Jupyter (or IPython with a suitable configuration) the image will be
displayed.

|im0|

.. |im0| image:: /images/congress_im0.jpg
  :width: 2in

You can also inspect the properties of the image. The parameters are similar
to Pillow's.

.. ipython::

    In [1]: pdfimage.colorspace

    In [1]: pdfimage.width, pdfimage.height

.. note::

    ``.width`` and ``.height`` are the resolution of the image in pixels, not
    the size of the image in page coordinates.

.. _extract_image:

Extracting images
-----------------

Extracting images is straightforward. :meth:`~pikepdf.PdfImage.extract_to` will
extract images to streams, such as an open file. Where possible, ``extract_to``
writes compressed data directly to the stream without transcoding. The return
value is the file extension that was extracted.

.. ipython::
    :verbatim:

    In [1]: pdfimage.extract_to(stream=open('file.jpg', 'w'))

You can also retrieve the image as a Pillow image:

.. ipython::
    :verbatim:

    In [1]: pdfimage.as_pil_image()

.. note::

    This simple example PDF displays a single full page image. Some PDF creators
    will paint a page using multiple images, and features such as layers,
    transparency and image masks. Accessing the first image on a page is like an
    HTML parser that scans for the first ``<img src="">`` tag it finds. A lot
    more could be happening. There can be multiple images drawn multiple times
    on a page, vector art, overdrawing, masking, and transparency. A set of
    resources can be grouped together in a "Form XObject" (not to be confused
    with a PDF Form), and drawn at all once. Images can be referenced by
    multiple pages.

.. _replace_image:

Replacing an image
------------------

See ``test_image_access.py::test_image_replace``.
