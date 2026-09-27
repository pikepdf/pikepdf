# SPDX-FileCopyrightText: 2026 James R. Barlow
# SPDX-License-Identifier: MPL-2.0

"""Embedded and associated files (ISO 19005-3 clause 6.8)."""

from __future__ import annotations

import pytest

pytest.importorskip('jsonschema')

from pdfa_samples import (
    assert_verapdf_agrees,
    assert_verapdf_fails,
    make_image_only_pdf,
    save_candidate,
)

import pikepdf
from pikepdf import Array, AttachedFileSpec, Dictionary, Name, String, pdfa
from pikepdf.pdfa import _engine, prepare, validate_written
from pikepdf.pdfa._report import ValidationReport


def rule_ids(report: ValidationReport) -> set[str]:
    return {f.rule for f in report.findings}


def kinds(report: ValidationReport) -> set[str]:
    return {f.kind for f in report.findings}


def check(pdf: pikepdf.Pdf, tmp_path, part: str = '3') -> ValidationReport:
    path = save_candidate(pdf, tmp_path / 'c.pdf', part)
    return validate_written(path, f'{part}b')


def attach(pdf: pikepdf.Pdf, name: str = 'data.xml', **kwargs) -> pikepdf.Dictionary:
    """Attach a file through pdf.attachments; return its file specification."""
    kwargs.setdefault('mime_type', 'application/xml')
    kwargs.setdefault('relationship', Name.Data)
    pdf.attachments[name] = AttachedFileSpec(pdf, b'<a/>', filename=name, **kwargs)
    return pdf.attachments[name].obj


def embedded_stream(filespec: pikepdf.Dictionary) -> pikepdf.Stream:
    return filespec.EF.F


def filespec_by_hand(pdf: pikepdf.Pdf, **extra) -> pikepdf.Dictionary:
    """An indirect file specification of an embedded file, not yet listed."""
    stream = pdf.make_stream(
        b'hello',
        Type=Name.EmbeddedFile,
        Subtype=Name('/text/plain'),
        Params=Dictionary(Size=5),
    )
    entries = dict(
        Type=Name.Filespec,
        F=String('a.txt'),
        UF=String('a.txt'),
        AFRelationship=Name.Supplement,
        EF=Dictionary(F=stream, UF=stream),
    )
    entries.update(extra)
    return pdf.make_indirect(Dictionary(**entries))


def list_in_name_tree(pdf: pikepdf.Pdf, *filespecs: pikepdf.Object) -> None:
    items: list[pikepdf.Object] = []
    for index, filespec in enumerate(filespecs):
        items += [String(f'file{index}'), filespec]
    pdf.Root.Names = Dictionary(EmbeddedFiles=Dictionary(Names=Array(items)))


# --- approved -----------------------------------------------------------------


def test_attachment_passes_3b(tmp_path):
    with make_image_only_pdf('3') as pdf:
        attach(
            pdf,
            description='Invoice data',
            creation_date='D:20260101120000Z',
            mod_date="D:20260102120000+01'00'",
        )
        report = check(pdf, tmp_path)
    assert report.verdict == 'pass', report.summary()
    assert_verapdf_agrees(tmp_path / 'c.pdf', '3b')


def test_pdfa_save_with_attachment(tmp_path):
    base = tmp_path / 'base.pdf'
    with pikepdf.new() as pdf:
        pdf.add_blank_page()
        pdfa.save(pdf, base, '3b')
    out = tmp_path / 'out.pdf'
    with pikepdf.open(base) as pdf:
        attach(pdf)
        report = pdfa.save(pdf, out, '3b')
    assert report.verdict == 'pass', report.summary()
    assert validate_written(out, '3b').verdict == 'pass'
    assert_verapdf_agrees(out, '3b')


def test_pdfa_save_from_filepath(tmp_path):
    invoice = tmp_path / 'invoice.xml'
    invoice.write_bytes(b'<invoice/>')
    unknown = tmp_path / 'data.xyzzy'
    unknown.write_bytes(b'\x00\x01')
    out = tmp_path / 'out.pdf'
    with make_image_only_pdf('3') as pdf:
        pdf.attachments['invoice.xml'] = AttachedFileSpec.from_filepath(
            pdf, invoice, relationship=Name.Data
        )
        pdf.attachments['data.xyzzy'] = AttachedFileSpec.from_filepath(pdf, unknown)
        report = pdfa.save(pdf, out, '3b')
    assert report.verdict == 'pass', report.summary()
    assert report.prepared is not None
    assert report.prepared.embedded_file_subtypes_set == 1
    assert_verapdf_agrees(out, '3b')


def test_two_attachments_and_name_tree_kids(tmp_path):
    with make_image_only_pdf('3') as pdf:
        first = filespec_by_hand(pdf)
        second = filespec_by_hand(pdf, Desc=String('second file'))
        leaf = pdf.make_indirect(
            Dictionary(
                Names=Array([String('a'), first, String('b'), second]),
                Limits=Array([String('a'), String('b')]),
            )
        )
        pdf.Root.Names = Dictionary(EmbeddedFiles=Dictionary(Kids=Array([leaf])))
        pdf.Root.AF = Array([first, second])
        report = check(pdf, tmp_path)
    assert report.verdict == 'pass', report.summary()
    assert_verapdf_agrees(tmp_path / 'c.pdf', '3b')


def test_associated_file_without_name_tree(tmp_path):
    with make_image_only_pdf('3') as pdf:
        pdf.Root.AF = Array([filespec_by_hand(pdf)])
        report = check(pdf, tmp_path)
    assert report.verdict == 'pass', report.summary()
    assert_verapdf_agrees(tmp_path / 'c.pdf', '3b')


def test_empty_name_dictionary_passes(tmp_path):
    with make_image_only_pdf('3') as pdf:
        pdf.Root.Names = Dictionary()
        report = check(pdf, tmp_path)
    assert report.verdict == 'pass', report.summary()


# --- 6.8 violations -----------------------------------------------------------


def test_missing_subtype(tmp_path):
    with make_image_only_pdf('3') as pdf:
        del embedded_stream(attach(pdf)).Subtype
        report = check(pdf, tmp_path)
    assert 'ISO_19005_3:6.8-1' in rule_ids(report), report.summary()
    assert report.verdict == 'fail'
    assert_verapdf_fails(tmp_path / 'c.pdf', '3b', 'ISO_19005_3:6.8-1')


@pytest.mark.parametrize(
    'subtype', ['/xml', '/text/plain\n', '/a/b/c', '/text/pl ain', '/text/']
)
def test_invalid_mime_subtype(tmp_path, subtype):
    with make_image_only_pdf('3') as pdf:
        embedded_stream(attach(pdf)).Subtype = Name(subtype)
        report = check(pdf, tmp_path)
    assert 'ISO_19005_3:6.8-1' in rule_ids(report), report.summary()
    assert report.verdict == 'fail'
    assert_verapdf_fails(tmp_path / 'c.pdf', '3b', 'ISO_19005_3:6.8-1')


def test_subtype_not_a_name(tmp_path):
    with make_image_only_pdf('3') as pdf:
        embedded_stream(attach(pdf)).Subtype = String('text/plain')
        report = check(pdf, tmp_path)
    assert 'ISO_19005_3:6.8-1' in rule_ids(report), report.summary()


@pytest.mark.parametrize('missing', ['/F', '/UF'])
def test_missing_f_or_uf(tmp_path, missing):
    with make_image_only_pdf('3') as pdf:
        del attach(pdf)[missing]
        report = check(pdf, tmp_path)
    assert 'ISO_19005_3:6.8-2' in rule_ids(report), report.summary()
    assert report.verdict == 'fail'
    assert_verapdf_fails(tmp_path / 'c.pdf', '3b', 'ISO_19005_3:6.8-2')


def test_missing_afrelationship(tmp_path):
    with make_image_only_pdf('3') as pdf:
        del attach(pdf).AFRelationship
        report = check(pdf, tmp_path)
    assert 'ISO_19005_3:6.8-3' in rule_ids(report), report.summary()
    assert report.verdict == 'fail'
    assert_verapdf_fails(tmp_path / 'c.pdf', '3b', 'ISO_19005_3:6.8-3')


def test_afrelationship_not_a_name(tmp_path):
    with make_image_only_pdf('3') as pdf:
        attach(pdf).AFRelationship = String('Data')
        report = check(pdf, tmp_path)
    assert 'ISO_19005_3:6.8-3' in rule_ids(report), report.summary()
    assert_verapdf_fails(tmp_path / 'c.pdf', '3b', 'ISO_19005_3:6.8-3')


def test_unknown_afrelationship_unsupported(tmp_path):
    with make_image_only_pdf('3') as pdf:
        attach(pdf).AFRelationship = Name('/ABCD_Custom')
        report = check(pdf, tmp_path)
    assert report.verdict == 'not_checked', report.summary()


def test_not_associated(tmp_path):
    with make_image_only_pdf('3') as pdf:
        attach(pdf)
        del pdf.Root.AF
        report = check(pdf, tmp_path)
    assert 'ISO_19005_3:6.8-4' in rule_ids(report), report.summary()
    assert report.verdict == 'fail'
    assert_verapdf_fails(tmp_path / 'c.pdf', '3b', 'ISO_19005_3:6.8-4')


def test_one_of_two_not_associated(tmp_path):
    with make_image_only_pdf('3') as pdf:
        first = filespec_by_hand(pdf)
        second = filespec_by_hand(pdf)
        list_in_name_tree(pdf, first, second)
        pdf.Root.AF = Array([first])
        report = check(pdf, tmp_path)
    assert [f.rule for f in report.findings] == ['ISO_19005_3:6.8-4']
    assert_verapdf_fails(tmp_path / 'c.pdf', '3b', 'ISO_19005_3:6.8-4')


def test_lzw_embedded_file_denied():
    # qpdf decodes LZWDecode when saving, so check an open file
    with make_image_only_pdf('3') as pdf:
        stream = embedded_stream(attach(pdf))
        stream.write(b'\x80\x0b\x60\x50\x22\x0c\x0c\x85\x01', filter=Name.LZWDecode)
        report = _engine.run(pdf, '3b')
    assert 'ISO_19005_3:6.1.7.2-1' in rule_ids(report), report.summary()
    assert report.verdict == 'fail'


def test_external_stream_embedded_file_denied(tmp_path):
    with make_image_only_pdf('3') as pdf:
        embedded_stream(attach(pdf)).FFilter = Name.FlateDecode
        report = check(pdf, tmp_path)
    assert 'ISO_19005_3:6.1.7.1-3' in rule_ids(report), report.summary()


# --- not approved -------------------------------------------------------------


def test_external_file_specification_not_approved(tmp_path):
    with make_image_only_pdf('3') as pdf:
        external = pdf.make_indirect(
            Dictionary(
                Type=Name.Filespec,
                F=String('other.pdf'),
                UF=String('other.pdf'),
                AFRelationship=Name.Source,
            )
        )
        pdf.Root.AF = Array([external])
        report = check(pdf, tmp_path)
    assert report.verdict == 'not_checked', report.summary()


def test_string_file_specification_not_approved(tmp_path):
    with make_image_only_pdf('3') as pdf:
        pdf.Root.Names = Dictionary(
            EmbeddedFiles=Dictionary(Names=Array([String('a'), String('other.pdf')]))
        )
        report = check(pdf, tmp_path)
    assert report.verdict == 'not_checked', report.summary()


def test_direct_associated_file_not_approved(tmp_path):
    with make_image_only_pdf('3') as pdf:
        pdf.Root.AF = Array(
            [Dictionary(Type=Name.Filespec, F=String('a'), UF=String('a'))]
        )
        report = check(pdf, tmp_path)
    assert report.verdict == 'not_checked', report.summary()


def test_direct_file_specification_not_approved(tmp_path):
    with make_image_only_pdf('3') as pdf:
        filespec = filespec_by_hand(pdf)
        direct = Dictionary(dict(filespec.items()))
        pdf.Root.Names = Dictionary(
            EmbeddedFiles=Dictionary(Names=Array([String('a'), direct]))
        )
        pdf.Root.AF = Array([filespec])
        report = check(pdf, tmp_path)
    assert report.verdict != 'pass', report.summary()


@pytest.mark.parametrize(
    'key, value',
    [
        ('/Foo', Name.Bar),
        ('/RF', Dictionary()),
        ('/FS', Name.URL),
        ('/CI', Dictionary()),
        ('/DOS', String('A.TXT')),
    ],
)
def test_unknown_filespec_key_unsupported(tmp_path, key, value):
    with make_image_only_pdf('3') as pdf:
        attach(pdf)[key] = value
        report = check(pdf, tmp_path)
    assert report.verdict == 'not_checked', report.summary()
    assert 'pikepdf:schema-FileSpec' in rule_ids(report)


def test_unknown_embedded_file_key_unsupported(tmp_path):
    with make_image_only_pdf('3') as pdf:
        embedded_stream(attach(pdf)).Foo = 1
        report = check(pdf, tmp_path)
    assert report.verdict == 'not_checked', report.summary()


def test_mac_params_unsupported(tmp_path):
    with make_image_only_pdf('3') as pdf:
        embedded_stream(attach(pdf)).Params.Mac = Dictionary(Creator=String('ABCD'))
        report = check(pdf, tmp_path)
    assert report.verdict == 'not_checked', report.summary()


def test_unknown_ef_key_unsupported(tmp_path):
    with make_image_only_pdf('3') as pdf:
        filespec = attach(pdf)
        filespec.EF.DOS = filespec.EF.F
        report = check(pdf, tmp_path)
    assert report.verdict == 'not_checked', report.summary()


@pytest.mark.parametrize('key', ['/Pages', '/Foo'])
def test_other_name_dictionary_keys_unsupported(tmp_path, key):
    with make_image_only_pdf('3') as pdf:
        attach(pdf)
        pdf.Root.Names[key] = Dictionary(Names=Array())
        report = check(pdf, tmp_path)
    assert report.verdict == 'not_checked', report.summary()
    assert 'unsupported' in kinds(report)


def test_page_associated_files_unsupported(tmp_path):
    with make_image_only_pdf('3') as pdf:
        filespec = attach(pdf)
        pdf.pages[0].obj.AF = Array([filespec])
        report = check(pdf, tmp_path)
    assert report.verdict == 'not_checked', report.summary()


def test_file_attachment_annotation_not_approved(tmp_path):
    with make_image_only_pdf('3') as pdf:
        filespec = filespec_by_hand(pdf)
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
        pdf.Root.AF = Array([filespec])
        report = check(pdf, tmp_path)
    assert report.verdict != 'pass', report.summary()


@pytest.mark.parametrize('indirect', [True, False])
def test_structure_associated_files_unsupported(tmp_path, indirect):
    # A direct structure tree puts its /AF inside the catalog object, beside
    # the catalog's own /AF
    with make_image_only_pdf('3') as pdf:
        filespec = attach(pdf)
        root = Dictionary(Type=Name.StructTreeRoot, K=Dictionary(AF=Array([filespec])))
        pdf.Root.StructTreeRoot = pdf.make_indirect(root) if indirect else root
        pdf.Root.MarkInfo = Dictionary(Marked=True)
        report = check(pdf, tmp_path)
    assert report.verdict == 'not_checked', report.summary()
    assert 'pikepdf:associated-files' in rule_ids(report)


# --- other flavours -----------------------------------------------------------


def test_attachment_2b_not_approved(tmp_path):
    with make_image_only_pdf('2') as pdf:
        attach(pdf)
        report = check(pdf, tmp_path, '2')
    assert report.verdict == 'not_checked', report.summary()


def test_attachment_1b_violation(tmp_path):
    with make_image_only_pdf('1') as pdf:
        attach(pdf)
        report = check(pdf, tmp_path, '1')
    assert report.verdict == 'fail', report.summary()
    assert 'ISO_19005_1:6.1.11-2' in rule_ids(report)
    assert 'ISO_19005_1:6.1.11-1' in rule_ids(report)
    assert_verapdf_fails(tmp_path / 'c.pdf', '1b', 'ISO_19005_1:6.1.11-2')


# --- prepare ------------------------------------------------------------------


def test_prepare_repairs_attachments(tmp_path):
    with make_image_only_pdf('3') as pdf:
        filespec = attach(pdf)
        del filespec.AFRelationship
        del embedded_stream(filespec).Subtype
        del pdf.Root.AF
        result = prepare(pdf, '3b')
        assert result.embedded_file_subtypes_set == 1
        assert result.af_relationships_set == 1
        assert result.associated_files_added == 1
        assert result.changed
        text = '\n'.join(result.describe())
        assert 'application/octet-stream' in text
        assert 'AFRelationship' in text
        assert '/AF' in text
        assert embedded_stream(filespec).Subtype == Name('/application/octet-stream')
        assert filespec.AFRelationship == Name.Unspecified
        assert list(pdf.Root.AF) == [filespec]
        again = prepare(pdf, '3b')
        assert not again.changed, again
        report = check(pdf, tmp_path)
    assert report.verdict == 'pass', report.summary()
    assert_verapdf_agrees(tmp_path / 'c.pdf', '3b')


def test_prepare_appends_to_existing_af(tmp_path):
    with make_image_only_pdf('3') as pdf:
        first = filespec_by_hand(pdf)
        second = filespec_by_hand(pdf)
        leaf = pdf.make_indirect(
            Dictionary(
                Names=Array([String('a'), first, String('b'), second]),
                Limits=Array([String('a'), String('b')]),
            )
        )
        pdf.Root.Names = Dictionary(EmbeddedFiles=Dictionary(Kids=Array([leaf])))
        pdf.Root.AF = pdf.make_indirect(Array([first]))
        result = prepare(pdf, '3b')
        assert result.associated_files_added == 1
        assert [fs.objgen for fs in pdf.Root.AF] == [first.objgen, second.objgen]
        report = check(pdf, tmp_path)
    assert report.verdict == 'pass', report.summary()


@pytest.mark.parametrize('flavour', ['1b', '2b'])
def test_prepare_leaves_attachments_alone_before_part3(flavour):
    with make_image_only_pdf(flavour[0]) as pdf:
        filespec = attach(pdf)
        del filespec.AFRelationship
        del embedded_stream(filespec).Subtype
        del pdf.Root.AF
        result = prepare(pdf, flavour)
        assert result.embedded_file_subtypes_set == 0
        assert result.af_relationships_set == 0
        assert result.associated_files_added == 0
        assert '/AFRelationship' not in filespec
        assert '/Subtype' not in embedded_stream(filespec)
        assert '/AF' not in pdf.Root
