# SPDX-FileCopyrightText: 2026 James R. Barlow
# SPDX-License-Identifier: MPL-2.0

from __future__ import annotations

import pytest

pytest.importorskip('jsonschema')

import zlib
from decimal import Decimal

from pdfa_samples import (
    RESOURCES,
    assert_verapdf_fails,
    make_image_only_pdf,
    make_simple_truetype_pdf,
    save_candidate,
    save_image_only_pdf,
)

import pikepdf
from pikepdf import Array, Dictionary, Name, String
from pikepdf.pdfa import Flavour, validate
from pikepdf.pdfa._context import ValidationContext
from pikepdf.pdfa._icc import (
    IccHeader,
    check_input_profile,
    check_output_profile,
)
from pikepdf.pdfa._report import Finding, ValidationReport
from pikepdf.pdfa._schemas import SchemaSet
from pikepdf.pdfa._shallow import shallow_json, shallow_json_of_stream_dict
from pikepdf.pdfa._walker import DocumentWalker

# The OCRmyPDF output fixture carries its input's PDF/X OutputIntent (which
# the pipeline replaces), so structural tests skip it, and with it the
# images, whose device colour needs a PDF/A OutputIntent.
LATER_ROLES = frozenset({'OutputIntents', 'ImageXObject'})


def walk(pdf: pikepdf.Pdf, flavour: str = '2b', skip=frozenset()) -> ValidationReport:
    fl = Flavour(flavour)
    report = ValidationReport(fl)
    ctx = ValidationContext(fl, pdf, report)
    DocumentWalker(ctx, SchemaSet.for_flavour(fl), skip_roles=frozenset(skip)).walk()
    return report


def rule_ids(report: ValidationReport) -> set[str]:
    return {f.rule for f in report.findings}


# --- Flavour -----------------------------------------------------------------


def test_flavour_properties():
    assert Flavour('1b').part == 1
    assert Flavour('2b').spec == 'ISO_19005_2'
    assert Flavour.PDFA_3B.part == 3


# --- shallow JSON ------------------------------------------------------------


def test_shallow_scalars():
    d = pikepdf.Object.parse(b'<< /I 42 /R 1.5 /B true /N null /Nm /Foo >>')
    assert shallow_json(d) == {'/I': 42, '/R': 1.5, '/B': True, '/Nm': '/Foo'}
    assert shallow_json(Name.Foo) == '/Foo'
    assert shallow_json(Decimal('2.25')) == 2.25
    assert shallow_json(None) is None


def test_shallow_non_utf8_name():
    d = pikepdf.Object.parse(b'<< /K /\xb0\xa1\xcc\xe5 >>')
    assert shallow_json(d) == {'/K': '/#b0#a1#cc#e5'}


def test_shallow_strings():
    assert shallow_json(String('abc')) == 'u:abc'
    assert shallow_json(String(b'\xfe\xff\x00A\x00\xe9')) == 'u:A\xe9'
    assert shallow_json(String(b'\x00\x9f\xff')) == 'b:009fff'


def test_shallow_explicit_conversion():
    with pikepdf.explicit_conversion():
        d = pikepdf.Object.parse(b'<< /I 42 /R 1.5 /B false >>')
        assert shallow_json(d) == {'/I': 42, '/R': 1.5, '/B': False}


def test_shallow_indirect_and_nested():
    pdf = pikepdf.new()
    ind = pdf.make_indirect(Dictionary(X=1))
    stream = pdf.make_stream(b'abc', Foo=Name.Bar)
    arr = Array([ind, 1, Dictionary(Y=ind), Array([Name.Z])])
    num, gen = ind.objgen
    ref = f'{num} {gen} R'
    assert shallow_json(ind) == ref
    assert shallow_json(arr) == [ref, 1, {'/Y': ref}, ['/Z']]
    snum, sgen = stream.objgen
    assert shallow_json(stream) == f'{snum} {sgen} R'
    assert shallow_json_of_stream_dict(stream) == {'/Foo': '/Bar'}


# --- end-to-end on synthetic image-only files ---------------------------------


@pytest.mark.parametrize('flavour, part', [('2b', '2'), ('3b', '3'), ('1b', '1')])
def test_image_only_pdf_validates(tmp_path, flavour, part):
    path = save_image_only_pdf(tmp_path / 'img.pdf', part)
    report = validate(path, flavour)
    assert report.passed, report.summary()
    assert report.findings == []


def test_image_only_pdf_1b_rejects_xref_stream(tmp_path):
    path = save_image_only_pdf(tmp_path / 'img.pdf', '1', object_streams=True)
    report = validate(path, Flavour.PDFA_1B)
    assert not report.passed
    assert 'ISO_19005_1:6.1.4-3' in rule_ids(report)


def test_image_only_pdf_rejects_javascript_names(tmp_path):
    def add_js(pdf):
        js = pdf.make_indirect(
            Dictionary(S=Name.JavaScript, JS=String('app.alert("hi")'))
        )
        pdf.Root.Names = Dictionary(
            JavaScript=Dictionary(Names=Array([String('a'), js]))
        )

    report = validate(save_image_only_pdf(tmp_path / 'js.pdf', '2', add_js), '2b')
    assert not report.passed
    assert any('/Names' in f.where or '/Names' in f.message for f in report.findings)


def test_image_only_pdf_rejects_ocproperties(tmp_path):
    def add_oc(pdf):
        ocg = pdf.make_indirect(Dictionary(Type=Name.OCG, Name=String('Layer')))
        pdf.Root.OCProperties = Dictionary(
            OCGs=Array([ocg]), D=Dictionary(Order=Array([ocg]))
        )

    report = validate(save_image_only_pdf(tmp_path / 'oc.pdf', '2', add_oc), '2b')
    assert not report.passed
    report1 = validate(save_image_only_pdf(tmp_path / 'oc1.pdf', '1', add_oc), '1b')
    assert 'ISO_19005_1:6.1.13-1' in rule_ids(report1)


def test_validate_never_raises(tmp_path):
    bad = tmp_path / 'bad.pdf'
    bad.write_bytes(b'not a pdf')
    report = validate(bad, '2b')
    assert not report.passed
    assert report.findings[0].rule == 'pikepdf:internal'
    assert report.findings[0].kind == 'unsupported'


def test_encrypted_is_denied(tmp_path):
    path = tmp_path / 'enc.pdf'
    with make_image_only_pdf() as pdf:
        pdf.save(path, encryption=pikepdf.Encryption(owner='a', user=''))
    report = validate(path, '2b')
    assert 'ISO_19005_2:6.1.3-2' in rule_ids(report)


def test_pdf_version_too_new_for_1b(tmp_path):
    path = tmp_path / 'v15.pdf'
    with make_image_only_pdf('1') as pdf:
        pdf.save(
            path,
            min_version='1.5',
            object_stream_mode=pikepdf.ObjectStreamMode.disable,
        )
    report = validate(path, '1b')
    assert not report.passed


# --- structural mutations (walker on in-memory PDFs) ------------------------


def test_walker_approves_image_only_in_memory():
    with make_image_only_pdf() as pdf:
        assert walk(pdf).findings == []


def test_catalog_aa_denied():
    with make_image_only_pdf() as pdf:
        pdf.Root.AA = Dictionary()
        assert 'ISO_19005_2:6.5.2-1' in rule_ids(walk(pdf))
    with make_image_only_pdf('1') as pdf:
        pdf.Root.AA = Dictionary()
        assert 'ISO_19005_1:6.6.2-3' in rule_ids(walk(pdf, '1b'))


def test_trailer_missing_id_denied():
    with make_image_only_pdf() as pdf:
        if '/ID' in pdf.trailer:
            del pdf.trailer['/ID']
        assert 'ISO_19005_2:6.1.3-1' in rule_ids(walk(pdf))


def test_trailer_encrypt_key_denied():
    with make_image_only_pdf() as pdf:
        pdf.trailer.ID = Array([String(b'1' * 16), String(b'1' * 16)])
        pdf.trailer.Encrypt = Dictionary()
        assert 'ISO_19005_2:6.1.3-2' in rule_ids(walk(pdf))


def test_catalog_unknown_key_denied():
    with make_image_only_pdf() as pdf:
        pdf.Root.Foo = 1
        report = walk(pdf)
        assert not report.passed
        assert any('/Foo' in f.message for f in report.findings)
        assert all(f.rule == 'pikepdf:schema-Catalog' for f in report.findings)


def test_page_aa_and_unknown_key_denied():
    with make_image_only_pdf() as pdf:
        pdf.pages[0].obj.AA = Dictionary()
        assert 'ISO_19005_2:6.5.2-2' in rule_ids(walk(pdf))
    with make_image_only_pdf() as pdf:
        pdf.pages[0].obj.Foo = 1
        assert not walk(pdf).passed


def test_page_group_denied_in_1b():
    def group():
        return Dictionary(Type=Name.Group, S=Name.Transparency, CS=Name.DeviceRGB)

    with make_image_only_pdf() as pdf:
        pdf.pages[0].obj.Group = group()
        assert walk(pdf).passed
    with make_image_only_pdf('1') as pdf:
        pdf.pages[0].obj.Group = group()
        assert 'ISO_19005_1:6.4-3' in rule_ids(walk(pdf, '1b'))


@pytest.mark.parametrize('box', [[0, 0, 2, 792], [0, 0, 612, 14401], [0, 0, 612, -1]])
def test_page_box_size_denied(box):
    with make_image_only_pdf() as pdf:
        pdf.pages[0].obj.MediaBox = Array(box)
        assert 'ISO_19005_2:6.1.13-11' in rule_ids(walk(pdf))


def test_inherited_mediabox_accepted():
    with make_image_only_pdf() as pdf:
        pdf.Root.Pages.MediaBox = pdf.pages[0].obj.MediaBox
        del pdf.pages[0].obj['/MediaBox']
        assert walk(pdf).passed


def test_missing_mediabox_denied():
    with make_image_only_pdf() as pdf:
        del pdf.pages[0].obj['/MediaBox']
        assert not walk(pdf).passed


def test_image_interpolate_denied():
    with make_image_only_pdf() as pdf:
        pdf.pages[0].Resources.XObject.Im0.Interpolate = True
        assert 'ISO_19005_2:6.2.8-3' in rule_ids(walk(pdf))


def test_image_lzw_denied():
    with make_image_only_pdf() as pdf:
        pdf.pages[0].Resources.XObject.Im0.Filter = Name.LZWDecode
        assert 'ISO_19005_2:6.1.7.2-1' in rule_ids(walk(pdf))


def test_image_jpx_unsupported():
    with make_image_only_pdf() as pdf:
        pdf.pages[0].Resources.XObject.Im0.Filter = Name.JPXDecode
        report = walk(pdf)
        assert not report.passed
        assert {f.kind for f in report.findings} == {'unsupported'}


def test_image_devicecmyk_without_cmyk_intent_denied():
    with make_image_only_pdf() as pdf:
        pdf.pages[0].Resources.XObject.Im0.ColorSpace = Name.DeviceCMYK
        assert 'ISO_19005_2:6.2.4.3-3' in rule_ids(walk(pdf))


def test_image_bpc16_denied_in_1b_only():
    with make_image_only_pdf() as pdf:
        pdf.pages[0].Resources.XObject.Im0.BitsPerComponent = 16
        assert walk(pdf).passed
    with make_image_only_pdf('1') as pdf:
        pdf.pages[0].Resources.XObject.Im0.BitsPerComponent = 16
        assert 'ISO_19005_1:6.2.4-4' in rule_ids(walk(pdf, '1b'))


def test_image_smask_denied_in_1b_only():
    def add_smask(pdf):
        smask = pdf.make_stream(
            zlib.compress(bytes(64)),
            Type=Name.XObject,
            Subtype=Name.Image,
            Width=8,
            Height=8,
            ColorSpace=Name.DeviceGray,
            BitsPerComponent=8,
            Filter=Name.FlateDecode,
        )
        pdf.pages[0].Resources.XObject.Im0.SMask = smask

    with make_image_only_pdf() as pdf:
        add_smask(pdf)
        assert walk(pdf).passed
    with make_image_only_pdf('1') as pdf:
        add_smask(pdf)
        assert 'ISO_19005_1:6.4-2' in rule_ids(walk(pdf, '1b'))


def test_placeholder_roles_are_unsupported():
    with make_image_only_pdf() as pdf:
        pdf.pages[0].Resources.Properties = Dictionary(P0=Dictionary(A=1))
        report = walk(pdf)
        assert not report.passed
        assert {f.kind for f in report.findings} == {'unsupported'}
        assert walk(pdf, skip={'Properties'}).passed


def test_nonembedded_standard_font_is_unsupported():
    with make_image_only_pdf() as pdf:
        pdf.pages[0].Resources.Font = Dictionary(
            F1=Dictionary(Type=Name.Font, Subtype=Name.Type1, BaseFont=Name.Helvetica)
        )
        report = walk(pdf)
        assert not report.passed
        assert {f.kind for f in report.findings} == {'unsupported'}
        assert walk(pdf, skip={'Font'}).passed


def test_output_intent_non_pdfa_unsupported():
    with make_image_only_pdf() as pdf:
        pdf.Root.OutputIntents[0].S = Name.GTS_PDFX
        report = walk(pdf)
        assert not report.passed


def test_output_intents_differing_profiles_denied():
    with make_image_only_pdf() as pdf:
        intent = pdf.Root.OutputIntents[0]
        profile = intent.DestOutputProfile
        other = pdf.make_stream(profile.read_bytes(), N=3)
        second = Dictionary(
            Type=Name.OutputIntent,
            S=Name.GTS_PDFA1,
            OutputConditionIdentifier=String('sRGB'),
            DestOutputProfile=other,
        )
        pdf.Root.OutputIntents.append(pdf.make_indirect(second))
        assert 'ISO_19005_2:6.2.3-2' in rule_ids(walk(pdf))


def test_missing_output_intent_denied():
    with make_image_only_pdf() as pdf:
        del pdf.Root['/OutputIntents']
        assert not walk(pdf).passed


def test_outlines_and_actions():
    with make_image_only_pdf() as pdf:
        page = pdf.pages[0].obj
        outlines = pdf.make_indirect(Dictionary(Type=Name.Outlines, Count=2))
        first = pdf.make_indirect(
            Dictionary(
                Title=String('One'), Parent=outlines, Dest=Array([page, Name.Fit])
            )
        )
        second = pdf.make_indirect(
            Dictionary(
                Title=String('Two'),
                Parent=outlines,
                Prev=first,
                A=Dictionary(S=Name.URI, URI=String('https://example.com')),
            )
        )
        first.Next = second
        outlines.First = first
        outlines.Last = second
        pdf.Root.Outlines = outlines
        assert walk(pdf).passed

        second.A = Dictionary(S=Name.JavaScript, JS=String('x'))
        assert 'ISO_19005_2:6.5.1-1' in rule_ids(walk(pdf))

        second.A = Dictionary(S=Name.Named, N=Name.Print)
        assert 'ISO_19005_2:6.5.1-2' in rule_ids(walk(pdf))


def test_long_outline_sibling_chain_not_depth_limited():
    with make_image_only_pdf() as pdf:
        outlines = pdf.make_indirect(Dictionary(Type=Name.Outlines))
        prev = None
        for n in range(200):
            item = pdf.make_indirect(Dictionary(Title=String(f'{n}'), Parent=outlines))
            if prev is None:
                outlines.First = item
            else:
                prev.Next = item
                item.Prev = prev
            prev = item
        outlines.Last = prev
        pdf.Root.Outlines = outlines
        assert walk(pdf).passed


def test_page_labels():
    with make_image_only_pdf() as pdf:
        pdf.Root.PageLabels = Dictionary(
            Nums=Array([0, Dictionary(S=Name.r, P=String('p'), St=1)])
        )
        assert walk(pdf).passed
        pdf.Root.PageLabels = Dictionary(Nums=Array([0, Dictionary(S=Name.X)]))
        assert not walk(pdf).passed


def test_page_tree_cycle_terminates():
    with make_image_only_pdf() as pdf:
        pages = pdf.Root.Pages
        pages.Kids.append(pages)
        pages.Count = 2
        report = walk(pdf)
        assert 'pikepdf:role-conflict' in rule_ids(report)


def test_deep_page_tree_denied_as_unsupported():
    with make_image_only_pdf() as pdf:
        root = pdf.Root.Pages
        page = root.Kids[0]
        parent = root
        for _ in range(70):
            node = pdf.make_indirect(
                Dictionary(Type=Name.Pages, Kids=Array(), Count=1, Parent=parent)
            )
            parent.Kids = Array([node])
            parent = node
        parent.Kids = Array([page])
        page.Parent = parent
        report = walk(pdf)
        assert 'pikepdf:depth' in rule_ids(report)
        assert {f.kind for f in report.findings} == {'unsupported'}


def test_object_in_two_roles_denied():
    with make_image_only_pdf() as pdf:
        # The ICC profile stream reused as a content stream
        profile = pdf.Root.OutputIntents[0].DestOutputProfile
        pdf.pages[0].obj.Contents = profile
        assert not walk(pdf).passed


# --- ICC --------------------------------------------------------------------


def _header(device_class=b'mntr', colour_space=b'RGB ', major=2) -> bytes:
    data = bytearray(128)
    data[0:4] = (3144).to_bytes(4, 'big')
    data[8] = major
    data[12:16] = device_class
    data[16:20] = colour_space
    return bytes(data)


def _ctx(flavour: str) -> ValidationContext:
    fl = Flavour(flavour)
    return ValidationContext(fl, pikepdf.new(), ValidationReport(fl))


def test_icc_header_parse():
    header = IccHeader.parse(_header())
    assert header.version_major == 2
    assert header.device_class == 'mntr'
    assert header.colour_space == 'RGB '
    with pytest.raises(ValueError):
        IccHeader.parse(b'short')


@pytest.mark.parametrize(
    'flavour, header, ok',
    [
        ('2b', _header(), True),
        ('2b', _header(b'scnr'), False),
        ('2b', _header(colour_space=b'Lab '), False),
        ('2b', _header(major=4), True),
        ('2b', _header(major=5), False),
        ('1b', _header(major=4), False),
        ('1b', _header(major=2), True),
    ],
)
def test_check_output_profile(flavour, header, ok):
    ctx = _ctx(flavour)
    check_output_profile(IccHeader.parse(header), ctx.flavour, ctx, 'here')
    assert ctx.report.passed == ok


@pytest.mark.parametrize(
    'header, n, ok',
    [
        (_header(b'scnr'), 3, True),
        (_header(b'spac', b'GRAY'), 1, True),
        (_header(b'spac', b'GRAY'), 3, False),
        (_header(b'abst'), 3, False),
        (_header(b'mntr', b'Lab '), 3, True),
        (_header(b'mntr', b'CMYK'), 4, True),
    ],
)
def test_check_input_profile(header, n, ok):
    ctx = _ctx('2b')
    check_input_profile(IccHeader.parse(header), n, ctx.flavour, ctx, 'here')
    assert ctx.report.passed == ok


def test_report_summary():
    report = ValidationReport(Flavour.PDFA_2B)
    assert report.passed
    assert 'pass' in report.summary().lower()
    report.findings.append(Finding('x', 'obj 1 0', 'bad', 'violation'))
    assert not report.passed
    assert 'x' in report.summary()


# --- OCRmyPDF output --------------------------------------------------------


@pytest.fixture(scope='module')
def ocrmypdf_output():
    # OCRmyPDF's output for francais.pdf with the fpdf2 renderer
    return RESOURCES / 'francais_ocr_fpdf2.pdf'


def test_ocrmypdf_output_structure_approved(ocrmypdf_output):
    with pikepdf.open(ocrmypdf_output) as pdf:
        report = walk(pdf, skip=LATER_ROLES)
        assert report.passed, report.summary()


@pytest.mark.parametrize(
    'mutation, rule',
    [
        (lambda pdf: pdf.Root.__setattr__('AA', Dictionary()), 'ISO_19005_2:6.5.2-1'),
        (lambda pdf: pdf.trailer.__delitem__('/ID'), 'ISO_19005_2:6.1.3-1'),
        (
            lambda pdf: pdf.trailer.__setitem__('/Encrypt', Dictionary()),
            'ISO_19005_2:6.1.3-2',
        ),
        (lambda pdf: pdf.Root.__setattr__('Foo', 1), 'pikepdf:schema-Catalog'),
        (
            lambda pdf: pdf.pages[0].obj.__setattr__('PresSteps', Dictionary()),
            'ISO_19005_2:6.10-2',
        ),
    ],
)
def test_ocrmypdf_output_mutations_denied(ocrmypdf_output, mutation, rule):
    with pikepdf.open(ocrmypdf_output) as pdf:
        mutation(pdf)
        assert rule in rule_ids(walk(pdf, skip=LATER_ROLES))


@pytest.mark.parametrize(
    'part, subtype, rule',
    [
        ('2', '/Foo', 'ISO_19005_2:6.2.11.2-7'),
        ('1', '/Foo', 'ISO_19005_1:6.3.2-7'),
        ('1', '/OpenType', 'ISO_19005_1:6.3.2-7'),
    ],
)
def test_font_file_subtype_denied(tmp_path, part, subtype, rule):
    with make_simple_truetype_pdf(part) as pdf:
        font = pdf.pages[0].Resources.Font.F1
        font.FontDescriptor.FontFile2.Subtype = Name(subtype)
        path = save_candidate(pdf, tmp_path / 'c.pdf', part)
    assert rule in rule_ids(validate(path, f'{part}b'))
    assert_verapdf_fails(path, f'{part}b', rule)


def _two_level_page_tree(pdf: pikepdf.Pdf) -> pikepdf.Dictionary:
    """Move the page under an intermediate Pages node and return that node."""
    root = pdf.Root.Pages
    page = root.Kids[0]
    node = pdf.make_indirect(
        Dictionary(Type=Name.Pages, Kids=Array([page]), Count=1, Parent=root)
    )
    page.Parent = node
    root.Kids = Array([node])
    return node


@pytest.mark.parametrize(
    'mutate',
    [
        lambda pdf: setattr(pdf.Root.Pages, 'Count', 2),
        lambda pdf: setattr(pdf.Root.Pages, 'Count', 0),
        lambda pdf: pdf.Root.Pages.__delitem__('/Count'),
        lambda pdf: setattr(pdf.Root.Pages, 'Count', Decimal('1.0')),
        lambda pdf: setattr(_two_level_page_tree(pdf), 'Count', 2),
        lambda pdf: pdf.pages.__delitem__(0),
    ],
    ids=['too-many', 'too-few', 'missing', 'real', 'inner-node', 'no-pages'],
)
def test_page_tree_count_denied(mutate):
    # Checked in memory: pikepdf corrects /Count when it saves
    with make_image_only_pdf('2') as pdf:
        mutate(pdf)
        report = walk(pdf)
    assert 'pikepdf:page-tree' in rule_ids(report), report.summary()


def test_two_level_page_tree_approved(tmp_path):
    path = save_image_only_pdf(tmp_path / 'c.pdf', '2', _two_level_page_tree)
    report = validate(path, '2b')
    assert report.passed, report.summary()
