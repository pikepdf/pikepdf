# SPDX-FileCopyrightText: 2022 James R. Barlow
# SPDX-License-Identifier: CC0-1.0

from __future__ import annotations

import pytest

import pikepdf

# pylint: disable=redefined-outer-name


@pytest.fixture
def trivial(resources):
    return pikepdf.open(resources / 'pal-1bit-trivial.pdf')


@pytest.fixture
def graph_encrypted(resources):
    return pikepdf.open(resources / 'graph-encrypted.pdf', password='owner')


@pytest.mark.parametrize(
    "R,owner,user",
    [
        (6, "foo", "bar"),
        (4, "password", "password"),
        (3, "12345678", "secret"),
        (2, "qwerty", "123456"),
    ],
)
def test_encrypt_basic(trivial, outpdf, R, owner, user):
    trivial.save(outpdf, encryption=dict(R=R, owner=owner, user=user))
    with pikepdf.open(outpdf, password=owner) as pdf_owner:
        assert pdf_owner.is_encrypted
        assert pdf_owner.owner_password_matched
        if owner != user:
            assert not pdf_owner.user_password_matched
        else:
            assert pdf_owner.user_password_matched
    with pikepdf.open(outpdf, password=user) as pdf_user:
        assert pdf_user.is_encrypted
        assert pdf_user.user_password_matched
        if owner != user:
            assert not pdf_user.owner_password_matched
        else:
            assert pdf_user.owner_password_matched


def test_encrypt_R5(trivial, outpdf):
    with pytest.warns(UserWarning):
        trivial.save(outpdf, encryption=dict(R=5, owner='foo', user='foo'))


@pytest.mark.parametrize("R", [-1, 0, 1, 7, 9, 42])
def test_encrypt_invalid_level_value(trivial, outpdf, R):
    with pytest.raises(ValueError):
        trivial.save(outpdf, encryption=dict(R=R, owner='foo', user='foo'))


@pytest.mark.parametrize("R", [3.14, '6', b'6', None])
def test_encrypt_invalid_level(trivial, outpdf, R):
    with pytest.raises(TypeError):
        trivial.save(outpdf, encryption=dict(R=R, owner='foo', user='foo'))


def test_encrypt_without_owner(trivial, outpdf):
    trivial.save(outpdf, encryption=dict(user='foo'))


def test_encrypt_no_passwords(trivial, outpdf):
    trivial.save(outpdf, encryption=dict(R=6))


@pytest.mark.parametrize(
    'highres, lowres', [(True, True), (False, True), (False, False)]
)
def test_encrypt_permissions_deny(trivial, outpdf, highres, lowres):
    perms = pikepdf.models.Permissions(
        extract=False, print_highres=highres, print_lowres=lowres
    )
    trivial.save(
        outpdf, encryption=pikepdf.Encryption(owner='sun', user='moon', allow=perms)
    )
    with pikepdf.open(outpdf, password='sun') as pdf:
        assert not pdf.allow.extract
        assert pdf.allow.modify_form


def test_encrypt_info(trivial, outpdf):
    trivial.save(outpdf, encryption=dict(R=4, owner='foo', user='bar'))
    with pikepdf.open(outpdf, password='foo') as pdf:
        assert pdf.encryption.user_password == b'bar'
        assert pdf.encryption.bits == 128
        assert pdf.encryption.R == 4
        assert pdf.encryption.V == 4
        assert pdf.encryption.P == -3392
        assert pdf.encryption.stream_method == pikepdf._core.EncryptionMethod.aes
        assert pdf.encryption.string_method == pikepdf._core.EncryptionMethod.aes
        assert pdf.encryption.file_method == pikepdf._core.EncryptionMethod.aes
        assert pdf.encryption.encryption_key[:2] == b'\x02\xdc'


@pytest.mark.parametrize(
    "R,owner,user,aes,metadata,err",
    [
        (6, "foo", "bar", 42, False, r"aes.*bool"),
        (6, "password", "password", True, 42, r"metadata.*bool"),
        (3, "12345678", "secret", False, True, r"metadata.*R < 4"),
        (2, "qwerty", "123456", True, False, r"AES.*R < 4"),
        (6, "rc4", "rc4", False, True, r"R = 6.*AES"),
        (4, "met", "met", False, True, r"unless AES"),
        (3, "密码", "password", False, False, r"password.*not encodable"),
        (4, "owner", "密码", False, False, r"password.*not encodable"),
        (6, None, "a", True, True, r"may not be None"),
        (6, "a", None, True, True, r"may not be None"),
    ],
)
def test_bad_settings(trivial, outpdf, R, owner, user, aes, metadata, err):
    with pytest.raises(Exception, match=err):
        trivial.save(
            outpdf,
            encryption=pikepdf.Encryption(
                R=R, owner=owner, user=user, aes=aes, metadata=metadata
            ),
        )


def test_block_encryption_and_normalize(trivial, outpdf):
    with pytest.raises(ValueError, match=r'encryption and normalize_content'):
        trivial.save(
            outpdf,
            encryption=pikepdf.Encryption(owner='foo', user='bar'),
            normalize_content=True,
        )


def test_consistency_saving_removes_encryption(graph_encrypted, outpdf):
    # This was not intended behavior. It's a side effect of unconditionally calling
    # w.setDecodeLevel(), which disables preserving encryption in
    # QPDFWriter::doWriteSetup()
    graph_encrypted.save(outpdf)
    with pikepdf.open(outpdf) as pdf:
        assert not pdf.is_encrypted


def test_save_without_encryption(graph_encrypted, outpdf):
    graph_encrypted.save(outpdf, encryption=False)
    with pikepdf.open(outpdf) as pdf:
        assert not pdf.is_encrypted


def test_save_preserve_encryption(graph_encrypted, outpdf):
    graph_encrypted.save(outpdf, encryption=True)
    with pikepdf.open(outpdf, password='owner') as pdf:
        assert pdf.is_encrypted


def test_preserve_encryption_not_encrypted(trivial, outpdf):
    with pytest.raises(ValueError):
        trivial.save(outpdf, encryption=True)


def test_access_encryption_not_encrypted(trivial):
    assert not trivial._encryption_data
