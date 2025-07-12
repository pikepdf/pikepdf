# SPDX-FileCopyrightText: 2022 James R. Barlow
# SPDX-License-Identifier: CC0-1.0

from __future__ import annotations

from decimal import Decimal

import pytest
from PIL import Image

from pikepdf import Matrix, Pdf
from pikepdf.canvas import (
    BLACK,
    Canvas,
    Color,
    ContentStreamBuilder,
    Helvetica,
    SimpleFont,
    Text,
    TextDirection,
)
from pikepdf.objects import Name, Operator


@pytest.fixture
def pdf(request, resources):
    with Pdf.open(resources / request.param) as pdf:
        yield pdf


@pytest.fixture
def resource_dict(request, pdf):
    if request.param == 'form':
        return pdf.Root.AcroForm.DR
    else:
        return pdf.pages[0].Resources


@pytest.fixture
def simplefont(request, resource_dict):
    return SimpleFont.load(request.param, resource_dict)


FONTS = {
    # TODO These are all TrueType fonts using the WinAnsiEncoding. Would be good to find
    # other examples. Having trouble finding other example PDFs with fonts that would be
    # supported by our current limited implementation. All the Type1 fonts I see reference
    # built-in fonts with no widths, or have difference maps, and MacRoman doesn't seem to
    # really exist in the wild anymore as far as I can tell.
    'arial-truetype-winansi': ('form_dd0293.pdf', 'form', Name('/ArialMT')),
    'arialbold-truetype-winansi': ('form_dd0293.pdf', 'form', Name('/Arial-BoldMT')),
    'times-truetype-winansi': ('form_dd0293.pdf', 'form', Name('/TimesNewRomanPSMT')),
}


class TestSimpleFont:
    @pytest.mark.parametrize(
        'pdf,resource_dict,name',
        [
            FONTS['arial-truetype-winansi'],
            FONTS['arialbold-truetype-winansi'],
            FONTS['times-truetype-winansi'],
        ],
        indirect=['pdf', 'resource_dict'],
    )
    def test_load(self, pdf, resource_dict, name):
        font = SimpleFont.load(name, resource_dict)
        assert font.data == resource_dict.Font[name]

    @pytest.mark.parametrize(
        'pdf,resource_dict,simplefont,char_code,expected_width',
        [
            (*FONTS['arial-truetype-winansi'], ord('a'), 556),
            (*FONTS['arialbold-truetype-winansi'], b'a', 556),
            (*FONTS['times-truetype-winansi'], 'a', 444),
        ],
        indirect=['pdf', 'resource_dict', 'simplefont'],
    )
    def test_unscaled_char_width_known(
        self, pdf, resource_dict, simplefont, char_code, expected_width
    ):
        width = simplefont.unscaled_char_width(char_code)
        assert width == expected_width

    @pytest.mark.parametrize(
        'pdf,resource_dict,simplefont',
        [
            FONTS['arial-truetype-winansi'],
            FONTS['arialbold-truetype-winansi'],
            FONTS['times-truetype-winansi'],
        ],
        indirect=True,
    )
    @pytest.mark.parametrize(
        'font_size,width,expected',
        [
            (1, 1000, 1),
            (12, 500, 6),
        ],
    )
    def test_convert_width(
        self, pdf, resource_dict, simplefont, font_size, width, expected
    ):
        assert simplefont.convert_width(width, font_size) == expected

    @pytest.mark.parametrize(
        'pdf,resource_dict,simplefont,string,encoded',
        [
            (
                *FONTS['arial-truetype-winansi'],
                "This is just ASCII!",
                b"This is just ASCII!",
            ),
            (
                *FONTS['times-truetype-winansi'],
                # Sentence constructed in a deliberate attempt to use multiple different
                # non-ascii latin characters, don't read too much into it. I assure you my
                # grandmother and I are fine.
                "«Disparaître avec ma grand-mère française aiguë à l'hôpital dégoûtant cet été»",
                b"\253Dispara\356tre avec ma grand-m\350re fran\347aise aigu\353 \340 l'h\364pital d\351go\373tant cet \351t\351\273",
            ),
        ],
        indirect=['pdf', 'resource_dict', 'simplefont'],
    )
    def test_unscaled_char_width_known2(
        self, pdf, resource_dict, simplefont, string, encoded
    ):
        assert simplefont.encode(string) == encoded


class TestContentStreamBuilder:
    def test_init(self):
        builder = ContentStreamBuilder()
        assert isinstance(builder.build(), bytes)

    def test_append(self):
        builder = ContentStreamBuilder()
        builder.push()
        assert builder.build() == b'q\n'

    def test_extend(self):
        builder1 = ContentStreamBuilder()
        builder2 = ContentStreamBuilder()
        builder2.push()
        builder1.extend(builder2)
        assert builder1.build() == b'q\n'

    @pytest.mark.parametrize(
        'method,args,operator',
        [
            (ContentStreamBuilder.push, (), 'q'),
            (ContentStreamBuilder.pop, (), 'Q'),
            (ContentStreamBuilder.cm, (Matrix(),), 'cm'),
            (
                ContentStreamBuilder.begin_marked_content_proplist,
                (Name.Test, 42),
                'BDC',
            ),
            (ContentStreamBuilder.end_marked_content, (), 'EMC'),
            (ContentStreamBuilder.begin_marked_content, (Name.Foo,), 'BMC'),
            (ContentStreamBuilder.begin_text, (), 'BT'),
            (ContentStreamBuilder.end_text, (), 'ET'),
            (ContentStreamBuilder.set_text_font, (Name.Test, 12), 'Tf'),
            (ContentStreamBuilder.set_text_font, (Name.Test, 12.5), 'Tf'),
            (ContentStreamBuilder.set_text_font, (Name.Test, Decimal('12.5')), 'Tf'),
            (ContentStreamBuilder.set_text_char_spacing, (1,), 'Tc'),
            (ContentStreamBuilder.set_text_char_spacing, (0.5,), 'Tc'),
            (ContentStreamBuilder.set_text_char_spacing, (Decimal('1'),), 'Tc'),
            (ContentStreamBuilder.set_text_word_spacing, (1,), 'Tw'),
            (ContentStreamBuilder.set_text_word_spacing, (0.5,), 'Tw'),
            (ContentStreamBuilder.set_text_word_spacing, (Decimal('1'),), 'Tw'),
            (ContentStreamBuilder.set_text_leading, (13,), 'TL'),
            (ContentStreamBuilder.set_text_leading, (13.5,), 'TL'),
            (ContentStreamBuilder.set_text_leading, (Decimal('13.5'),), 'TL'),
            (ContentStreamBuilder.set_text_matrix, (Matrix(),), "Tm"),
            (ContentStreamBuilder.set_text_rendering, (3,), "Tr"),
            (ContentStreamBuilder.set_text_horizontal_scaling, (100.0,), "Tz"),
            (
                ContentStreamBuilder.show_text_with_kerning,
                (b'A', 120, b'W', 120, b'A', 95, b'Y'),
                "TJ",
            ),
            (ContentStreamBuilder.show_text_line, (b'hello world',), "'"),
            (
                ContentStreamBuilder.show_text_line_with_spacing,
                (b'hello world', 0.25, 0.25),
                '"',
            ),
            (ContentStreamBuilder.move_cursor, (1, 2), "Td"),
            (ContentStreamBuilder.move_cursor_new_line, (), "T*"),
            (ContentStreamBuilder.stroke_and_close, (), "s"),
            (ContentStreamBuilder.fill, (), "f"),
            (ContentStreamBuilder.append_rectangle, (10, 10, 40, 40), "re"),
            (ContentStreamBuilder.set_stroke_color, (1, 0, 1), "RG"),
            (ContentStreamBuilder.set_fill_color, (0, 1, 0), "rg"),
            (ContentStreamBuilder.set_line_width, (5,), "w"),
            (ContentStreamBuilder.line, (1, 2, 3, 4), "l"),
            (ContentStreamBuilder.set_dashes, (), "d"),
            (ContentStreamBuilder.set_dashes, (1,), "d"),
            (ContentStreamBuilder.set_dashes, ([1, 2], 1), "d"),
            (ContentStreamBuilder.draw_xobject, (Name.X,), "Do"),
        ],
    )
    def test_operators(self, method, operator, args):
        builder = ContentStreamBuilder()
        method(builder, *args)
        assert builder.build().endswith(Operator(operator).unparse() + b'\n')


class TestCanvas:
    def test_basic(self):
        canvas = Canvas(page_size=(100, 100))
        assert canvas.page_size == (100, 100)
        with canvas.do.save_state(cm=Matrix().scaled(2, 2)):
            canvas.do.stroke_color(Color(1, 0, 0, 1)).line_width(2).dashes(1, 1).line(
                0, 0, 10, 10
            )
            canvas.do.fill_color(Color(0, 1, 0, 1)).rect(
                10, 10, 10, 10, fill=False
            ).rect(10, 10, 5, 5, fill=True)
        pdf = canvas.to_pdf()
        assert len(pdf.pages) == 1
        pdf.check_pdf_syntax()

    def test_image(self, resources):
        canvas = Canvas(page_size=(400, 100))
        canvas.do.draw_image(resources / 'pink-palette-icc.png', 0, 0, 100, 100)
        im = Image.open(resources / 'pink-palette-icc.png')
        canvas.do.draw_image(im.convert('1'), 100, 0, 100, 100)
        canvas.do.draw_image(im.convert('L'), 200, 0, 100, 100)
        canvas.do.draw_image(im.convert('RGB'), 300, 0, 100, 100)

        pdf = canvas.to_pdf()
        pdf.check_pdf_syntax()

    def test_text(self):
        hello_msg = 'Hello, World!'
        hello_arabic = 'مرحبا بالعالم'
        canvas = Canvas(page_size=(100, 100))

        text = Text()
        text.font(Name.Helvetica, 12).render_mode(1).text_transform(
            Matrix().translated(10, 10)
        ).horiz_scale(110).move_cursor(10, 10).show(hello_msg)

        # This is cheating! We're using one of the 14 base PDF fonts for a quick
        # test. If the resulting PDF is viewed, the result will not be in Arabic.
        # This does not properly register the font. The point of this test is
        # to ensure that the content stream is properly encoded.
        rtltext = Text(TextDirection.RTL)
        rtltext.font(Name.Helvetica, 12).render_mode(0).text_transform(
            Matrix().translated(10, 10)
        ).move_cursor(50, 50).show(hello_arabic)

        canvas.do.stroke_color(BLACK).draw_text(text)
        canvas.do.fill_color(BLACK).draw_text(rtltext)
        canvas.add_font(Name.Helvetica, Helvetica())
        pdf = canvas.to_pdf()
        pdf.check_pdf_syntax()

        for msg in [hello_msg, hello_arabic]:
            # str -> UTF-16 big endian bytes -> hex encoded str -> hex bytes
            hex_bytes = msg.encode('utf-16be').hex().encode('ascii')
            assert hex_bytes in pdf.pages[0].Contents.read_bytes()

    def test_stack_abuse(self, caplog):
        canvas = Canvas(page_size=(100, 100))
        canvas.do.pop().pop()
        canvas.to_pdf()
        assert "Graphics state stack is not empty when page saved" in caplog.text
