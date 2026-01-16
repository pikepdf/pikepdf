# SPDX-FileCopyrightText: 2022 James R. Barlow
# SPDX-License-Identifier: CC0-1.0

from __future__ import annotations

import pytest

from pikepdf import Pdf, PdfError, Dictionary, Name, Array

# pylint: disable=redefined-outer-name,pointless-statement,expression-not-assigned


@pytest.fixture
def congress(resources):
    with Pdf.open(resources / 'congress.pdf') as pdf:
        pdfimage = pdf.pages[0].Resources.XObject['/Im0']
        yield pdfimage, pdf


def test_get_equality_stream(congress):
    image = congress[0]
    assert image.ColorSpace == image['/ColorSpace'] == image.get('/ColorSpace')
    assert image.ColorSpace == image.stream_dict.ColorSpace

    with pytest.raises(AttributeError):
        image.NoSuchKey
    with pytest.raises(KeyError):
        image['/NoSuchKey']

    assert image.get('/NoSuchKey', 42) == 42


def test_get_equality_dict(congress):
    page = congress[1].pages[0]

    assert page.MediaBox == page['/MediaBox'] == page.get('/MediaBox')

    with pytest.raises((RuntimeError, PdfError)):
        page.stream_dict
    with pytest.raises(AttributeError):
        page.NoSuchKey
    with pytest.raises(KeyError):
        page['/NoSuchKey']

    assert page.get('/NoSuchKey', 42) == 42

def test_dictionary_copy_semantics():
    """Ensure copy() creates a shallow copy, not a reference."""
    d1 = Dictionary({'/A': 1, '/B': 2})
    d2 = d1.copy()

    # 1. Content equality check
    assert d1 == d2
    assert d1.keys() == d2.keys()

    # 2. Independence check (Modifying copy shouldn't affect original)
    d2['/C'] = 3
    assert '/C' in d2
    assert '/C' not in d1

    # 3. Independence check (Modifying original shouldn't affect copy)
    d1['/A'] = 99
    assert d1['/A'] == 99
    assert d2['/A'] == 1  # Should remain 1


def test_dictionary_update():
    """Ensure update() merges keys correctly."""
    d = Dictionary({'/A': 1, '/B': 2})

    # 1. Update with new key
    d.update({'/C': 3})
    assert d['/C'] == 3

    # 2. Update overwriting existing key
    d.update({'/A': 100})
    assert d['/A'] == 100

    # 3. Ensure untouched keys remain
    assert d['/B'] == 2

    # 4. Test mixed Python types
    d.update({'/D': "hello", '/E': 3.14})
    assert str(d['/D']) == "hello"
    assert float(d['/E']) == 3.14

def test_copy_raises_on_non_dict():
    """Ensure we can't call .copy() on an Array or other types."""
    # Since QPDFObjectHandle wraps everything, we must ensure .copy()
    # throws the error we defined in C++ if called on an Array.
    arr = Array([1, 2, 3])

    with pytest.raises(TypeError, match="only supported for Dictionaries"):
        arr.copy()

def test_dictionary_update_from_pikepdf_dict():
    """Ensure we can update a pikepdf.Dictionary using another pikepdf.Dictionary."""
    d1 = Dictionary({'/A': 1})
    d2 = Dictionary({'/B': 2, '/A': 99}) # Overlap on /A

    # This previously would have raised TypeError
    d1.update(d2)

    assert d1['/A'] == 99
    assert d1['/B'] == 2
