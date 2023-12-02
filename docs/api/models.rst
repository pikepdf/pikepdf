Support models
**************

Support models are abstracts over "raw" objects within a Pdf. For example, a page
in a PDF is a Dictionary with set to ``/Type`` of ``/Page``. The Dictionary in
that case is the "raw" object. Upon establishing what type of object it is, we
can wrap it with a support model that adds features to ensure consistency with
the PDF specification.

In version 2.x, did not apply support models to "raw" objects automatically.
Version 3.x automatically applies support models to ``/Page`` objects.

.. autoclass:: pikepdf.ObjectHelper
    :members:

.. autoclass:: pikepdf.Page
    :members:
    :inherited-members:

    Support model wrapper around a page dictionary object.

.. autoclass:: pikepdf.PdfMatrix
    :members:
    :special-members: __init__, __matmul__, __array__

.. autoclass:: pikepdf.PdfImage
    :inherited-members:

.. autoclass:: pikepdf.PdfInlineImage

.. autoclass:: pikepdf.models.PdfMetadata
    :members:

.. autoclass:: pikepdf.models.Encryption
    :members:

.. autoclass:: pikepdf.models.Outline
    :members:

.. autoclass:: pikepdf.models.OutlineItem
    :members:

.. autoclass:: pikepdf.Permissions
    :members:

.. class:: pikepdf.models.EncryptionMethod

    Describes which encryption method was used on a particular part of a
    PDF. These values are returned by :class:`pikepdf.EncryptionInfo` but
    are not currently used to specify how encryption is requested.

    .. attribute:: none

        Data was not encrypted.

    .. attribute:: unknown

        An unknown algorithm was used.

    .. attribute:: rc4

        The RC4 encryption algorithm was used (obsolete).

    .. attribute:: aes

        The AES-based algorithm was used as described in the |pdfrm|.

    .. attribute:: aesv3

        An improved version of the AES-based algorithm was used as described in the
        :doc:`Adobe Supplement to the ISO 32000 </references/resources>`, requiring
        PDF 1.7 extension level 3. This algorithm still uses AES, but allows both
        AES-128 and AES-256, and improves how the key is derived from the password.

.. autoclass:: pikepdf.models.EncryptionInfo
    :members:

.. autoclass:: pikepdf.Annotation
    :members:

    Describes an annotation in a PDF, such as a comment, underline, copy editing marks,
    interactive widgets, redactions, 3D objects, sound and video clips.

    See the |pdfrm| section 12.5.6 for the full list of annotation types
    and definition of terminology.

    .. versionadded:: 2.12

.. autoclass:: pikepdf._core.Attachments
    :members:

    This interface provides access to any files that are attached to this PDF,
    exposed as a Python :class:`collections.abc.MutableMapping` interface.

    The keys (virtual filenames) are always ``str``, and values are always
    :class:`pikepdf.AttachedFileSpec`.

    Use this interface through :attr:`pikepdf.Pdf.attachments`.

    .. versionadded:: 3.0

.. autoclass:: pikepdf.AttachedFileSpec
    :members:
    :inherited-members:
    :special-members: __init__

    In a PDF, a file specification provides name and metadata for a target file.

    Most file specifications are *simple* file specifications, and contain only
    one attached file. Call :meth:`get_file` to get the attached file:

    .. code-block:: python

        pdf = Pdf.open(...)

        fs = pdf.attachments['example.txt']
        stream = fs.get_file()

    To attach a new file to a PDF, you may construct a ``AttachedFileSpec``.

    .. code-block:: python

        pdf = Pdf.open(...)

        fs = AttachedFileSpec.from_filepath(pdf, Path('somewhere/spreadsheet.xlsx'))

        pdf.attachments['spreadsheet.xlsx'] = fs

    PDF supports the concept of having multiple, platform-specialized versions of the
    attached file (similar to resource forks on some operating systems). In theory,
    this attachment ought to be the same file, but
    encoded in different ways. For example, perhaps a PDF includes a text file encoded
    with Windows line endings (``\r\n``) and a different one with POSIX line endings
    (``\n``). Similarly, PDF allows for the possibility that you need to encode
    platform-specific filenames. pikepdf cannot directly create these, because they
    are arguably obsolete; it can provide access to them, however.

    If you have to deal with platform-specialized versions,
    use :meth:`get_all_filenames` to enumerate those available.

    Described in the |pdfrm| section 7.11.3.

    .. versionadded:: 3.0

.. autoclass:: pikepdf._core.AttachedFile
    :members:
    :inherited-members:

    An object that contains an actual attached file. These objects do not need
    to be created manually; they are normally part of an AttachedFileSpec.

    .. versionadded:: 3.0

.. autoclass:: pikepdf.NameTree
    :members:

    An object for managing *name tree* data structures in PDFs.

    A name tree is a key-value data structure. The keys are any binary strings
    (that is, Python ``bytes``). If ``str`` selected is provided as a key,
    the UTF-8 encoding of that string is tested. Name trees are (confusingly)
    not indexed by ``pikepdf.Name`` objects. They behave like
    ``DictMapping[bytes, pikepdf.Object]``.

    The keys are sorted; pikepdf will ensure that the order is preserved.

    The value may be any PDF object. Typically it will be a dictionary or array.

    Internally in the PDF, a name tree can be a fairly complex tree data structure
    implemented with many dictionaries and arrays. pikepdf (using libqpdf)
    will automatically read, repair and maintain this tree for you. There should not
    be any reason to access the internal nodes of a number tree; use this
    interface instead.

    NameTrees are used to store certain objects like file attachments in a PDF.
    Where a more specific interface exists, use that instead, and it will
    manipulate the name tree in a semantic correct manner for you.

    Do not modify the internal structure of a name tree while you have a
    ``NameTree`` referencing it. Access it only through the ``NameTree`` object.

    Names trees are described in the |pdfrm| section 7.9.6. See section 7.7.4
    for a list of PDF objects that are stored in name trees.

    .. versionadded:: 3.0

.. autoclass:: pikepdf.NumberTree
    :members:

    An object for managing *number tree* data structures in PDFs.

    A number tree is a key-value data structure, like name trees, except that the
    key is an integer. It behaves like ``Dict[int, pikepdf.Object]``.

    The keys can be sparse - not all integers positions will be populated. Keys
    are also always sorted; pikepdf will ensure that the order is preserved.

    The value may be any PDF object. Typically it will be a dictionary or array.

    Internally in the PDF, a number tree can be a fairly complex tree data structure
    implemented with many dictionaries and arrays. pikepdf (using libqpdf)
    will automatically read, repair and maintain this tree for you. There should not
    be any reason to access the internal nodes of a number tree; use this
    interface instead.

    NumberTrees are not used much in PDF. The main thing they provide is a mapping
    between 0-based page numbers and user-facing page numbers (which pikepdf
    also exposes as ``Page.label``). The ``/PageLabels`` number tree is where the
    page numbering rules are defined.

    Number trees are described in the |pdfrm| section 7.9.7. See section 12.4.2
    for a description of the page labels number tree. Here is an example of modifying
    an existing page labels number tree:

    .. code-block:: python

        pagelabels = NumberTree(pdf.Root.PageLabels)
        # Label pages starting at 0 with lowercase Roman numerals
        pagelabels[0] = Dictionary(S=Name.r)
        # Label pages starting at 6 with decimal numbers
        pagelabels[6] = Dictionary(S=Name.D)

        # Page labels will now be:
        # i, ii, iii, iv, v, 1, 2, 3, ...

    Do not modify the internal structure of a name tree while you have a
    ``NumberTree`` referencing it. Access it only through the ``NumberTree`` object.

    .. versionadded:: 5.4

.. automodule:: pikepdf.canvas