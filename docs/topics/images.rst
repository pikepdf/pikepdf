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

Playing with images
-------------------

pikepdf provides a helper class :class:`~pikepdf.PdfImage` for manipulating
images in a PDF. The helper class helps manage the complexity of the image
dictionaries.

.. ipython::

    In [1]: from pikepdf import Pdf, PdfImage, Name

    In [1]: example = Pdf.open('../tests/resources/congress.pdf')

    In [1]: page1 = example.pages[0]

    In [1]: list(page1.images.keys())

    In [1]: rawimage = page1.images['/Im0']  # The raw object/dictionary

    In [1]: pdfimage = PdfImage(rawimage)

    In [1]: type(pdfimage)

In Jupyter (or IPython with a suitable backend) the image will be
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

.. ipython::
    :verbatim:

    In [1]: pdfimage.extract_to(fileprefix='image'))
    Out[1]: 'image.jpg'

It also possible to extract to a writable Python stream using
``.extract_to(stream=...`)``.

You can also retrieve the image as a Pillow image (this will transcode):

.. ipython::

    In [1]: type(pdfimage.as_pil_image())

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

.. ipython::

    In [1]: import zlib

    In [1]: rawimage = pdfimage.obj

    In [1]: pillowimage = pdfimage.as_pil_image()

    In [1]: grayscale = pillowimage.convert('L')

    In [1]: grayscale = grayscale.resize((32, 32))

    In [1]: rawimage.write(zlib.compress(grayscale.tobytes()), filter=Name("/FlateDecode"))

    In [1]: rawimage.ColorSpace = Name("/DeviceGray")

    In [1]: rawimage.Width, rawimage.Height = 32, 32

Notes on this example:

* It is generally possible to use ``zlib.compress()`` to
  generate compressed image data, although this is not as efficient as using
  a program that knows it is preparing a PDF.

* In general we can resize an image to any scale. The PDF content stream
  specifies where to draw an image and at what scale.

* This example would replace all occurrences of the image if it were used
  multiple times in a PDF.
