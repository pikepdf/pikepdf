# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.
#
# Copyright (C) 2017, James R. Barlow (https://github.com/jbarlow83/)

import types


class Permissions(types.SimpleNamespace):
    """
    Stores the permissions for an encrypted PDF.

    Unencrypted PDFs implicitly have all permissions allowed.
    pikepdf does not enforce the restrictions in any way. Permissions
    can only be changed when a PDF is saved.
    """

    def __init__(
        self,
        accessibility=True,  # pylint: disable=unused-argument
        extract=True,  # pylint: disable=unused-argument
        modify_annotation=True,  # pylint: disable=unused-argument
        modify_assembly=False,  # pylint: disable=unused-argument
        modify_form=True,  # pylint: disable=unused-argument
        modify_other=True,  # pylint: disable=unused-argument
        print_lowres=True,  # pylint: disable=unused-argument
        print_highres=True,  # pylint: disable=unused-argument
    ):
        kwargs = {
            k: v for k, v in locals().items() if k != 'self' and not k.startswith('_')
        }
        super().__init__(**kwargs)

    def _readonly(self, *args):
        raise TypeError("object is read-only")

    __setattr__ = _readonly

    __delattr__ = _readonly

    def keys(self):
        yield from (k for k in self.__dict__ if not k.startswith('_'))

    def values(self):
        yield from (v for k, v in self.__dict__.items() if not k.startswith('_'))

    @classmethod
    def fields(cls):
        yield from (k for k in cls().__dict__ if not k.startswith('_'))


class EncryptionInfo:
    """
    Reports encryption information for an encrypted PDF.

    This information may not be changed, except when a PDF is saved.
    This object is not used to specify the encryption settings to save
    a PDF, due to non-overlapping information requirements.
    """

    def __init__(self, encdict):
        self._encdict = encdict

    @property
    def R(self):
        """Revision number of the security handler."""
        return self._encdict['R']

    @property
    def V(self):
        """Version of PDF password algorithm."""
        return self._encdict['V']

    @property
    def P(self):
        """Encoded permission bits.

        See :meth:`Pdf.allow` instead.
        """
        return self._encdict['P']

    @property
    def stream_method(self):
        """Encryption method used to encode streams."""
        return self._encdict['stream']

    @property
    def string_method(self):
        """Encryption method used to encode strings."""
        return self._encdict['string']

    @property
    def file_method(self):
        """Encryption method used to encode the whole file."""
        return self._encdict['file']

    @property
    def user_password(self):
        """If possible, return the user password.

        The user password can only be retrieved when a PDF is opened
        with the owner password and when older versions of the
        encryption algorithm are used.

        The password is always returned as ``bytes`` even if it has
        a clear Unicode representation.
        """
        return self._encdict['user_passwd']

    @property
    def encryption_key(self):
        """The RC4 or AES encryption key used for this file."""
        return self._encdict['encryption_key']

    @property
    def bits(self):
        """The number of encryption bits."""
        return len(self._encdict['encryption_key']) * 8


class Encryption(dict):
    """
    Specify the encryption settings to apply when a PDF is saved.

    Args:
        owner (str): The owner password to use. This allows full control
            of the file. If blank, the PDF will be encrypted and
            present as "(SECURED)" in PDF viewers. If the owner password
            is blank, the user password should be as well.
        user (str): The user password to use. With this password, some
            restrictions will be imposed by a typical PDF reader.
            If blank, the PDF can be opened by anyone, but only modified
            as allowed by the permissions in ``allow``.
        R (int): Select the security handler algorithm to use. Choose from:
            ``2``, ``3``, ``4`` or ``6``. By default, the highest version of
            is selected (``6``). ``5`` is a deprecated algorithm that should
            not be used.
        allow (pikepdf.Permissions): The permissions to set.
            If omitted, all permissions are granted to the user.
        aes (bool): If True, request the AES algorithm. If False, use RC4.
            If omitted, AES is selected whenever possible (R >= 4).
        metadata (bool): If True, also encrypt the PDF metadata. If False,
            metadata is not encrypted. Reading document metadata without
            decryption may be desirable in some cases. Requires ``aes=True``.
            If omitted, metadata is encrypted whenever possible.
    """

    def __init__(
        self, *, owner, user, R=6, allow=Permissions(), aes=True, metadata=True
    ):
        super().__init__()
        self.update(
            dict(R=R, owner=owner, user=user, allow=allow, aes=aes, metadata=metadata)
        )
