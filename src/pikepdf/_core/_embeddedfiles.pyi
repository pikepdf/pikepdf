# SPDX-FileCopyrightText: 2022 James R. Barlow
# SPDX-License-Identifier: MPL-2.0

# Type stubs for the bindings in src/core/embeddedfiles.cpp.
# See pikepdf/_core/__init__.pyi for how this stub package is laid out.

# pylint: disable=no-method-argument,unused-argument,no-self-use,too-many-public-methods
# ruff: noqa: D418
# mypy: disable-error-code="misc"

from __future__ import annotations

import datetime
from collections.abc import Iterator, MutableMapping
from pathlib import Path
from typing import Any

from pikepdf._core._object import Object, ObjectHelper
from pikepdf._core._object_construct import Dictionary, Name
from pikepdf._core._qpdf import Pdf

class AttachedFile:
    """An object that contains an actual attached file.

    These objects do not need to be created manually; they are normally part of an
    AttachedFileSpec.

    .. versionadded:: 3.0
    """

    _creation_date: str
    _mod_date: str
    creation_date: datetime.datetime | None
    mime_type: str
    """Get the MIME type of the attached file according to the PDF creator."""
    mod_date: datetime.datetime | None
    @property
    def md5(self) -> bytes:
        """Get the MD5 checksum of attached file according to the PDF creator."""
    @property
    def obj(self) -> Object: ...
    def read_bytes(self) -> bytes:
        """Read the attached file's decoded contents."""
    @property
    def size(self) -> int:
        """Get length of the attached file in bytes according to the PDF creator."""

class AttachedFileSpec(ObjectHelper):
    r"""In a PDF, a file specification provides name and metadata for a target file.

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

    Described in the {{ pdfrm }} section 7.11.3.

    .. versionadded:: 3.0
    """

    def __init__(
        self,
        pdf: Pdf,
        data: bytes,
        *,
        description: str,
        filename: str,
        mime_type: str,
        creation_date: str,
        mod_date: str,
    ) -> None:
        """Construct a attached file spec from data in memory.

        To construct a file spec from a file on the computer's file system,
        use :meth:`from_filepath`.

        Args:
            pdf: The Pdf to attach this file specification to.
            data: Resource to load.
            description: Any description text for the attachment. May be
                shown in PDF viewers.
            filename: Filename to display in PDF viewers.
            mime_type: Helps PDF viewers decide how to display the information.
            creation_date: PDF date string for when this file was created.
            mod_date: PDF date string for when this file was last modified.
            relationship: A :class:`pikepdf.Name` indicating the relationship
                of this file to the document. Canonically, this should be a name
                from the PDF specification:
                Source, Data, Alternative, Supplement, EncryptedPayload, FormData,
                Schema, Unspecified. If omitted, Unspecified is used.
        """
    # Inherited from ObjectHelper, restated so that sphinx-autoapi documents it:
    # its :inherited-members: support does not follow a base class into a
    # sibling stub module.
    @property
    def obj(self) -> Dictionary:
        """Get the underlying PDF object (typically a Dictionary)."""

    def get_all_filenames(self) -> dict:
        """Return a Python dictionary that describes all filenames.

        The returned dictionary is not a pikepdf Object.

        Multiple filenames are generally a holdover from the pre-Unicode era.
        Modern PDFs can generally set UTF-8 filenames and avoid using
        punctuation or other marks that are forbidden in filenames.
        """
    def get_file(self, name: Name = ...) -> AttachedFile:
        """Return an attached file.

        Typically, only one file is attached to an attached file spec.
        When multiple files are attached, use the ``name`` parameter to
        specify which one to return.

        Args:
            name: Typical names would be ``/UF`` and ``/F``. See {{ pdfrm }}
                for other obsolete names.
        """
    @staticmethod
    def from_filepath(
        pdf: Pdf, path: Path | str, *, description: str = ''
    ) -> AttachedFileSpec:
        """Construct a file specification from a file path.

        This function will automatically add a creation and modified date
        using the file system, and a MIME type inferred from the file's extension.

        If the data required for the attach is in memory, use
        :meth:`pikepdf.AttachedFileSpec` instead.

        Args:
            pdf: The Pdf to attach this file specification to.
            path: A file path for the file to attach to this Pdf.
            description: An optional description. May be shown to the user in
                PDF viewers.
            relationship: An optional relationship type. May be used to
                indicate the type of attachment, e.g. Name.Source or Name.Data.
                Canonically, this should be a name from the PDF specification:
                Source, Data, Alternative, Supplement, EncryptedPayload, FormData,
                Schema, Unspecified. If omitted, Unspecified is used.
        """
    @property
    def description(self) -> str:
        """Description text associated with the embedded file."""
    @property
    def filename(self) -> str:
        """The main filename for this file spec.

        In priority order, getting this returns the first of /UF, /F, /Unix,
        /DOS, /Mac if multiple filenames are set. Setting this will set a UTF-8
        encoded Unicode filename and write it to /UF.
        """
    @property
    def relationship(self) -> Name | None:
        """The file's relationship to the document, as a :class:`pikepdf.Name`.

        Returns ``None`` if the file specification has no ``/AFRelationship``.
        Assigning ``None`` removes it.
        """
    @relationship.setter
    def relationship(self, value: Name | None) -> None: ...

class Attachments(MutableMapping[str, AttachedFileSpec]):
    """Exposes files attached to a PDF.

    If a file is attached to a PDF, it is exposed through this interface.
    For example ``p.attachments['readme.txt']`` would return a
    :class:`pikepdf._core.AttachedFileSpec` that describes the attached file,
    if a file were attached under that name.
    ``p.attachments['readme.txt'].get_file()`` would return a
    :class:`pikepdf._core.AttachedFile`, an archaic intermediate object to support
    different versions of the file for different platforms. Typically one
    just calls ``p.attachments['readme.txt'].read_bytes()`` to get the
    contents of the file.

    This interface provides access to any files that are attached to this PDF,
    exposed as a Python :class:`collections.abc.MutableMapping` interface.

    The keys (virtual filenames) are always ``str``, and values are always
    :class:`pikepdf.AttachedFileSpec`.

    To create a new attached file, use
    :meth:`pikepdf._core.AttachedFileSpec.from_filepath`
    to create a :class:`pikepdf._core.AttachedFileSpec` and then assign it to the
    :attr:`pikepdf.Pdf.attachments` mapping. If the file is in memory, use
    ``p.attachments['test.pdf'] = b'binary data'``.

    Use this interface through :attr:`pikepdf.Pdf.attachments`.

    .. versionadded:: 3.0

    .. versionchanged:: 8.10.1
        Added convenience interface for directly loading attached files, e.g.
        ``pdf.attachments['/test.pdf'] = b'binary data'``. Prior to this release,
        there was no way to attach data in memory as a file.
    """

    def __contains__(self, k: object, /) -> bool: ...
    def __delitem__(self, k: str, /) -> None: ...
    def __eq__(self, other: Any, /) -> bool: ...
    def __getitem__(self, k: str, /) -> AttachedFileSpec: ...
    def __iter__(self) -> Iterator[str]: ...
    def __len__(self) -> int: ...
    def __setitem__(self, k: str, v: AttachedFileSpec | bytes, /) -> None: ...
    def __init__(self, *args, **kwargs) -> None: ...
    @property
    def _has_embedded_files(self) -> bool: ...
