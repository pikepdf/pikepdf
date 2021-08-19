.. _attachments:

Attaching files to a PDF
************************

.. versionadded:: 3.0

You can attach (or if you prefer, embed) any file to a PDF, including
other PDFs. As a quick example, let's attach pikepdf's README.md file
to one of its test files.

.. ipython::

    In [1]: from pikepdf import Pdf, AttachedFileSpec

    In [1]: from pathlib import Path

    In [1]: pdf = Pdf.open('../tests/resources/fourpages.pdf')

    In [1]: filespec = AttachedFileSpec.from_filepath(pdf, Path('../README.md'))

    In [1]: pdf.attachments['README.md'] = filespec

    In [1]: pdf.attachments

This creates an attached file named ``README.md``, which holds the data in ``filespec``.
Now we can retrive the data.

.. ipython::

    In [1]: pdf.attachments['README.md']

    In [1]: pdf.attachments['README.md'].get_file()

    In [1]: pdf.attachments['README.md'].get_file().read_bytes()[:50]


General notes on attached files
-------------------------------

* If the main PDF is encrypted, any embedded files will be encrypted with the same
  encryption settings.

* PDF viewers tend to display attachment filenames in alphabetical order. Use prefixes
  if you want to control the display order.

* The ``AttachedFileSpec`` will capture all of the data when created, so the file object
  used to create the data can be closed.

* Each attachment is a :class:`pikepdf.AttachedFileSpec`. An attachment usually contains only
  one :class:`pikepdf.AttachedFile`, but might contain multiple objects of this
  type. Usually, multiple versions are used to provide different versions of the
  same file for alternate platforms, such as Windows and macOS versions of a file.
  Newer PDFs rarely provide multiple versions.