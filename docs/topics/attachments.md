(attachments)=

# Attaching files to a PDF

:::{versionadded} 3.0
:::

You can attach (or if you prefer, embed) any file to a PDF, including
other PDFs. As a quick example, let's attach pikepdf's README.md file
to one of its test files.

```{eval-rst}
.. doctest::

    >>> from pikepdf import Pdf, AttachedFileSpec, Name, Dictionary, Array

    >>> from pathlib import Path

    >>> pdf = Pdf.open('../tests/resources/fourpages.pdf')

    >>> filespec = AttachedFileSpec.from_filepath(pdf, Path('../README.md'))

    >>> pdf.attachments['README.md'] = filespec

    >>> pdf.attachments
    <pikepdf._core.Attachments: ['README.md']>
```

This creates an attached file named `README.md`, which holds the data in `filespec`.
Now we can retrieve the data.

```{eval-rst}
.. doctest::

    >>> pdf.attachments['README.md']
    <pikepdf._core.AttachedFileSpec for 'README.md', description ''>

    >>> file = pdf.attachments['README.md'].get_file()
```

```python
>>> file.read_bytes()[...]
b'**pikepdf** is a Python library for reading and writing PDF files.'
```

If the data used to create an attachment is in memory:

```{eval-rst}
.. doctest::

    >>> memfilespec = AttachedFileSpec(pdf, b'Some text', mime_type='text/plain')

    >>> pdf.attachments['plain.txt'] = memfilespec

```

## General notes on attached files

- If the main PDF is encrypted, any embedded files will be encrypted with the same
  encryption settings.
- PDF viewers tend to display attachment filenames in alphabetical order. Use prefixes
  if you want to control the display order.
- The `AttachedFileSpec` will capture all of the data when created, so the file object
  used to create the data can be closed.
- Each attachment is a {class}`pikepdf.AttachedFileSpec`. An attachment usually contains only
  one {class}`pikepdf.AttachedFile`, but might contain multiple objects of this
  type. Usually, multiple versions are used to provide different versions of the
  same file for alternate platforms, such as Windows and macOS versions of a file.
  Newer PDFs rarely provide multiple versions.

## How to find attachments in a PDF viewer

Your PDF viewer should have an attachments panel that shows available attachments.

:::{figure} /images/acrobat-attachments.png
:alt: Screenshot of attachments panel in Acrobat DC on Windows

Attachments in Adobe Acrobat DC.
:::

Attachments added to `Pdf.attachments` will be shown here.

You may find it useful to set `pdf.root.PageMode = Name.UseAttachments`. This
tells the PDF viewer to open a pane that lists all attachments in the PDF. Note
that it is up to the PDF viewer to implement and honor this request.

## Creating attachment annotations

You can also create PDF Annotations and Actions that contain attached files.

Here is an example of an annotation that displays an icon. Clicking the icon
prompt the user to view the attached document.

```{eval-rst}
.. doctest::

  >>> pdf = Pdf.open('../tests/resources/fourpages.pdf')

  >>> filespec = AttachedFileSpec.from_filepath(pdf, Path('../README.md'))

  >>> pushpin = Dictionary(
  ...     Type=Name.Annot,
  ...     Subtype=Name.FileAttachment,
  ...     Name=Name.GraphPushPin,
  ...     FS=filespec.obj,
  ...     Rect=[2*72, 9*72, 3*72, 10*72],
  ... )

  >>> pdf.pages[0].Annots = pdf.make_indirect(Array([
  ...     pushpin
  ... ]))
```

Files that are referenced as Annotations and Actions do not need to be added
to `Pdf.attachments`. If they are, the file will be attached twice.
