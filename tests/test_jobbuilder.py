# SPDX-FileCopyrightText: 2026 James R. Barlow
# SPDX-License-Identifier: CC0-1.0

from __future__ import annotations

import json

import pytest

from pikepdf import Encryption, JobBuilder, JobUsageError, Pdf, Permissions
from pikepdf._core import Job
from pikepdf.jobs import ALL_JSON_KEYS

# -- Dict-shape / round-trip (no qpdf run) ---------------------------------


def test_basic_io_shape():
    spec = JobBuilder().input('in.pdf').output('out.pdf').to_json()
    assert spec == {'inputFile': 'in.pdf', 'outputFile': 'out.pdf'}


def test_input_password_shape():
    spec = JobBuilder().input('in.pdf', password='pw').to_json()
    assert spec == {'inputFile': 'in.pdf', 'password': 'pw'}


def test_empty_and_input_conflict():
    with pytest.raises(ValueError, match='empty'):
        JobBuilder().input('in.pdf').empty()
    with pytest.raises(ValueError, match='input file'):
        JobBuilder().empty().input('in.pdf')


def test_pages_shape():
    spec = (
        JobBuilder()
        .empty()
        .output('out.pdf')
        .add_pages('a.pdf')
        .add_pages('b.pdf', '1-5')
        .add_pages('c.pdf', 'z-1', password='pw')
        .to_json()
    )
    assert spec['pages'] == [
        {'file': 'a.pdf'},
        {'file': 'b.pdf', 'range': '1-5'},
        {'file': 'c.pdf', 'range': 'z-1', 'password': 'pw'},
    ]


def test_split_pages_shape():
    assert JobBuilder().split_pages().to_json() == {'splitPages': ''}
    assert JobBuilder().split_pages(10).to_json() == {'splitPages': '10'}


def test_compress_shape():
    spec = (
        JobBuilder()
        .compress(
            object_streams='generate',
            recompress_flate=True,
            compression_level=9,
            compress_streams=True,
        )
        .to_json()
    )
    assert spec == {
        'objectStreams': 'generate',
        'recompressFlate': '',
        'compressionLevel': '9',
        'compressStreams': 'y',
    }


def test_rotate_shape():
    spec = JobBuilder().rotate('+90', '1-z').rotate(180).to_json()
    assert spec['rotate'] == ['+90:1-z', '180']


def test_attachment_shape():
    spec = (
        JobBuilder()
        .add_attachment('data.csv', key='data', mimetype='text/csv', replace=True)
        .copy_attachments_from('other.pdf', prefix='ext-', password='pw')
        .remove_attachment('old')
        .to_json()
    )
    assert spec['addAttachment'] == [
        {'file': 'data.csv', 'key': 'data', 'mimetype': 'text/csv', 'replace': ''}
    ]
    assert spec['copyAttachmentsFrom'] == [
        {'file': 'other.pdf', 'prefix': 'ext-', 'password': 'pw'}
    ]
    assert spec['removeAttachment'] == ['old']


def test_overlay_underlay_shape():
    spec = (
        JobBuilder()
        .add_overlay('wm.pdf', to='1-z', from_='1', repeat='1')
        .add_underlay('bg.pdf', from_='1')
        .to_json()
    )
    assert spec['overlay'] == [
        {'file': 'wm.pdf', 'to': '1-z', 'from': '1', 'repeat': '1'}
    ]
    assert spec['underlay'] == [{'file': 'bg.pdf', 'from': '1'}]


def test_limits_shape():
    spec = JobBuilder().limits(parser_max_nesting=50, max_stream_filters=100).to_json()
    assert spec['global'] == {'parserMaxNesting': '50', 'maxStreamFilters': '100'}


def test_to_json_is_a_copy():
    builder = JobBuilder().input('in.pdf')
    spec = builder.to_json()
    spec['inputFile'] = 'mutated'
    assert builder.to_json()['inputFile'] == 'in.pdf'


def test_to_json_str_roundtrips():
    builder = JobBuilder().input('in.pdf').output('out.pdf')
    assert json.loads(builder.to_json_str()) == builder.to_json()


# -- Encryption permission inversion ---------------------------------------


def test_encrypt_default_permissions_256():
    spec = JobBuilder().encrypt(owner_password='owner').to_json()
    flags = spec['encrypt']['256bit']
    # DEFAULT_PERMISSIONS: modify_assembly=False, everything else allowed.
    assert flags['print'] == 'full'
    assert flags['extract'] == 'y'
    assert flags['assemble'] == 'n'  # default modify_assembly is False
    assert flags['modifyOther'] == 'y'
    assert spec['encrypt']['ownerPassword'] == 'owner'
    assert spec['encrypt']['userPassword'] == ''


def test_encrypt_print_levels():
    f = JobBuilder().encrypt(allow=Permissions(print_highres=False)).to_json()
    assert f['encrypt']['256bit']['print'] == 'low'
    f = JobBuilder().encrypt(allow=Permissions(print_lowres=False)).to_json()
    assert f['encrypt']['256bit']['print'] == 'none'


def test_encrypt_metadata_cleartext():
    f = JobBuilder().encrypt(metadata=False).to_json()
    assert f['encrypt']['256bit']['cleartextMetadata'] == ''
    f = JobBuilder().encrypt(metadata=True).to_json()
    assert 'cleartextMetadata' not in f['encrypt']['256bit']


def test_encrypt_40bit_coarse():
    none_modifiable = Permissions(
        modify_other=False,
        modify_form=False,
        modify_annotation=False,
        modify_assembly=False,
    )
    f = JobBuilder().encrypt(bits=40, allow=none_modifiable).to_json()
    flags = f['encrypt']['40bit']
    assert '40bit' in f['encrypt']
    assert flags['modify'] == 'none'  # nothing modifiable -> none
    assert 'assemble' not in flags  # 40-bit has no granular assemble
    # A modifiable permission promotes the coarse modify level.
    f2 = JobBuilder().encrypt(bits=40, allow=Permissions(modify_other=True)).to_json()
    assert f2['encrypt']['40bit']['modify'] == 'all'


def test_encrypt_128bit_aes():
    f = JobBuilder().encrypt(bits=128, aes=True, force_v4=True).to_json()
    assert f['encrypt']['128bit']['useAes'] == 'y'
    assert f['encrypt']['128bit']['forceV4'] == ''


def test_encrypt_from_encryption_object():
    enc = Encryption(owner='o', user='u', allow=Permissions(extract=False))
    f = JobBuilder().encrypt(enc).to_json()
    assert f['encrypt']['ownerPassword'] == 'o'
    assert f['encrypt']['userPassword'] == 'u'
    assert f['encrypt']['256bit']['extract'] == 'n'  # R=6 -> 256-bit


def test_encrypt_object_and_kwargs_conflict():
    with pytest.raises(ValueError, match='not both'):
        JobBuilder().encrypt(Encryption(owner='o'), owner_password='x')


def test_encrypt_bad_bits():
    with pytest.raises(ValueError, match='bits'):
        JobBuilder().encrypt(bits=64)  # type: ignore[arg-type]


# -- .set() escape hatch ----------------------------------------------------


def test_set_known_keys():
    spec = JobBuilder().set(no_warn=True, compression_level=5, verbose=False).to_json()
    assert spec == {'noWarn': '', 'compressionLevel': 5}


def test_set_unknown_key():
    with pytest.raises(ValueError, match='Unknown job option'):
        JobBuilder().set(definitely_not_a_key=1)


# -- Equivalence: actually run qpdf -----------------------------------------


def test_run_passthrough(resources, outpdf):
    job = JobBuilder().input(resources / 'outlines.pdf').output(outpdf).run()
    assert job.exit_code == 0
    with Pdf.open(outpdf) as pdf:
        assert len(pdf.pages) >= 1


def test_run_encrypt_decrypt(resources, outpdf, outdir):
    JobBuilder().input(resources / 'outlines.pdf').output(outpdf).encrypt(
        owner_password='owner', allow=Permissions(extract=False)
    ).run()
    with Pdf.open(outpdf, password='owner') as pdf:
        assert pdf.is_encrypted
        assert not pdf.allow.extract

    decrypted = outdir / 'decrypted.pdf'
    JobBuilder().input(outpdf, password='owner').output(decrypted).decrypt().run()
    with Pdf.open(decrypted) as pdf:
        assert not pdf.is_encrypted


def test_run_merge(resources, outpdf):
    src = resources / 'outlines.pdf'
    with Pdf.open(src) as pdf:
        n = len(pdf.pages)
    JobBuilder().empty().output(outpdf).add_pages(src).add_pages(src).run()
    with Pdf.open(outpdf) as pdf:
        assert len(pdf.pages) == 2 * n


def test_run_split(resources, outdir):
    src = resources / 'outlines.pdf'
    with Pdf.open(src) as pdf:
        n = len(pdf.pages)
    JobBuilder().input(src).output(outdir / 'page-%d.pdf').split_pages().run()
    produced = sorted(outdir.glob('page-*.pdf'))
    assert len(produced) == n


def test_run_linearize(resources, outpdf):
    job = (
        JobBuilder().input(resources / 'outlines.pdf').output(outpdf).linearize().run()
    )
    assert job.exit_code == 0
    with Pdf.open(outpdf) as pdf:
        assert pdf.is_linearized


# -- Validation -------------------------------------------------------------


def test_build_invalid_raises():
    builder = JobBuilder()
    builder._spec = {'inputFile': []}  # type: ignore[dict-item]
    with pytest.raises(JobUsageError):
        builder.build()


def test_build_unknown_json_key_raises():
    builder = JobBuilder()
    builder._spec = {'invalidJsonSetting': '123'}
    with pytest.raises(RuntimeError):
        builder.build()


# -- Staged workflow --------------------------------------------------------


def test_create_pdf_staged(resources, outpdf):
    builder = JobBuilder().input(resources / 'outlines.pdf').output(outpdf)
    job = builder.build()
    pdf = job.create_pdf()
    del pdf.pages[1]
    job.write_pdf(pdf)
    with Pdf.open(outpdf) as reopened:
        assert len(reopened.pages) == 1


# -- Schema-drift guard -----------------------------------------------------


def _collect_schema_keys(node, acc: set[str]) -> None:
    if isinstance(node, dict):
        for key, value in node.items():
            acc.add(key)
            _collect_schema_keys(value, acc)
    elif isinstance(node, list):
        for item in node:
            _collect_schema_keys(item, acc)


def test_all_json_keys_exist_in_schema():
    schema = json.loads(Job.job_json_schema(schema=Job.LATEST_JOB_JSON))
    schema_keys: set[str] = set()
    _collect_schema_keys(schema, schema_keys)
    # 'Bits' is a schema-only discriminator; it is never emitted by the builder.
    missing = ALL_JSON_KEYS - schema_keys
    assert not missing, f"Job keys absent from libqpdf schema: {sorted(missing)}"
