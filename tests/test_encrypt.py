import pytest

import pikepdf


@pytest.fixture
def trivial(resources):
    return pikepdf.open(resources / 'pal-1bit-trivial.pdf')


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
    pdf_owner = pikepdf.open(outpdf, password=owner)
    assert pdf_owner.is_encrypted
    pdf_user = pikepdf.open(outpdf, password=user)
    assert pdf_user.is_encrypted


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
