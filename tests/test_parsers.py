# SPDX-FileCopyrightText: 2022 James R. Barlow
# SPDX-License-Identifier: CC0-1.0

from __future__ import annotations

import shutil
from subprocess import PIPE, run

import pytest

import pikepdf
from pikepdf import (
    ContentStreamInlineImage,
    ContentStreamInstruction,
    Dictionary,
    Name,
    Object,
    Operator,
    Pdf,
    PdfError,
    PdfInlineImage,
    PdfMatrix,
    Stream,
    _core,
    parse_content_stream,
    unparse_content_stream,
)
from pikepdf._core import StreamParser
from pikepdf.models import PdfParsingError

# pylint: disable=useless-super-delegation,redefined-outer-name


@pytest.fixture
def graph(resources):
    yield Pdf.open(resources / 'graph.pdf')


@pytest.fixture
def inline(resources):
    yield Pdf.open(resources / 'image-mono-inline.pdf')


class PrintParser(StreamParser):
    def __init__(self):
        super().__init__()

    def handle_object(self, obj, *_args):
        print(repr(obj))

    def handle_eof(self):
        print("--EOF--")


class ExceptionParser(StreamParser):
    def __init__(self):
        super().__init__()

    def handle_object(self, obj, *_args):  # pylint: disable=unused-argument
        raise ValueError("I take exception to this")

    def handle_eof(self):
        print("--EOF--")


def slow_unparse_content_stream(instructions):
    def encode(obj):
        return _core.unparse(obj)

    def encode_iimage(iimage: PdfInlineImage):
        return iimage.unparse()

    def encode_operator(obj):
        if isinstance(obj, Operator):
            return obj.unparse()
        return encode(Operator(obj))

    def for_each_instruction():
        for n, (operands, operator) in enumerate(instructions):
            try:
                if operator == Operator(b'INLINE IMAGE'):
                    iimage = operands[0]
                    if not isinstance(iimage, PdfInlineImage):
                        raise ValueError(
                            "Operator was INLINE IMAGE but operands were not "
                            "a PdfInlineImage"
                        )
                    line = encode_iimage(iimage)
                else:
                    if operands:
                        line = b' '.join(encode(operand) for operand in operands)
                        line += b' ' + encode_operator(operator)
                    else:
                        line = encode_operator(operator)
            except (PdfError, ValueError) as e:
                raise PdfParsingError(line=n + 1) from e
            yield line

    return b'\n'.join(for_each_instruction())


def test_open_pdf(graph):
    page = graph.pages[0]
    Object._parse_stream(page.obj, PrintParser())


def test_parser_exception(graph):
    stream = graph.pages[0]['/Contents']
    with pytest.raises(ValueError):
        Object._parse_stream(stream, ExceptionParser())


@pytest.mark.skipif(shutil.which('pdftotext') is None, reason="poppler not installed")
def test_text_filter(resources, outdir):
    input_pdf = resources / 'veraPDF test suite 6-2-10-t02-pass-a.pdf'

    # Ensure the test PDF has detect we can find
    proc = run(
        ['pdftotext', str(input_pdf), '-'], check=True, stdout=PIPE, encoding='utf-8'
    )
    assert proc.stdout.strip() != '', "Need input test file that contains text"

    with Pdf.open(input_pdf) as pdf:
        page = pdf.pages[0]

        keep = []
        for operands, command in parse_content_stream(
            page, """TJ Tj ' " BT ET Td TD Tm T* Tc Tw Tz TL Tf Tr Ts"""
        ):
            if command == Operator('Tj'):
                print("skipping Tj")
                continue
            keep.append((operands, command))

        new_stream = Stream(pdf, pikepdf.unparse_content_stream(keep))
        print(new_stream.read_bytes())  # pylint: disable=no-member
        page['/Contents'] = new_stream
        page['/Rotate'] = 90

        pdf.save(outdir / 'notext.pdf', static_id=True)

    proc = run(
        ['pdftotext', str(outdir / 'notext.pdf'), '-'],
        check=True,
        stdout=PIPE,
        encoding='utf-8',
    )

    assert proc.stdout.strip() == '', "Expected text to be removed"


def test_invalid_stream_object():
    with pytest.raises(TypeError, match="must be a pikepdf.Object"):
        parse_content_stream(42)

    with pytest.raises(TypeError, match="called on page or stream"):
        parse_content_stream(Dictionary({"/Hi": 3}))

    false_page = Dictionary(Type=Name.Page, Contents=42)
    with pytest.raises(
        TypeError, match="parse_content_stream called on non-stream Object"
    ):
        parse_content_stream(false_page)


# @pytest.mark.parametrize(
#     "test_file,expected",
#     [
#         ("fourpages.pdf", True),
#         ("graph.pdf", False),
#         ("veraPDF test suite 6-2-10-t02-pass-a.pdf", True),
#         ("veraPDF test suite 6-2-3-3-t01-fail-c.pdf", False),
#         ('sandwich.pdf', True),
#     ],
# )
# def test_has_text(resources, test_file, expected):
#     with Pdf.open(resources / test_file) as pdf:
#         for p in pdf.pages:
#             page = p
#             assert page.has_text() == expected


def test_unparse_cs():
    instructions = [
        ([], Operator('q')),
        ([*PdfMatrix.identity().shorthand], Operator('cm')),
        ([], Operator('Q')),
    ]
    assert unparse_content_stream(instructions).strip() == b'q\n1 0 0 1 0 0 cm\nQ'


def test_unparse_failure():
    instructions = [([float('nan')], Operator('cm'))]
    with pytest.raises(PdfParsingError):
        unparse_content_stream(instructions)


def test_parse_xobject(resources):
    with Pdf.open(resources / 'formxobject.pdf') as pdf:
        form1 = pdf.pages[0].Resources.XObject.Form1
        instructions = parse_content_stream(form1)
        assert instructions[0][1] == Operator('cm')


def test_parse_results(inline):
    p0 = inline.pages[0]
    cmds = parse_content_stream(p0)
    assert isinstance(cmds[0], ContentStreamInstruction)
    csi = cmds[0]
    assert isinstance(csi.operands, _core._ObjectList)
    assert isinstance(csi.operator, Operator)
    assert 'Operator' in repr(csi)

    assert ContentStreamInstruction(cmds[0]).operator == cmds[0].operator

    for cmd in cmds:
        if isinstance(cmd, ContentStreamInlineImage):
            assert cmd.operator == Operator("INLINE IMAGE")
            assert isinstance(cmd.operands[0], PdfInlineImage)
            assert 'INLINE' in repr(cmd)
            assert cmd.operands[0] == cmd.iimage


def test_build_instructions():
    cs = ContentStreamInstruction([1, 0, 0, 1, 0, 0], Operator('cm'))
    assert 'cm' in repr(cs)
    assert unparse_content_stream([cs]) == b'1 0 0 1 0 0 cm'


def test_unparse_interpret_operator():
    commands = []
    matrix = [2, 0, 0, 2, 0, 0]
    commands.insert(0, (matrix, 'cm'))
    commands.insert(0, (matrix, b'cm'))
    commands.insert(0, (matrix, Operator('cm')))
    unparsed = unparse_content_stream(commands)
    assert (
        unparsed
        == b'2 0 0 2 0 0 cm\n2 0 0 2 0 0 cm\n2 0 0 2 0 0 cm'
        == slow_unparse_content_stream(commands)
    )


def test_unparse_inline(inline):
    p0 = inline.pages[0]
    cmds = parse_content_stream(p0)
    unparsed = unparse_content_stream(cmds)
    assert b'BI' in unparsed
    assert unparsed == slow_unparse_content_stream(cmds)


def test_unparse_invalid_inline_image():
    instructions = [((42,), Operator(b'INLINE IMAGE'))]

    with pytest.raises(PdfParsingError):
        unparse_content_stream(instructions)


def test_inline_copy(inline):
    for instr in parse_content_stream(inline.pages[0].Contents):
        if not isinstance(instr, ContentStreamInlineImage):
            continue
        csiimage = instr
        _copy_of_csiimage = ContentStreamInlineImage(csiimage)
        new_iimage = ContentStreamInlineImage(csiimage.iimage)
        assert unparse_content_stream([new_iimage]).startswith(b'BI')


def test_end_inline_parse():
    pdf = pikepdf.new()
    pdf.add_blank_page(page_size=(1000, 1000))
    stream = b"""
        q 200 0 0 200 500 500 cm
        BI
        /W 1
        /H 1
        /BPC 8
        /CS /RGB
        ID \x80\x80\x80
        EI Q
        q 300 0 0 300 500 200 cm
        BI
        /W 2
        /H 2
        /BPC 8
        /CS /RGB
        ID \xff\x00\x00\x00\xff\x00\x00\xff\x00\x00\x00\xff
        EI Q
        """
    pdf.pages[0].Contents = pdf.make_stream(stream)
    cs = parse_content_stream(pdf.pages[0])
    assert unparse_content_stream(cs).split() == stream.split()


class TestMalformedContentStreamInstructions:
    def test_rejects_not_list_of_pairs(self):
        with pytest.raises(PdfParsingError):
            unparse_content_stream([(1, 2, 3)])

    def test_rejects_not_castable_to_object(self):
        with pytest.raises(PdfParsingError, match="While unparsing"):
            unparse_content_stream([(['one', 'two'], 42)])  # 42 is not an operator

    def test_rejects_not_operator(self):
        with pytest.raises(PdfParsingError, match="While unparsing"):
            unparse_content_stream(
                [(['one', 'two'], Name.FortyTwo)]
            )  # Name is not an operator

    def test_rejects_inline_image_missing(self):
        with pytest.raises(PdfParsingError):
            unparse_content_stream(
                [('should be a PdfInlineImage but is not', b'INLINE IMAGE')]
            )

    def test_accepts_all_lists(self):
        unparse_content_stream([[[], b'Q']])

    def test_accepts_all_tuples(self):
        unparse_content_stream((((Name.Foo,), b'/Do'),))
