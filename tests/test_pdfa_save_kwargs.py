# SPDX-FileCopyrightText: 2026 James R. Barlow
# SPDX-License-Identifier: MPL-2.0

from __future__ import annotations

import pytest

pytest.importorskip('jsonschema')

import pikepdf  # noqa: E402
from pikepdf import ObjectStreamMode, StreamDecodeLevel  # noqa: E402
from pikepdf.pdfa._flavour import Flavour  # noqa: E402
from pikepdf.pdfa._save_kwargs import (  # noqa: E402
    PART1_PINNED_KEYS,
    PINNED_KEYS,
    USER_KEYS,
    describe_pins,
    resolve_save_kwargs,
)

FLAVOURS = ['1b', '2b', '3b']

COMMON_PINS = {
    'preserve_pdfa': True,
    'encryption': None,
    'qdf': False,
    'normalize_content': False,
    'stream_decode_level': StreamDecodeLevel.generalized,
    'fix_metadata_version': False,
}
PART1_PINS = {
    'object_stream_mode': ObjectStreamMode.disable,
    'force_version': '1.4',
}
USER_DEFAULTS = {
    'compress_streams': True,
    'recompress_flate': False,
    'linearize': False,
    'progress': None,
    'deterministic_id': False,
    'static_id': False,
    'min_version': '',
}

CONFLICTS = {
    'preserve_pdfa': False,
    'encryption': True,
    'qdf': True,
    'normalize_content': True,
    'stream_decode_level': StreamDecodeLevel.all,
    'fix_metadata_version': True,
    'object_stream_mode': ObjectStreamMode.generate,
    'force_version': '1.5',
}


@pytest.mark.parametrize('flavour', FLAVOURS)
def test_defaults(flavour):
    kw = resolve_save_kwargs(flavour)
    expected = {**COMMON_PINS, **USER_DEFAULTS}
    if flavour == '1b':
        expected.update(PART1_PINS)
    else:
        expected['object_stream_mode'] = ObjectStreamMode.generate
        expected['force_version'] = ''
    assert kw == expected
    assert 'filename_or_stream' not in kw


def test_flavour_enum_accepted():
    assert resolve_save_kwargs(Flavour.PDFA_2B) == resolve_save_kwargs('2b')


def test_bad_flavour():
    with pytest.raises(ValueError):
        resolve_save_kwargs('4u')


def test_key_sets_cover_save_signature():
    import inspect

    params = set(inspect.signature(pikepdf.Pdf.save).parameters) - {
        'self',
        'filename_or_stream',
    }
    assert PINNED_KEYS | USER_KEYS == params
    assert not PINNED_KEYS & USER_KEYS
    assert PART1_PINNED_KEYS <= USER_KEYS


@pytest.mark.parametrize('key', sorted(CONFLICTS))
def test_pinned_rejected(key):
    with pytest.raises(ValueError) as exc:
        resolve_save_kwargs('1b', **{key: CONFLICTS[key]})
    msg = str(exc.value)
    assert key in msg
    assert 'PDF/A-1b' in msg


@pytest.mark.parametrize('key', sorted(COMMON_PINS))
@pytest.mark.parametrize('flavour', FLAVOURS)
def test_pinned_accepted(flavour, key):
    kw = resolve_save_kwargs(flavour, **{key: COMMON_PINS[key]})
    assert kw[key] == COMMON_PINS[key]


@pytest.mark.parametrize('key', sorted(PART1_PINS))
def test_part1_pinned_accepted(key):
    assert resolve_save_kwargs('1b', **{key: PART1_PINS[key]})[key] == PART1_PINS[key]


def test_part1_force_version_tuple_accepted():
    assert resolve_save_kwargs('1b', force_version=('1.4', 0))['force_version'] == (
        '1.4',
        0,
    )


@pytest.mark.parametrize('flavour', FLAVOURS)
def test_encryption_false_accepted(flavour):
    assert resolve_save_kwargs(flavour, encryption=False)['encryption'] is False


@pytest.mark.parametrize('flavour', ['2b', '3b'])
def test_object_stream_mode_free_for_part23(flavour):
    for mode in ObjectStreamMode:
        assert resolve_save_kwargs(flavour, object_stream_mode=mode)[
            'object_stream_mode'
        ] == (mode)


def test_versions_2b():
    assert resolve_save_kwargs('2b', min_version='1.7')['min_version'] == '1.7'
    assert resolve_save_kwargs('2b', force_version='1.7')['force_version'] == '1.7'
    assert resolve_save_kwargs('2b', force_version=('1.6', 0))['force_version'] == (
        '1.6',
        0,
    )
    with pytest.raises(ValueError, match='min_version'):
        resolve_save_kwargs('2b', min_version='2.0')
    with pytest.raises(ValueError, match='force_version'):
        resolve_save_kwargs('2b', force_version='2.0')


def test_versions_1b():
    assert resolve_save_kwargs('1b', min_version='1.4')['min_version'] == '1.4'
    assert resolve_save_kwargs('1b', min_version='1.3')['min_version'] == '1.3'
    with pytest.raises(ValueError, match='min_version'):
        resolve_save_kwargs('1b', min_version='1.5')


@pytest.mark.parametrize('key', ['min_version', 'force_version'])
def test_extension_level_rejected(key):
    with pytest.raises(ValueError, match='extension'):
        resolve_save_kwargs('2b', **{key: ('1.7', 8)})


@pytest.mark.parametrize('bad', ['x.y', '1', '1.7.2', ('x', 0), 17])
def test_garbage_version_rejected(bad):
    with pytest.raises(ValueError):
        resolve_save_kwargs('2b', min_version=bad)


def test_unknown_key():
    with pytest.raises(TypeError, match="unexpected keyword argument 'foo'"):
        resolve_save_kwargs('2b', foo=1)


def test_filename_not_accepted():
    with pytest.raises(TypeError):
        resolve_save_kwargs('2b', filename_or_stream='x.pdf')


def test_user_choices_pass_through():
    def progress(_n):
        pass

    kw = resolve_save_kwargs(
        '3b',
        compress_streams=False,
        recompress_flate=True,
        linearize=True,
        progress=progress,
        deterministic_id=True,
        static_id=True,
    )
    assert kw['compress_streams'] is False
    assert kw['recompress_flate'] is True
    assert kw['linearize'] is True
    assert kw['progress'] is progress
    assert kw['deterministic_id'] is True
    assert kw['static_id'] is True


@pytest.mark.parametrize('flavour', FLAVOURS)
def test_describe_pins(flavour):
    pins = describe_pins(flavour)
    assert set(COMMON_PINS) <= set(pins)
    assert ('object_stream_mode' in pins) == (flavour == '1b')
    assert all(isinstance(v, str) and v for v in pins.values())
    assert (
        'generalized' in pins['stream_decode_level']
        or 'filter' in (pins['stream_decode_level'])
    )


def _one_page():
    pdf = pikepdf.new()
    pdf.add_blank_page()
    return pdf


@pytest.mark.parametrize('flavour', FLAVOURS)
def test_round_trip(flavour, tmp_path):
    out = tmp_path / 'out.pdf'
    with _one_page() as pdf:
        pdf.save(out, **resolve_save_kwargs(flavour))
    with pikepdf.open(out) as pdf:
        assert len(pdf.pages) == 1
        if flavour == '1b':
            assert pdf.pdf_version == '1.4'
            assert pdf.trailer.get('/Type') != pikepdf.Name.XRef


@pytest.mark.parametrize('flavour', FLAVOURS)
def test_linearize_round_trip(flavour, tmp_path):
    out = tmp_path / 'out.pdf'
    with _one_page() as pdf:
        pdf.save(out, **resolve_save_kwargs(flavour, linearize=True))
    with pikepdf.open(out) as pdf:
        assert pdf.is_linearized
