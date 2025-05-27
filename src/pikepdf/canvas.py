# SPDX-FileCopyrightText: 2023 James R. Barlow
# SPDX-License-Identifier: MPL-2.0

"""Module for generating PDF content streams."""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from collections import namedtuple
from contextlib import contextmanager
from dataclasses import dataclass
from decimal import Decimal
from enum import Enum
from io import BytesIO
from pathlib import Path

from PIL import Image

from pikepdf._core import ContentStreamInstruction, Matrix, Pdf
from pikepdf._data import CHARNAMES_TO_UNICODE
from pikepdf.models import unparse_content_stream
from pikepdf.objects import Array, Dictionary, Name, Operator, String

log = logging.getLogger(__name__)


Color = namedtuple('Color', ['red', 'green', 'blue', 'alpha'])

BLACK = Color(0, 0, 0, 1)
WHITE = Color(1, 1, 1, 1)
BLUE = Color(0, 0, 1, 1)
CYAN = Color(0, 1, 1, 1)
GREEN = Color(0, 1, 0, 1)
DARKGREEN = Color(0, 0.5, 0, 1)
MAGENTA = Color(1, 0, 1, 1)
RED = Color(1, 0, 0, 1)


class TextDirection(Enum):
    """Enumeration for text direction."""

    LTR = 1
    """Left to right, the default."""
    RTL = 2
    """Right to left, Arabic, Hebrew, Persian, etc."""


class Font(ABC):
    """Base class for fonts."""

    @abstractmethod
    def text_width(
        self, text: str | bytes, fontsize: float | int | Decimal
    ) -> float | int | Decimal:
        """Estimate the width of a text string when rendered with the given font."""

    @abstractmethod
    def register(self, pdf: Pdf) -> Dictionary:
        """Register the font.

        Create several data structures in the Pdf to describe the font.

        After registering the font, the returned object should be added to the
        /Resources dictionary of any page or Form XObject that uses the font. For
        example one might write:

        ```python
        page.Resources.Font[Name.Arial] = font.register(pdf)
        ```

        The same object can be used for multiple pages or Form XObjects, since it is
        an indirect object.

        Returns a Dictionary suitable for insertion into a /Resources /Font dictionary.
        """


class DimensionedFont(Font):
    """Base class for fonts that have dimensional information.

    Specifically, these fonts can provide leading and ascent/descent values, and
    encode strings to the encoding used by the font.

    .. versionadded:: 9.8.1
    """

    @property
    @abstractmethod
    def leading(self) -> Decimal | int:
        """Default leading (line spacing) value for this font; 0 if not applicable."""

    @property
    @abstractmethod
    def ascent(self) -> Decimal | int | None:
        """The max height of the font above the baseline."""

    @property
    @abstractmethod
    def descent(self) -> Decimal | int | None:
        """The max height of the font below the baseline."""

    @abstractmethod
    def encode(self, text: str) -> bytes:
        """Encode a string in the encoding used by this font."""


class Helvetica(Font):
    """Helvetica font.

    Helvetica is one of the 14 PDF standard fonts that can typically be counted on being
    present even if not embedded in the PDF document. However, starting with PDF 2.0,
    PDF processors are no longer guaranteed to have these fonts. See 9.6.2.2.
    """

    def text_width(
        self, text: str | bytes, fontsize: float | int | Decimal
    ) -> float | int | Decimal:
        """Estimate the width of a text string when rendered with the given font."""
        raise NotImplementedError()

    def register(self, pdf: Pdf) -> Dictionary:
        """Register the font."""
        return pdf.make_indirect(
            Dictionary(
                BaseFont=Name.Helvetica,
                Type=Name.Font,
                Subtype=Name.Type1,
            )
        )


class SimpleFont(DimensionedFont):
    """Font implementation designed to work with Type 1 Fonts and TrueType fonts.

    As described in section 9.6 of the PDF spec.

    See also section 9.8: Font Descriptors.

    The PDF spec also considers Type3 fonts to be "Simple Fonts", but Type3 fonts are
    not implemented here.
    """

    data: Dictionary

    _diffmap_cache = None

    def __init__(self, data: Dictionary):
        """Create a SimpleFont instance from a font resource dictionary."""
        if Name.Subtype not in data or data.Subtype not in (
            Name.Type1,
            Name.MMType1,
            Name.TrueType,
        ):
            raise ValueError(
                'Font resource dictionary does not describe a Type1 or TrueType font:',
                data,
            )
        self.data = data

    @classmethod
    def load(cls, name: Name, resource_dict: Dictionary) -> SimpleFont:
        """Load a font from the specified resource dictionary."""
        if name not in resource_dict.Font:
            raise LookupError(
                f'Cannot find font information for {name} '
                f'(Available fonts: {", ".join(resource_dict.Font.keys())})'
            )
        font_data = resource_dict.Font[name]
        if not isinstance(font_data, Dictionary):
            raise TypeError(
                f'Font data for {name} is not a dictionary, but a {type(font_data)}'
            )
        return cls(font_data)

    def register(self, pdf: Pdf) -> Dictionary:
        """Register the font."""
        return pdf.make_indirect(self.data)

    @property
    def leading(self) -> int | Decimal:
        """Returns leading for a SimpleFont."""
        if Name.Leading in self.data.FontDescriptor:
            return self.data.FontDescriptor.Leading
        else:
            return 0

    @property
    def ascent(self) -> Decimal:
        """Returns ascent for a SimpleFont."""
        # Required for all byt type 3 fonts, so should be present
        return self.data.FontDescriptor.Ascent

    @property
    def descent(self) -> Decimal:
        """Returns descent for a SimpleFont."""
        # Required for all byt type 3 fonts, so should be present
        return self.data.FontDescriptor.Descent

    def unscaled_char_width(self, char: int | bytes | str) -> Decimal:
        """Get the (unscaled) width of the character, in glyph-space units.

        Args:
            char: The character to check. May be a char code, or a string containing a
                single character.
        """
        if isinstance(char, str):
            char = self.encode(str)
        if isinstance(char, bytes):
            # Simple fonts always use single-byte encodings, so this is safe
            char = char[0]
        char_code = char - int(self.data.get(Name.FirstChar, 0))
        if Name.Widths in self.data and len(self.data.Widths) > char_code:
            width = self.data.Widths[char_code]
        elif Name.MissingWidth in self.data.FontDescriptor:
            width = self.data.FontDescriptor.MissingWidth
        else:
            width = Decimal(0)
        return width

    def convert_width(
        self, width: int | Decimal, fontsize: int | Decimal = 1
    ) -> int | Decimal:
        """Convert width from glyph space to text space, scaling by font size.

        Scaling based on the nominal height (see 9.2.2):

        "This standard is arranged so that the nominal height of tightly spaced lines of
        text is 1 unit. ... The standard-size font shall then be scaled to be usable."

        This means, essentially, that a font size of 1 means a character is 1 text-space
        unit high, and a font size of 12 is 12 text-space units high. Assuming no text
        scaling is in place (such as via the text matrix), and the PDF has not set a
        user-defined unit in the page dictionary, then text space units will be points
        (defined as 1/72 of an inch).
        """
        # For all but Type3 fonts, the ratio of text-space units to glyph-space units is
        # a fixed ratio of 1 to 1000 (See 9.2.4: Glyph Positioning and Metrics)
        glyph_space_ratio = Decimal(1000)
        return (width / glyph_space_ratio) * fontsize

    def convert_width_reverse(
        self, width: int | Decimal, fontsize: int | Decimal = 1
    ) -> int | Decimal:
        """Convert width from text space back to glyph space, scaling by font size."""
        # For all but Type3 fonts, the ratio of text-space units to glyph-space units is
        # a fixed ratio of 1 to 1000 (See 9.2.4: Glyph Positioning and Metrics)
        glyph_space_ratio = Decimal(1000)
        return (width * glyph_space_ratio) / fontsize

    def encode(self, text: str) -> bytes:
        """Encode a string in the encoding used by this font.

        This currently only works with fonts that use the WinAnsiEncoding or the
        MacRomanEncoding. Differences maps are supported, though with a limited
        set of recognized character names.
        """
        if Name.Encoding not in self.data:
            # This is allowed by the spec, and if I understand correctly has the same
            # meaning as StandardEncoding.
            raise NotImplementedError(
                'Cannot encode without explicitly defined encoding'
            )
        if isinstance(self.data.Encoding, Name):
            return self._encode_named(text, self.data.Encoding)
        if isinstance(self.data.Encoding, Dictionary):
            if Name.Differences in self.data.Encoding:
                return self._encode_diffmap(
                    text,
                    self.data.Encoding.Differences,
                    self.data.Encoding.get(Name.BaseEncoding),
                )
            if Name.BaseEncoding not in self.data.Encoding:
                raise NotImplementedError(
                    'Cannot encode without explicitly defined encoding'
                )
            return self._encode_named(text, self.data.Encoding.BaseEncoding)
        raise TypeError(f'Unsupported encoding type: {type(self.data.Encoding)}')

    def _encode_named(self, text: str, encoding: Name):
        if encoding == Name.StandardEncoding:
            # Standard encoding is defined as "whatever the underlying font uses by
            # default", but we have no good way to detect that.
            raise NotImplementedError('Cannot encode to StandardEncoding')
        if encoding == Name.WinAnsiEncoding:
            return text.encode('cp1252')
        if encoding == Name.MacRomanEncoding:
            return text.encode('mac_roman')
        if encoding == Name.MacExpertEncoding:
            # D.4 describes this character set if we want to implement a codec. However,
            # it doesn't seem actually useful to me.
            raise NotImplementedError('Cannot encode to MacExpertEncoding')
        if encoding == Name.PDFDocEncoding:
            # The spec says this is generally not used to show text, but includes it as
            # an option anyway, so we'll do the same.
            return text.encode('pdfdoc_pikepdf')
        raise ValueError('Unknown encoding:', encoding)

    def _encode_diffmap(
        self, text: str, diffmap: Array, base_encoding: Name | None = None
    ):
        if self._diffmap_cache is None:
            self._diffmap_cache = _differences_map_lookup(diffmap)
        result = bytearray()
        for char in text:
            if char in self._diffmap_cache:
                result.append(self._diffmap_cache[char])
            elif base_encoding is not None:
                result.extend(self._encode_named(char, base_encoding))
            elif char.isascii():
                result.append(ord(char))
            else:
                # Can't map character
                log.warning(f"No mapping for {repr(char)} in current encoding; skipped")

    def text_width(
        self,
        text: str | bytes,
        fontsize: int | Decimal = 1,
        *,
        char_spacing: int | Decimal = 0,
        word_spacing: int | Decimal = 0,
    ) -> int | Decimal:
        """Get the width of the string.

        This is the width of the string when rendered with the current font, scaled by
        the given font size.

        Args:
            text: The string to check
            fontsize: The target font size in text-space units. (Assuming text space
                isn't being scaled, this means the font size in points.)
            char_spacing: Additional space that will be added between each character.
                May be negative.
            word_spacing: Additional space that will be added after each ASCII space
                character (' '). May be negative.
        """
        width = 0
        ascii_space = ord(' ')
        if isinstance(text, str):
            text = self.encode(text)
        for byte in text:
            # It may seem like we are ignoring the possibility for multi-byte encodings
            # here. However, Simple Fonts are explicitly defined as using only
            # single-byte encodings (See 9.2.2), so this is safe. Composite fonts will
            # obviously require a more sophisticated implementation.
            width += self.unscaled_char_width(byte) + char_spacing
            if byte == ascii_space:
                width += word_spacing
        return self.convert_width(width, fontsize)


def _parse_differences_map(diffmap: Array):
    """Parses a Differences map to ``(char_code, char_name)`` pairs.

    This procedure is as described in 9.6.5.1.

    Here, ``char_code`` refers to the byte value of the character as it would appear in
    a text content stream using this font; it is the PDF encoding, not the true unicode
    character code. The corresponding ``char_name`` refers to the name of the glyph. The
    name is used by Type1 and Type3 fonts to look up the actual glyph used from the
    font.

    A partial mapping of glyph names to true unicode characters is available at
    pikepdf._data.CHARNAMES_TO_UNICODE`.
    """
    counter = 0
    for value in diffmap:
        if isinstance(value, Name):
            yield counter, value
            counter += 1
        else:
            # An index
            counter = value


# pdfminer.six has a some closely related code:
# https://github.com/pdfminer/pdfminer.six/blob/master/pdfminer/encodingdb.py
# It works exactly opposite of what we would need here, but still could be interesting
# to adapt.
def _differences_map_lookup(diffmap: Array) -> dict:
    """Convert a Differences map (See 9.6.5.1) to a Python dict.

    The Python dict maps unicode characters to the character index value.

    The character index values are the byte values used in actual text content streams.

    If the difference map encodes characters whose names aren't recognized, they will be
    omitted from the final map, and a warning emitted.
    """
    diff = {}
    for index, name in _parse_differences_map(diffmap):
        try:
            diff[CHARNAMES_TO_UNICODE[str(name)]] = index
        except KeyError:
            log.warning(f"Unknown character name in difference map: {str(name)}")
    return diff


class ContentStreamBuilder:
    """Content stream builder."""

    def __init__(self):
        """Initialize."""
        self._stream = bytearray()

    def _append(self, inst: ContentStreamInstruction):
        self._stream += unparse_content_stream([inst]) + b"\n"

    def extend(self, other: ContentStreamBuilder | bytes):
        """Append another content stream."""
        if isinstance(other, ContentStreamBuilder):
            self._stream += other._stream
        else:
            self._stream += other + b"\n"

    def push(self):
        """Save the graphics state."""
        inst = ContentStreamInstruction([], Operator("q"))
        self._append(inst)
        return self

    def pop(self):
        """Restore the graphics state."""
        inst = ContentStreamInstruction([], Operator("Q"))
        self._append(inst)
        return self

    def cm(self, matrix: Matrix):
        """Concatenate matrix."""
        inst = ContentStreamInstruction(matrix.shorthand, Operator("cm"))
        self._append(inst)
        return self

    def begin_text(self):
        """Begin text object.

        All text operations must be contained within a text object, and are invalid
        otherwise. The text matrix and font are reset for each text object. Text objects
        may not be nested.
        """
        inst = ContentStreamInstruction([], Operator("BT"))
        self._append(inst)
        return self

    def end_text(self):
        """End text object."""
        inst = ContentStreamInstruction([], Operator("ET"))
        self._append(inst)
        return self

    def begin_marked_content_proplist(self, mctype: Name, mcid: int):
        """Begin marked content sequence."""
        inst = ContentStreamInstruction(
            [mctype, Dictionary(MCID=mcid)], Operator("BDC")
        )
        self._append(inst)
        return self

    def begin_marked_content(self, mctype: Name):
        """Begin marked content sequence."""
        inst = ContentStreamInstruction([mctype], Operator("BMC"))
        self._append(inst)
        return self

    def end_marked_content(self):
        """End marked content sequence."""
        inst = ContentStreamInstruction([], Operator("EMC"))
        self._append(inst)
        return self

    def set_text_font(self, font: Name, size: int | float | Decimal):
        """Set text font and size.

        This operator is mandatory in order to show text. Any text object which attempts
        to show text without first calling this operator is invalid.

        The font name must match an entry in the current resources dictionary. The font
        size is expressed in text-space units. Assuming no text scaling is in place, and
        the PDF has not set a user-defined unit in the page dictionary, then text space
        units will be points (defined as 1/72 of an inch).
        """
        inst = ContentStreamInstruction([font, size], Operator("Tf"))
        self._append(inst)
        return self

    def set_text_char_spacing(self, size: int | float | Decimal):
        """Set the character spacing (Tc) for future text operations.

        This is a value, measured in unscaled text-space units, which will be used to
        adjust the spacing between characters. A value of 0 (the default) means that,
        for each rendered glyph, the cursor will advance only the actual width of the
        glyph. Positive values will result in additional space between characters, and
        negative values will cause glyphs to overlap.

        In vertical writing, the sign works opposite of what one might expect: a
        positive value shrinks the space, and a negative value increases it.
        """
        inst = ContentStreamInstruction([size], Operator("Tc"))
        self._append(inst)
        return self

    def set_text_word_spacing(self, size: int | float | Decimal):
        """Set the word spacing (Tw) for future text operations.

        This is a value, measured in unscaled text-space units, which will be added to
        the width of any ASCII space characters.

        In vertical writing, the sign works opposite of what one might expect: a
        positive value shrinks the space, and a negative value increases it.
        """
        inst = ContentStreamInstruction([size], Operator("Tw"))
        self._append(inst)
        return self

    def set_text_leading(self, size: int | float | Decimal):
        """Set the leading value (TL) for future text operations.

        This is the vertical spacing between lines. Specifically, it is defined as the
        distance between the baseline of the previous line to the baseline of the next
        line.
        """
        inst = ContentStreamInstruction([size], Operator("TL"))
        self._append(inst)
        return self

    def set_text_matrix(self, matrix: Matrix):
        """Set text matrix.

        The text matrix defines the conversion between text-space and page-space, in
        terms of both scaling and translation. If this matrix scales the text, then
        it redefines text-space units as being some scale factor of page-space units.
        """
        inst = ContentStreamInstruction(matrix.shorthand, Operator("Tm"))
        self._append(inst)
        return self

    def set_text_rendering(self, mode: int):
        """Set text rendering mode."""
        inst = ContentStreamInstruction([mode], Operator("Tr"))
        self._append(inst)
        return self

    def set_text_horizontal_scaling(self, scale: float):
        """Set text horizontal scaling."""
        inst = ContentStreamInstruction([scale], Operator("Tz"))
        self._append(inst)
        return self

    def show_text(self, encoded: bytes):
        """Show text.

        The text must be encoded in character codes expected by the font.
        """
        # [ <text string> ] TJ
        # operands need to be enclosed in Array
        # There is a Tj operator (lowercase j) which does not have this requirement,
        # but for some reason QPDF hex-encodes the strings when using that operator.
        # The TJ operator (Uppercase J) is technically meant for including spacing
        # options, rather than showing a single string.
        inst = ContentStreamInstruction([Array([String(encoded)])], Operator("TJ"))
        self._append(inst)
        return self

    def show_text_with_kerning(self, *parts: bytes | int | float | Decimal):
        """Show text, with manual spacing (kerning) options.

        Arguments are either bytes, which represent the actual text to show, or numbers,
        which move the cursor. The units for the numbers are expressed in thousandths
        of a text-space unit (thus typically equivalent to a glyph-space unit).

        For horizontal writing, positive values move the cursor left, and negative
        right. For vertical writing, positive values move down and negative up.

        The text must be encoded in character codes expected by the font.
        """
        inst = ContentStreamInstruction(
            [
                Array(
                    String(part) if isinstance(part, bytes) else part for part in parts
                )
            ],
            Operator("TJ"),
        )
        self._append(inst)
        return self

    def show_text_line(self, encoded: bytes):
        """Advance to the next line and show text.

        The text must be encoded in character codes expected by the font.

        This is functionally equivalent to ``move_cursor_new_line()`` followed by
        ``show_text_string(encoded)``, but in a single operation.
        """
        inst = ContentStreamInstruction([String(encoded)], Operator("'"))
        self._append(inst)
        return self

    def show_text_line_with_spacing(
        self, encoded: bytes, word_spacing: int, char_spacing: int
    ):
        """Advance to the next line and show text.

        The text must be encoded in character codes expected by the font.

        This is functionally equivalent to ``set_text_char_spacing(char_spacing)`` and
        ``set_text_word_spacing()``, followed by ``move_cursor_new_line()`` and then
        ``show_text(encoded)``, all in a single operation.
        """
        inst = ContentStreamInstruction(
            [word_spacing, char_spacing, String(encoded)], Operator('"')
        )
        self._append(inst)
        return self

    def move_cursor(self, dx, dy):
        """Move cursor by the given offset, relative to the start of the current line.

        This operator modifies the both current text matrix and the text line matrix.
        This means that, in addition to moving the current cursor, the new cursor will
        also be defined as the start of a new line.

        The new position will be redefined as the new start of the line even if the y
        offset is 0; what to a user may look like a single line of text could be encoded
        in the PDF content stream as multiple "lines". It's not uncommon for PDFs to be
        written with every word as a separate "line", allowing the PDF writer to
        explicitly define the spacing between each word.
        """
        inst = ContentStreamInstruction([dx, dy], Operator("Td"))
        self._append(inst)
        return self

    def move_cursor_new_line(self):
        """Move cursor to the start of the next line.

        This moves down by the current leading value, and resets the x position back to
        the value it had at the beginning of the current line.

        This operator modifies the both current text matrix and the text line matrix.
        This means that, in addition to moving the current cursor, the new cursor will
        also be defined as the start of a new line.

        The value this operation moves the cursor is set using ``set_text_leading``.
        """
        inst = ContentStreamInstruction([], Operator("T*"))
        self._append(inst)
        return self

    def stroke_and_close(self):
        """Stroke and close path."""
        inst = ContentStreamInstruction([], Operator("s"))
        self._append(inst)
        return self

    def fill(self):
        """Stroke and close path."""
        inst = ContentStreamInstruction([], Operator("f"))
        self._append(inst)
        return self

    def append_rectangle(self, x: float, y: float, w: float, h: float):
        """Append rectangle to path."""
        inst = ContentStreamInstruction([x, y, w, h], Operator("re"))
        self._append(inst)
        return self

    def set_stroke_color(self, r: float, g: float, b: float):
        """Set RGB stroke color."""
        inst = ContentStreamInstruction([r, g, b], Operator("RG"))
        self._append(inst)
        return self

    def set_fill_color(self, r: float, g: float, b: float):
        """Set RGB fill color."""
        inst = ContentStreamInstruction([r, g, b], Operator("rg"))
        self._append(inst)
        return self

    def set_line_width(self, width):
        """Set line width."""
        inst = ContentStreamInstruction([width], Operator("w"))
        self._append(inst)
        return self

    def line(self, x1: float, y1: float, x2: float, y2: float):
        """Draw line."""
        insts = [
            ContentStreamInstruction([x1, y1], Operator("m")),
            ContentStreamInstruction([x2, y2], Operator("l")),
        ]
        self._append(insts[0])
        self._append(insts[1])
        return self

    def set_dashes(self, array=None, phase=0):
        """Set dashes."""
        if array is None:
            array = []
        if isinstance(array, (int, float)):
            array = (array, phase)
            phase = 0
        inst = ContentStreamInstruction([array, phase], Operator("d"))
        self._append(inst)
        return self

    def draw_xobject(self, name: Name):
        """Draw XObject.

        Add instructions to render an XObject. The XObject must be
        defined in the document.

        Args:
            name: Name of XObject
        """
        inst = ContentStreamInstruction([name], Operator("Do"))
        self._append(inst)
        return self

    def build(self) -> bytes:
        """Build content stream."""
        return bytes(self._stream)


@dataclass
class LoadedImage:
    """Loaded image.

    This class is used to track images that have been loaded into a
    canvas.
    """

    name: Name
    image: Image.Image


class _CanvasAccessor:
    """Contains all drawing methods class for drawing on a Canvas."""

    def __init__(self, cs: ContentStreamBuilder, images=None):
        self._cs = cs
        self._images = images if images is not None else []
        self._stack_depth = 0

    def stroke_color(self, color: Color):
        """Set stroke color."""
        r, g, b = color.red, color.green, color.blue
        self._cs.set_stroke_color(r, g, b)
        return self

    def fill_color(self, color: Color):
        """Set fill color."""
        r, g, b = color.red, color.green, color.blue
        self._cs.set_fill_color(r, g, b)
        return self

    def line_width(self, width):
        """Set line width."""
        self._cs.set_line_width(width)
        return self

    def line(self, x1, y1, x2, y2):
        """Draw line from (x1,y1) to (x2,y2)."""
        self._cs.line(x1, y1, x2, y2)
        self._cs.stroke_and_close()
        return self

    def rect(self, x, y, w, h, fill: bool):
        """Draw optionally filled rectangle at (x,y) with width w and height h."""
        self._cs.append_rectangle(x, y, w, h)
        if fill:
            self._cs.fill()
        else:
            self._cs.stroke_and_close()
        return self

    def draw_image(self, image: Path | str | Image.Image, x, y, width, height):
        """Draw image at (x,y) with width w and height h."""
        with self.save_state(cm=Matrix(width, 0, 0, height, x, y)):
            if isinstance(image, (Path, str)):
                image = Image.open(image)
            image.load()
            if image.mode == "P":
                image = image.convert("RGB")
            if image.mode not in ("1", "L", "RGB"):
                raise ValueError(f"Unsupported image mode: {image.mode}")
            name = Name.random(prefix="Im")
            li = LoadedImage(name, image)
            self._images.append(li)
            self._cs.draw_xobject(name)
        return self

    def draw_text(self, text: Text):
        """Draw text object."""
        self._cs.extend(text._cs)
        self._cs.end_text()
        return self

    def dashes(self, *args):
        """Set dashes."""
        self._cs.set_dashes(*args)
        return self

    def push(self):
        """Save the graphics state."""
        self._cs.push()
        self._stack_depth += 1
        return self

    def pop(self):
        """Restore the previous graphics state."""
        self._cs.pop()
        self._stack_depth -= 1
        return self

    @contextmanager
    def save_state(self, *, cm: Matrix | None = None):
        """Save the graphics state and restore it on exit.

        Optionally, concatenate a transformation matrix. Implements
        the commonly used pattern of:

            q cm ... Q
        """
        self.push()
        if cm is not None:
            self.cm(cm)
        yield self
        self.pop()

    def cm(self, matrix: Matrix):
        """Concatenate a new transformation matrix to the current matrix."""
        self._cs.cm(matrix)
        return self


class Canvas:
    """Canvas for rendering PDFs with pikepdf.

    All drawing is done on a pikepdf canvas using the ``.do`` property.
    This interface manages the graphics state of the canvas.

    A Canvas can be exported as a single page Pdf using ``.to_pdf``. This Pdf can
    then be merged into other PDFs or written to a file.
    """

    def __init__(self, *, page_size: tuple[int | float, int | float]):
        """Initialize a canvas."""
        self.page_size = page_size
        self._pdf = Pdf.new()
        self._page = self._pdf.add_blank_page(page_size=page_size)
        self._page.Resources = Dictionary(Font=Dictionary(), XObject=Dictionary())
        self._cs = ContentStreamBuilder()
        self._images: list[LoadedImage] = []
        self._accessor = _CanvasAccessor(self._cs, self._images)
        self.do.push()

    def add_font(self, resource_name: Name, font: Font):
        """Add a font to the page."""
        self._page.Resources.Font[resource_name] = font.register(self._pdf)

    @property
    def do(self) -> _CanvasAccessor:
        """Do operations on the current graphics state."""
        return self._accessor

    def _save_image(self, li: LoadedImage):
        return self._pdf.make_stream(
            li.image.tobytes(),
            Width=li.image.width,
            Height=li.image.height,
            ColorSpace=(
                Name.DeviceGray if li.image.mode in ("1", "L") else Name.DeviceRGB
            ),
            Type=Name.XObject,
            Subtype=Name.Image,
            BitsPerComponent=1 if li.image.mode == '1' else 8,
        )

    def to_pdf(self) -> Pdf:
        """Render the canvas as a single page PDF."""
        self.do.pop()
        if self._accessor._stack_depth != 0:
            log.warning(
                "Graphics state stack is not empty when page saved - "
                "rendering may be incorrect"
            )
        self._page.Contents = self._pdf.make_stream(self._cs.build())
        for li in self._images:
            self._page.Resources.XObject[li.name] = self._save_image(li)
        bio = BytesIO()
        self._pdf.save(bio)
        bio.seek(0)
        result = Pdf.open(bio)

        # Reset the graphics state to before we saved the page
        self.do.push()
        return result

    def _repr_mimebundle_(self, include=None, exclude=None):
        return self.to_pdf()._repr_mimebundle_(include, exclude)


class Text:
    """Text object for rendering text on a pikepdf canvas."""

    def __init__(self, direction=TextDirection.LTR):
        """Initialize."""
        self._cs = ContentStreamBuilder()
        self._cs.begin_text()
        self._direction = direction

    def font(self, font: Name, size: float):
        """Set font and size."""
        self._cs.set_text_font(font, size)
        return self

    def render_mode(self, mode):
        """Set text rendering mode."""
        self._cs.set_text_rendering(mode)
        return self

    def text_transform(self, matrix: Matrix):
        """Set text matrix."""
        self._cs.set_text_matrix(matrix)
        return self

    def show(self, text: str | bytes):
        """Show text.

        The text must be encoded in character codes expected by the font.
        If a text string is passed, it will be encoded as UTF-16BE.
        Text rendering will not work properly if the font's character
        codes are not consistent with UTF-16BE. This is a rudimentary
        interface. You've been warned.
        """
        if isinstance(text, str):
            encoded = b"\xfe\xff" + text.encode("utf-16be")
        else:
            encoded = text
        if self._direction == TextDirection.LTR:
            self._cs.show_text(encoded)
        else:
            self._cs.begin_marked_content(Name.ReversedChars)
            self._cs.show_text(encoded)
            self._cs.end_marked_content()
        return self

    def horiz_scale(self, scale):
        """Set text horizontal scaling."""
        self._cs.set_text_horizontal_scaling(scale)
        return self

    def move_cursor(self, x, y):
        """Move cursor."""
        self._cs.move_cursor(x, y)
        return self
