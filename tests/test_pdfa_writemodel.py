# SPDX-FileCopyrightText: 2026 James R. Barlow
# SPDX-License-Identifier: MPL-2.0

"""WriteModel.predict and pdfa.check: the validator sees the written form."""

from __future__ import annotations

import pytest

pytest.importorskip('jsonschema')

import base64
import zlib
from io import BytesIO
from typing import Any

from pdfa_samples import make_image_only_pdf

import pikepdf
from pikepdf import Array, Dictionary, Name
from pikepdf.pdfa import _engine, validate_written
from pikepdf.pdfa._api import check
from pikepdf.pdfa._save_kwargs import resolve_save_kwargs
from pikepdf.pdfa._shallow import shallow_json
from pikepdf.pdfa._writemodel import WriteModel

PIL = pytest.importorskip('PIL.Image')


def lzw_encode(data: bytes) -> bytes:
    """LZW-encode data as literal 9-bit codes, with a clear code every 200.

    Clearing the table keeps it below 511 entries, so every code is 9 bits.
    """
    codes: list[int] = []
    for start in range(0, len(data), 200):
        codes += [256, *data[start : start + 200]]
    codes.append(257)
    bits = ''.join(f'{code:09b}' for code in codes)
    bits += '0' * (-len(bits) % 8)
    return int(bits, 2).to_bytes(len(bits) // 8, 'big')


def jpeg_bytes() -> bytes:
    buffer = BytesIO()
    PIL.new('L', (8, 8), 128).save(buffer, format='JPEG')
    return buffer.getvalue()


HELLO = b'hello world'
PNG_ROWS = b'\x00abcd' * 4
XMP = b'<?xpacket begin="" id="W5M0MpCehiHzreSzNTczkc9d"?><x:xmpmeta xmlns:x="adobe:ns:meta/"/><?xpacket end="w"?>'


def cases() -> dict[str, tuple[bytes, Any, Any]]:
    """tag: (raw data, /Filter, /DecodeParms).

    Built afresh on each call: an Array or Dictionary becomes owned by the
    first Pdf it is added to.
    """
    return {
        'plain': (HELLO, None, None),
        'flate': (zlib.compress(HELLO), Name.FlateDecode, None),
        'fl': (zlib.compress(HELLO), Name('/Fl'), None),
        'flate-array': (zlib.compress(HELLO), Array([Name.FlateDecode]), None),
        'flate-predictor': (
            zlib.compress(PNG_ROWS),
            Name.FlateDecode,
            Dictionary(Predictor=12, Columns=4),
        ),
        'flate-bad-predictor': (
            zlib.compress(HELLO),
            Name.FlateDecode,
            Dictionary(Predictor=3),
        ),
        'flate-predictor-no-columns': (
            zlib.compress(HELLO),
            Name.FlateDecode,
            Dictionary(Predictor=12),
        ),
        'parms-length-mismatch': (
            zlib.compress(HELLO),
            Array([Name.FlateDecode]),
            Array([Dictionary(), Dictionary()]),
        ),
        'parms-empty-array': (zlib.compress(HELLO), Name.FlateDecode, Array([])),
        'lzw': (lzw_encode(HELLO), Name.LZWDecode, None),
        'lzw-early-change': (
            lzw_encode(HELLO),
            Name.LZWDecode,
            Dictionary(EarlyChange=1),
        ),
        'lzw-dct': (
            lzw_encode(b'not really a jpeg'),
            Array([Name.LZWDecode, Name.DCTDecode]),
            None,
        ),
        'ahx': (HELLO.hex().encode() + b'>', Name.ASCIIHexDecode, None),
        'a85': (base64.a85encode(HELLO) + b'~>', Name.ASCII85Decode, None),
        'a85-parms': (
            base64.a85encode(HELLO) + b'~>',
            Name.ASCII85Decode,
            Dictionary(Foo=1),
        ),
        'a85-flate': (
            base64.a85encode(zlib.compress(HELLO)) + b'~>',
            Array([Name.ASCII85Decode, Name.FlateDecode]),
            None,
        ),
        'runlength': (b'\x04hello\x80', Name.RunLengthDecode, None),
        'dct': (b'junk jpeg', Name.DCTDecode, None),
        'ccitt': (b'junk fax', Name.CCITTFaxDecode, None),
        'jbig2': (b'junk jbig2', Name.JBIG2Decode, None),
        'unknown': (b'junk', Name('/Foo'), None),
        'crypt-identity': (
            HELLO,
            Array([Name.Crypt]),
            Array([Dictionary(Name=Name.Identity)]),
        ),
        'empty-plain': (b'', None, None),
        'empty-flate': (b'', Name.FlateDecode, None),
        'empty-unknown': (b'', Name('/Foo'), None),
    }


def _set_filters(stream: pikepdf.Stream, filter_: Any, parms: Any) -> None:
    for key, value in (('/Filter', filter_), ('/DecodeParms', parms)):
        if value is None:
            if key in stream.stream_dict:
                del stream.stream_dict[key]
        else:
            stream.stream_dict[key] = value


def _build(source: str) -> pikepdf.Pdf:
    """A Pdf with one stream per case, tagged /PikeTestId, plus root XMP.

    ``source='memory'`` builds the streams in memory; ``'file'`` saves them
    unchanged and reopens, so that they are read from a file (with /Length).
    """
    pdf = pikepdf.new()
    streams = Array()
    for tag, (data, filter_, parms) in cases().items():
        stream = pdf.make_stream(data, PikeTestId=Name('/' + tag))
        _set_filters(stream, filter_, parms)
        streams.append(stream)
    pdf.Root.PikeTest = streams
    pdf.Root.Metadata = pdf.make_stream(
        zlib.compress(XMP),
        Type=Name.Metadata,
        Subtype=Name.XML,
        Filter=Name.FlateDecode,
        PikeTestId=Name('/root-metadata'),
    )
    if source == 'memory':
        return pdf
    buffer = BytesIO()
    pdf.save(
        buffer,
        compress_streams=False,
        stream_decode_level=pikepdf.StreamDecodeLevel.none,
        fix_metadata_version=False,
    )
    reopened = pikepdf.open(buffer)
    # Empty streams and the root metadata stream are decoded whatever the
    # settings; put the filters back.
    table = cases()
    for stream in reopened.Root.PikeTest:
        _data, filter_, parms = table[str(stream.PikeTestId)[1:]]
        _set_filters(stream, filter_, parms)
    reopened.Root.Metadata.write(zlib.compress(XMP), filter=Name.FlateDecode)
    return reopened


def _tagged(pdf: pikepdf.Pdf) -> dict[str, pikepdf.Stream]:
    return {
        str(obj.PikeTestId)[1:]: obj
        for obj in pdf.objects
        if isinstance(obj, pikepdf.Stream) and '/PikeTestId' in obj.stream_dict
    }


def _json(value: Any) -> Any:
    return None if value is None else shallow_json(value)


def _predicted(pdf: pikepdf.Pdf, kw: dict[str, Any]) -> dict[str, Any]:
    model = WriteModel.predict(pdf, kw)
    return {
        tag: tuple(_json(v) for v in model.stream_filters(stream))
        for tag, stream in _tagged(pdf).items()
    }


def _written(pdf: pikepdf.Pdf, kw: dict[str, Any]) -> dict[str, Any]:
    buffer = BytesIO()
    pdf.save(buffer, **kw)
    with pikepdf.open(buffer) as written:
        return {
            tag: (_json(stream.get('/Filter')), _json(stream.get('/DecodeParms')))
            for tag, stream in _tagged(written).items()
        }


SETTINGS = [
    ('2b', {'compress_streams': c, 'recompress_flate': r})
    for c in (True, False)
    for r in (False, True)
] + [('1b', {})]


class TestStreamFilters:
    @pytest.mark.parametrize('source', ['memory', 'file'])
    @pytest.mark.parametrize(('flavour', 'user'), SETTINGS)
    def test_model_matches_reality(self, source, flavour, user):
        kw = resolve_save_kwargs(flavour, **user)
        with _build(source) as pdf:
            predicted = _predicted(pdf, kw)
            written = _written(pdf, kw)
        assert set(predicted) == set(cases()) | {'root-metadata'}
        assert predicted == written

    def test_expected_rewrites(self):
        kw = resolve_save_kwargs('2b')
        with _build('memory') as pdf:
            predicted = _predicted(pdf, kw)
        assert predicted['lzw'] == ('/FlateDecode', None)
        assert predicted['flate-predictor'] == (
            '/FlateDecode',
            {'/Columns': 4, '/Predictor': 12},
        )
        assert predicted['lzw-dct'] == (['/LZWDecode', '/DCTDecode'], None)
        assert predicted['runlength'] == ('/RunLengthDecode', None)
        assert predicted['root-metadata'] == (None, None)

    def test_identity_is_in_memory(self):
        with _build('memory') as pdf:
            model = WriteModel.identity()
            stream = _tagged(pdf)['lzw']
            assert model.stream_filters(stream) == (Name.LZWDecode, None)


class TestObjects:
    def test_unreachable_objects_are_not_written(self):
        with make_image_only_pdf('2') as pdf:
            orphan = pdf.make_indirect(Dictionary(Orphan=True))
            model = WriteModel.predict(pdf, resolve_save_kwargs('2b'))
            objgens = {obj.objgen for obj in model.objects(pdf)}
            assert orphan.objgen not in objgens
            assert pdf.Root.objgen in objgens
            assert pdf.pages[0].obj.objgen in objgens
            identity = {obj.objgen for obj in WriteModel.identity().objects(pdf)}
            assert orphan.objgen in identity

    def test_each_object_once(self):
        with make_image_only_pdf('2') as pdf:
            model = WriteModel.predict(pdf, resolve_save_kwargs('2b'))
            objgens = [obj.objgen for obj in model.objects(pdf)]
            assert len(objgens) == len(set(objgens))

    def test_deep_graph_does_not_recurse(self):
        with pikepdf.new() as pdf:
            node = pdf.make_indirect(Dictionary())
            pdf.Root.Deep = node
            for _ in range(5000):
                child = pdf.make_indirect(Dictionary())
                node.Next = child
                node = child
            model = WriteModel.predict(pdf, resolve_save_kwargs('2b'))
            assert sum(1 for _ in model.objects(pdf)) >= 5001

    def test_encrypt_is_not_written(self, tmp_path):
        path = tmp_path / 'enc.pdf'
        with make_image_only_pdf('2') as pdf:
            pdf.save(path, encryption=pikepdf.Encryption(owner='o', user='u'))
        with pikepdf.open(path, password='u') as pdf:
            encrypt = pdf.trailer.Encrypt
            model = WriteModel.predict(pdf, resolve_save_kwargs('2b'))
            objgens = {obj.objgen for obj in model.objects(pdf)}
            if encrypt.is_indirect:
                assert encrypt.objgen not in objgens
            assert model.encrypted(pdf) is False


def lzw_image(pdf: pikepdf.Pdf, filters: Any, data: bytes) -> None:
    image = pdf.pages[0].Resources.XObject.Im0
    image.write(data, filter=filters)


class TestCheck:
    @pytest.mark.parametrize('compress', [True, False])
    def test_lzw_image_passes(self, compress, tmp_path):
        with make_image_only_pdf('2') as pdf:
            lzw_image(pdf, Name.LZWDecode, lzw_encode(bytes(range(64))))
            report = check(pdf, '2b', compress_streams=compress)
            assert report.verdict == 'pass', report.summary()
            identity = _engine.run(pdf, '2b')
            assert identity.verdict == 'fail'
            path = tmp_path / 'out.pdf'
            pdf.save(path, **report.save_kwargs)
        assert validate_written(path, '2b').verdict == 'pass'

    def test_lzw_dct_fails(self):
        with make_image_only_pdf('2') as pdf:
            lzw_image(
                pdf, Array([Name.LZWDecode, Name.DCTDecode]), lzw_encode(jpeg_bytes())
            )
            report = check(pdf, '2b')
        assert report.verdict == 'fail'
        assert 'ISO_19005_2:6.1.7.2-1' in {f.rule for f in report.findings}

    def test_filtered_root_metadata_passes_1b(self, tmp_path):
        with make_image_only_pdf('1') as pdf:
            raw = pdf.Root.Metadata.read_bytes()
            pdf.Root.Metadata.write(zlib.compress(raw), filter=Name.FlateDecode)
            identity = _engine.run(pdf, '1b')
            assert 'ISO_19005_1:6.7.2-2' in {f.rule for f in identity.findings}
            report = check(pdf, '1b')
            assert report.verdict == 'pass', report.summary()
            path = tmp_path / 'out.pdf'
            pdf.save(path, **report.save_kwargs)
        assert validate_written(path, '1b').verdict == 'pass'

    def test_orphaned_objects_are_ignored(self, tmp_path):
        with make_image_only_pdf('1') as pdf:
            filespec = Dictionary(
                Type=Name.Filespec,
                F=pikepdf.String('a.txt'),
                EF=Dictionary(F=pdf.make_stream(b'hi', Type=Name.EmbeddedFile)),
            )
            annot = pdf.make_indirect(
                Dictionary(
                    Type=Name.Annot,
                    Subtype=Name.FileAttachment,
                    Rect=[0, 0, 10, 10],
                    F=4,
                    FS=filespec,
                )
            )
            pdf.pages[0].obj.Annots = Array([annot])
            del pdf.pages[0].obj['/Annots']
            identity = _engine.run(pdf, '1b')
            assert identity.verdict != 'pass'
            report = check(pdf, '1b')
            assert report.verdict == 'pass', report.summary()
            path = tmp_path / 'out.pdf'
            pdf.save(path, **report.save_kwargs)
        assert validate_written(path, '1b').verdict == 'pass'

    def test_xref_stream_source_for_1b(self):
        buffer = BytesIO()
        with make_image_only_pdf('1') as pdf:
            pdf.save(buffer, object_stream_mode=pikepdf.ObjectStreamMode.generate)
        with pikepdf.open(buffer) as pdf:
            assert pdf.trailer.get('/Type') == Name.XRef
            identity = _engine.run(pdf, '1b')
            assert 'ISO_19005_1:6.1.4-3' in {f.rule for f in identity.findings}
            report = check(pdf, '1b')
        assert 'ISO_19005_1:6.1.4-3' not in {f.rule for f in report.findings}
        assert report.verdict == 'pass', report.summary()

    def test_encrypted_input(self, tmp_path):
        source = tmp_path / 'enc.pdf'
        with make_image_only_pdf('2') as pdf:
            pdf.save(source, encryption=pikepdf.Encryption(owner='o', user='u', R=4))
        out = tmp_path / 'out.pdf'
        with pikepdf.open(source, password='u') as pdf:
            report = check(pdf, '2b')
            assert report.verdict == 'pass', report.summary()
            pdf.save(out, **report.save_kwargs)
        assert validate_written(out, '2b').verdict == 'pass'

    def test_aes256_input_keeps_extension_level(self, tmp_path):
        # qpdf carries the input's Adobe extension level (8 for AES-256)
        # into the written /Extensions unless a version is forced, and the
        # validator does not check developer extensions.
        source = tmp_path / 'enc.pdf'
        with make_image_only_pdf('2') as pdf:
            pdf.save(source, encryption=pikepdf.Encryption(owner='o', user='u'))
        out = tmp_path / 'out.pdf'
        with pikepdf.open(source, password='u') as pdf:
            report = check(pdf, '2b')
            pdf.save(out, **report.save_kwargs)
        written = validate_written(out, '2b')
        assert report.verdict == written.verdict == 'not_checked'
        # qpdf renumbers objects when writing, so compare without locations
        assert [(f.rule, f.message) for f in report.findings] == [
            (f.rule, f.message) for f in written.findings
        ]

    def test_version_2_0(self):
        buffer = BytesIO()
        with make_image_only_pdf('2') as pdf:
            pdf.save(buffer, force_version='2.0')
        with pikepdf.open(buffer) as pdf:
            assert pdf.pdf_version == '2.0'
            report = check(pdf, '2b')
            assert report.verdict == 'fail'
            assert 'ISO_19005_2:6.1.2-1' in {f.rule for f in report.findings}
            assert check(pdf, '2b', force_version='1.7').verdict == 'pass'

    def test_rejects_bad_save_kwargs(self):
        with make_image_only_pdf('2') as pdf:
            with pytest.raises(ValueError):
                check(pdf, '2b', encryption=True)
            with pytest.raises(TypeError):
                check(pdf, '2b', nonsense=1)

    def test_save_kwargs_recorded(self):
        with make_image_only_pdf('2') as pdf:
            report = check(pdf, '2b', compress_streams=False)
        assert report.save_kwargs == resolve_save_kwargs('2b', compress_streams=False)

    def test_pure(self):
        def static_bytes(pdf):
            buffer = BytesIO()
            pdf.save(buffer, static_id=True, fix_metadata_version=False)
            return buffer.getvalue()

        with make_image_only_pdf('2') as pdf:
            lzw_image(pdf, Name.LZWDecode, lzw_encode(bytes(range(64))))
            pdf.make_indirect(Dictionary(Orphan=True))
            before = static_bytes(pdf)
            check(pdf, '2b')
            check(pdf, '1b')
            after = static_bytes(pdf)
        assert before == after


def set_interpolate(pdf: pikepdf.Pdf) -> None:
    pdf.pages[0].Resources.XObject.Im0.Interpolate = True


def add_pattern(pdf: pikepdf.Pdf) -> None:
    pattern = pdf.make_stream(
        b'0 0 10 10 re f',
        Type=Name.Pattern,
        PatternType=1,
        PaintType=1,
        TilingType=1,
        BBox=[0, 0, 10, 10],
        XStep=10,
        YStep=10,
        Resources=Dictionary(),
    )
    page = Dictionary(
        Type=Name.Page,
        MediaBox=[0, 0, 612, 792],
        Resources=Dictionary(Pattern=Dictionary(P0=pattern)),
        Contents=pdf.make_stream(b''),
    )
    pdf.pages.append(pikepdf.Page(page))


MUTATIONS = {'pass': [], 'fail': [set_interpolate], 'not_checked': [add_pattern]}


@pytest.mark.parametrize('kind', ['pass', 'fail', 'not_checked'])
@pytest.mark.parametrize('flavour', ['1b', '2b', '3b'])
def test_check_agrees_with_written(kind, flavour, tmp_path):
    path = tmp_path / 'out.pdf'
    with make_image_only_pdf(flavour[0]) as pdf:
        for mutate in MUTATIONS[kind]:
            mutate(pdf)
        report = check(pdf, flavour)
        pdf.save(path, **report.save_kwargs)
    written = validate_written(path, flavour)
    assert report.verdict == kind
    assert report.verdict == written.verdict
    assert {f.rule for f in report.findings} == {f.rule for f in written.findings}
