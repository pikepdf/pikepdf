# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.
#
# Copyright (C) 2017, James R. Barlow (https://github.com/jbarlow83/)

from typing import Collection, List, Tuple, Union, cast

from pikepdf import Object, ObjectType, Operator, PdfError, _qpdf

from .encryption import Encryption, EncryptionInfo, Permissions
from .image import PdfImage, PdfInlineImage, UnsupportedImageTypeError
from .matrix import PdfMatrix
from .metadata import PdfMetadata
from .outlines import (
    Outline,
    OutlineItem,
    OutlineStructureError,
    PageLocation,
    make_page_destination,
)

# Operands, Operator
ContentStreamOperands = Collection[Union[Object, PdfInlineImage]]
ContentStreamInstructions = Tuple[ContentStreamOperands, Operator]


class PdfParsingError(Exception):
    def __init__(self, message=None, line=None):
        if not message:
            message = f"Error encoding content stream at line {line}"
        super().__init__(message)
        self.line = line


def parse_content_stream(
    page_or_stream: Object, operators: str = ''
) -> List[ContentStreamInstructions]:
    """
    Parse a PDF content stream into a sequence of instructions.

    A PDF content stream is list of instructions that describe where to render
    the text and graphics in a PDF. This is the starting point for analyzing
    PDFs.

    If the input is a page and page.Contents is an array, then the content
    stream is automatically treated as one coalesced stream.

    Each instruction contains at least one operator and zero or more operands.

    This function does not have anything to do with opening a PDF file itself or
    processing data from a whole PDF. It is for processing a specific object inside
    a PDF that is already opened.

    Args:
        page_or_stream: A page object, or the content
            stream attached to another object such as a Form XObject.
        operators: A space-separated string of operators to whitelist.
            For example 'q Q cm Do' will return only operators
            that pertain to drawing images. Use 'BI ID EI' for inline images.
            All other operators and associated tokens are ignored. If blank,
            all tokens are accepted.

    Returns:
        list: List of ``(operands, command)`` tuples where ``command`` is an
            operator (str) and ``operands`` is a tuple of str; the PDF drawing
            command and the command's operands, respectively.

    Example:

        >>> pdf = pikepdf.Pdf.open(input_pdf)
        >>> page = pdf.pages[0]
        >>> for operands, command in parse_content_stream(page):
        >>>     print(command)

    """

    if not isinstance(page_or_stream, Object):
        raise TypeError("stream must be a pikepdf.Object")

    if (
        page_or_stream._type_code != ObjectType.stream
        and page_or_stream.get('/Type') != '/Page'
    ):
        raise TypeError("parse_content_stream called on page or stream object")

    try:
        if page_or_stream.get('/Type') == '/Page':
            page = page_or_stream
            instructions = cast(
                List[ContentStreamInstructions],
                page._parse_page_contents_grouped(operators),
            )
        else:
            stream = page_or_stream
            instructions = cast(
                List[ContentStreamInstructions],
                Object._parse_stream_grouped(stream, operators),
            )
    except PdfError as e:
        if 'supposed to be a stream or an array' in str(e):
            raise TypeError("parse_content_stream called on non-stream Object") from e
        else:
            raise e from e

    return instructions


def unparse_content_stream(
    instructions: Collection[ContentStreamInstructions],
) -> bytes:
    """
    Given a parsed list of instructions/operand-operators, convert to bytes suitable
    for embedding in a PDF. In PDF the operator always follows the operands.

    Args:
        instructions: list of (operands, operator) types such as is returned
            by :func:`parse_content_stream()`

    Returns:
        bytes: a binary content stream, suitable for attaching to a Pdf.
            To attach to a Pdf, use :meth:`Pdf.make_stream()``.
    """

    def encode(obj):
        return _qpdf.unparse(obj)

    def encode_iimage(iimage):
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
                    line = b' '.join(encode(operand) for operand in operands)
                    line += b' ' + encode_operator(operator)
            except (PdfError, ValueError) as e:
                raise PdfParsingError(line=n + 1) from e
            yield line

    return b'\n'.join(for_each_instruction())
