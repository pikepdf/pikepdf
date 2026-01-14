# SPDX-FileCopyrightText: 2022 James R. Barlow
# SPDX-License-Identifier: CC0-1.0

from __future__ import annotations

import io
import pytest

from pikepdf import Pdf, PdfError, Dictionary

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



@pytest.fixture
def bad_pdf_obj():
    # A minimal valid PDF structure so QPDF doesn't complain on open.
    # We include an "orphan" object (4 0 obj) that contains the bad key.
    BAD_PDF_DATA = (
        b'%PDF-1.0\n'
        b'1 0 obj << /Type /Catalog /Pages 2 0 R >> endobj\n'
        b'2 0 obj << /Type /Pages /Kids [3 0 R] /Count 1 >> endobj\n'
        b'3 0 obj << /Type /Page /MediaBox [0 0 200 200] >> endobj\n'
        b'4 0 obj << /Key\x80 (Value) >> endobj\n'
        b'trailer << /Root 1 0 R >>\n'
        b'%%EOF\n'
    )
    with Pdf.open(io.BytesIO(BAD_PDF_DATA)) as bad_pdf:
        bad_obj = bad_pdf.get_object(4, 0)
        yield bad_pdf, bad_obj


def test_iterate_invalid_utf8_keys(bad_pdf_obj):
    """Verify we can iterate over dictionary keys with invalid UTF-8 without crashing."""
    obj = bad_pdf_obj[1]

    # 1. Test keys() - this triggered the original crash
    keys = list(obj.keys())
    assert len(keys) == 1

    # 2. Verify the key was preserved using surrogateescape
    # We expect the bad byte \x80 to become \udc80
    bad_key = keys[0]
    assert bad_key == "/Key\udc80"

    # 3. Verify we can round-trip it back to the original bytes
    assert bad_key.encode("utf-8", "surrogateescape") == b"/Key\x80"


def test_items_invalid_utf8(bad_pdf_obj):
    """Verify items() iteration works and values are accessible."""
    obj = bad_pdf_obj[1]

    # This iterates both keys and values
    items = list(obj.items())

    assert len(items) == 1
    key, value = items[0]

    assert key == "/Key\udc80"
    assert str(value) == "Value"


def test_contains_invalid_utf8(bad_pdf_obj):
    """Verify 'in' operator works with the surrogated key."""
    obj = bad_pdf_obj[1]

    # We should be able to find the key if we ask for the surrogate version
    assert "/Key\udc80" in obj


def test_invalid_utf8_keys():
    # The surrogate code \udc80 represents the raw byte 0x80.
    # We use this string to inject "bad bytes" into the PDF structure
    # via the C++ layer.
    bad_key_surrogate = '/Key\udc80'

    # 1. Test Writing (hits key_to_string logic)
    # This creates a dictionary entry with the raw key b'/Key\x80'
    d = Dictionary()
    d[bad_key_surrogate] = 1

    # 2. Test __contains__ (hits __contains__ try/catch logic)
    assert bad_key_surrogate in d

    # 3. Test __getitem__ (hits key_to_string logic for lookups)
    assert d[bad_key_surrogate] == 1

    # 4. Test keys() iteration (hits safe_decode logic)
    # If this wasn't fixed, this line would raise UnicodeDecodeError
    keys = list(d.keys())
    assert bad_key_surrogate in keys
    assert len(keys) == 1

    # 5. Test Deletion
    del d[bad_key_surrogate]
    assert bad_key_surrogate not in d


def test_dictionary_coverage_edges(bad_pdf_obj):
    """Cover edge cases for bytes keys and invalid types in __contains__."""
    _, obj = bad_pdf_obj

    # Cover lookup using a bytes object
    # We know the key is /Key\x80. In C++, this matches the raw bytes.
    assert obj[b'/Key\x80'] == 'Value'

    # Cover 'in' operator with invalid type
    # This forces key_to_string to throw TypeError, which is caught and returns False
    assert 123 not in obj
    assert None not in obj

    # Cover iterating the object directly (not .keys())
    iterator_keys = list(obj)
    assert len(iterator_keys) == 1
    assert iterator_keys[0] == '/Key\udc80'