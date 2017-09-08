from . import _qpdf

from ._qpdf import Object, ObjectType, PdfError, Pdf

from collections import namedtuple

PdfInstruction = namedtuple('PdfInstruction', ('operands', 'operator'))


class OperandGrouper(_qpdf.StreamParser):
    """Parse a PDF content stream into a sequence of instructions.

    A PDF content stream is list of instructions that describe where to render
    the text and graphics in a PDF. This is the starting point for analyzing
    PDFs.

    Each instruction contains at least one operator and zero or more operands.

    TO DO: move to a private class that hides the details since the usage is
    necessarily weird

    >>> pdf = pikepdf.Pdf.open(input_pdf)
    >>> stream = pdf.pages[0].Contents
    >>> grouper = pikepdf.OperandGrouper()
    >>> qpdf.Object.parse_stream(stream, grouper)
    >>> for operands, command in grouper.instructions:
    >>>     print(command)

    """

    def __init__(self):
        super().__init__()
        self.instructions = []
        self._tokens = []

    def handle_object(self, obj):
        if obj.type_code == ObjectType.ot_operator:
            instruction = PdfInstruction(operands=self._tokens, operator=obj)
            self.instructions.append(instruction)
            self._tokens = []
        else:
            self._tokens.append(obj)

    def handle_eof(self):
        if self._tokens:
            raise EOFError("Unexpected end of stream")