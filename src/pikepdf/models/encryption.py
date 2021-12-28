# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.
#
# Copyright (C) 2017, James R. Barlow (https://github.com/jbarlow83/)

from typing import Any, Dict, NamedTuple, cast

from pikepdf._qpdf import EncryptionMethod


class Permissions(NamedTuple):
    """
    Stores the user-level permissions for an encrypted PDF.

    A compliant PDF reader/writer should enforce these restrictions on people
    who have the user password and not the owner password. In practice, either
    password is sufficient to decrypt all document contents. A person who has
    the owner password should be allowed to modify the document in any way.
    pikepdf does not enforce the restrictions in any way; it is up to application
    developers to enforce them as they see fit.

    Unencrypted PDFs implicitly have all permissions allowed. Permissions can
    only be changed when a PDF is saved.
    """

    accessibility: bool = True
    """Can users use screen readers and accessibility tools to read the PDF?"""

    extract: bool = True
    """Can users extract contents?"""

    modify_annotation: bool = True
    """Can users modify annotations?"""

    modify_assembly: bool = False
    """Can users arrange document contents?"""

    modify_form: bool = True
    """Can users fill out formts?"""

    modify_other: bool = True
    """Can users modify the document?"""

    print_lowres: bool = True
    """Can users print the document at low resolution?"""

    print_highres: bool = True
    """Can users print the document at high resolution?"""


DEFAULT_PERMISSIONS = Permissions()


class EncryptionInfo:
    """
    Reports encryption information for an encrypted PDF.

    This information may not be changed, except when a PDF is saved.
    This object is not used to specify the encryption settings to save
    a PDF, due to non-overlapping information requirements.
    """

    def __init__(self, encdict: Dict[str, Any]):
        self._encdict = encdict

    @property
    def R(self) -> int:
        """Revision number of the security handler."""
        return int(self._encdict['R'])

    @property
    def V(self) -> int:
        """Version of PDF password algorithm."""
        return int(self._encdict['V'])

    @property
    def P(self) -> int:
        """Encoded permission bits.

        See :meth:`Pdf.allow` instead.
        """
        return int(self._encdict['P'])

    @property
    def stream_method(self) -> EncryptionMethod:
        """Encryption method used to encode streams."""
        return cast(EncryptionMethod, self._encdict['stream'])

    @property
    def string_method(self) -> EncryptionMethod:
        """Encryption method used to encode strings."""
        return cast(EncryptionMethod, self._encdict['string'])

    @property
    def file_method(self) -> EncryptionMethod:
        """Encryption method used to encode the whole file."""
        return cast(EncryptionMethod, self._encdict['file'])

    @property
    def user_password(self) -> bytes:
        """If possible, return the user password.

        The user password can only be retrieved when a PDF is opened
        with the owner password and when older versions of the
        encryption algorithm are used.

        The password is always returned as ``bytes`` even if it has
        a clear Unicode representation.
        """
        return bytes(self._encdict['user_passwd'])

    @property
    def encryption_key(self) -> bytes:
        """The RC4 or AES encryption key used for this file."""
        return bytes(self._encdict['encryption_key'])

    @property
    def bits(self) -> int:
        """The number of encryption bits.

        e.g. if the algorithm is AES-256, this returns 256.
        """
        return len(self._encdict['encryption_key']) * 8


class Encryption(dict):
    """
    Specify the encryption settings to apply when a PDF is saved.

    Args:
        owner: The owner password to use. This allows full control
            of the file. If blank, the PDF will be encrypted and
            present as "(SECURED)" in PDF viewers. If the owner password
            is blank, the user password should be as well.
        user: The user password to use. With this password, some
            restrictions will be imposed by a typical PDF reader.
            If blank, the PDF can be opened by anyone, but only modified
            as allowed by the permissions in ``allow``.
        R: Select the security handler algorithm to use. Choose from:
            ``2``, ``3``, ``4`` or ``6``. By default, the highest version of
            is selected (``6``). ``5`` is a deprecated algorithm that should
            not be used.
        allow: The permissions to set.
            If omitted, all permissions are granted to the user.
        aes: If True, request the AES algorithm. If False, use RC4.
            If omitted, AES is selected whenever possible (R >= 4).
        metadata: If True, also encrypt the PDF metadata. If False,
            metadata is not encrypted. Reading document metadata without
            decryption may be desirable in some cases. Requires ``aes=True``.
            If omitted, metadata is encrypted whenever possible.
    """

    def __init__(
        self,
        *,
        owner: str,
        user: str,
        R: int = 6,
        allow: Permissions = DEFAULT_PERMISSIONS,
        aes: bool = True,
        metadata: bool = True,
    ):
        super().__init__()
        self.update(
            dict(R=R, owner=owner, user=user, allow=allow, aes=aes, metadata=metadata)
        )
