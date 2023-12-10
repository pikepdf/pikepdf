Working with images
===================

PDFs embed images as binary stream objects within the PDF's data stream. The
stream object's dictionary describes properties of the image such as its
dimensions and color space. The same image may be drawn multiple times on
multiple pages, at different scales and positions.

In some cases such as JPEG2000, the standard file format of the image
is used verbatim, even when the file format contains headers and information
that is repeated in the stream dictionary. In other cases such as for
PNG-style encoding, the image file format is not used directly.

pikepdf currently has no facility to embed new images into PDFs. We recommend
img2pdf instead, because it does the job so well. pikepdf instead allows
for image inspection and lossless/transcode free (where possible) "pdf2img".

pikepdf also cannot extract vector images, that is images produced through a
combination of PDF drawing commands. These are produced by a content stream,
or sometimes a Form XObject. Unfortunately there may not be anything in the
PDF that indicates a particular sequence of operations produces an image,
and that sequence is not necessarily all in the same place. To extract a
vector image, use a PDF viewer/editor to crop to that image.

Playing with images
-------------------

pikepdf provides a helper class :class:`~pikepdf.PdfImage` for manipulating
images in a PDF. The helper class helps manage the complexity of the image
dictionaries.

.. doctest::

    >>> from pikepdf import Pdf, PdfImage, Name

    >>> example = Pdf.open('../tests/resources/congress.pdf')

    >>> page1 = example.pages[0]

    >>> list(page1.images.keys())
    ['/Im0']

    >>> rawimage = page1.images['/Im0']  # The raw object/dictionary

    >>> pdfimage = PdfImage(rawimage)

    >>> type(pdfimage)
    <class 'pikepdf.models.image.PdfImage'>

In Jupyter (or IPython with a suitable backend) the image will be
displayed.

|im0|

.. |im0| image:: /images/congress_im0.jpg
  :width: 2in

You can also inspect the properties of the image. The parameters are similar
to Pillow's.

.. doctest::

    >>> pdfimage.colorspace
    '/DeviceRGB'

    >>> pdfimage.width, pdfimage.height
    (1000, 1520)

.. note::

    ``.width`` and ``.height`` are the resolution of the image in pixels, not
    the size of the image in page coordinates. The size of the image in page
    coordinates is determined by the content stream.

.. _extract_image:

Extracting images
-----------------

Extracting images is straightforward. :meth:`~pikepdf.PdfImage.extract_to` will
extract images to a specified file prefix. The extension is determined while
extracting and appended to the filename. Where possible, ``extract_to``
writes compressed data directly to the stream without transcoding. (Transcoding
lossy formats like JPEG can reduce their quality.)

.. code-block:: python

    >>> pdfimage.extract_to(fileprefix='image')
    'image.jpg'

It also possible to extract to a writable Python stream using
``.extract_to(stream=...`)``.

You can also retrieve the image as a Pillow image (this will transcode):

.. doctest::

    >>> type(pdfimage.as_pil_image())
    <class 'PIL.JpegImagePlugin.JpegImageFile'>

Another way to view the image is using Pillow's ``Image.show()`` method.

Not all image types can be extracted. Also, some PDFs describe an image with a
mask, with transparency effects. pikepdf can only extract the images
themselves, not rasterize them exactly as they would appear in a PDF viewer. In
the vast majority of cases, however, the image can be extracted as it appears.

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

In this example we extract an image and replace it with a grayscale
equivalent.

.. doctest::

    >>> import zlib

    >>> rawimage = pdfimage.obj

    >>> pillowimage = pdfimage.as_pil_image()

    >>> grayscale = pillowimage.convert('L')

    >>> grayscale = grayscale.resize((32, 32))

    >>> rawimage.write(zlib.compress(grayscale.tobytes()), filter=Name("/FlateDecode"))

    >>> rawimage.ColorSpace = Name("/DeviceGray")

    >>> rawimage.Width, rawimage.Height = 32, 32

Notes on this example:

* It is generally possible to use ``zlib.compress()`` to
  generate compressed image data, although this is not as efficient as using
  a program that knows it is preparing a PDF.

* In general we can resize an image to any scale. The PDF content stream
  specifies where to draw an image and at what scale.

* This example would replace all occurrences of the image if it were used
  multiple times in a PDF.

Removing an image
-----------------

The easy way to remove an image is to replace it with a 1x1 pixel transparent image.
A transparent image can be created by setting the ``/ImageMask`` to true.

Note that, if an image is referenced on multiple pages, this procedure only updates
the occurrence on one page. If all references to the image are deleted, it should
not be included in the output file.

.. doctest::

  >>> pdf = pikepdf.open('../tests/resources/sandwich.pdf')

  >>> page = pdf.pages[0]

  >>> image_name, image = next(iter(page.images.items()))

  >>> new_image = pdf.make_stream(b'\xff')

  >>> new_image.Width, new_image.Height = 1, 1

  >>> new_image.BitsPerComponent = 1

  >>> new_image.ImageMask = True

  >>> new_image.Decode = [0, 1]

  >>> page.Resources.XObject[image_name] = new_image
