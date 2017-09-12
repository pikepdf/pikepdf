from . import _qpdf

from ._qpdf import Object, ObjectType, PDFError, PDF, PasswordError

from collections import namedtuple



class _OperandGrouper(_qpdf.StreamParser):
    """Parse a PDF content stream into a sequence of instructions.

    Helper class for parsing PDF content streams into instructions. Semantics
    are a little weird since it is subclassed from C++.

    """

    PdfInstruction = namedtuple('PdfInstruction', ('operands', 'operator'))

    def __init__(self):
        super().__init__()
        self.instructions = []
        self._tokens = []

    def handle_object(self, obj):
        if obj.type_code == ObjectType.ot_operator:
            instruction = self.PdfInstruction(
                operands=self._tokens, operator=obj)
            self.instructions.append(instruction)
            self._tokens = []
        else:
            self._tokens.append(obj)

    def handle_eof(self):
        if self._tokens:
            raise EOFError("Unexpected end of stream")


def parse_content_stream(stream):
    """Parse a PDF content stream into a sequence of instructions.

    A PDF content stream is list of instructions that describe where to render
    the text and graphics in a PDF. This is the starting point for analyzing
    PDFs.

    Each instruction contains at least one operator and zero or more operands.

    >>> pdf = pikepdf.PDF.open(input_pdf)
    >>> stream = pdf.pages[0].Contents
    >>> for operands, command in parse_content_stream(stream):
    >>>     print(command)

    """

    if not isinstance(stream, Object):
        raise TypeError("stream must a PDF object")

    grouper = _OperandGrouper()
    try:
        Object.parse_stream(stream, grouper)
    except RuntimeError as e:
        if 'parseContentStream called on non-stream' in str(e):
            raise TypeError("parse_content_stream called on non-stream Object")
        raise e from e

    return grouper.instructions


class Page:
    def __init__(self, obj):
        self.obj = obj

    def __getattr__(self, item):
        return getattr(self.obj, item)

    def __setattr__(self, item, value):
        if item == 'obj':
            object.__setattr__(self, item, value)
        elif hasattr(self.obj, item):
            setattr(self.obj, item, value)
        else:
            raise AttributeError(item)

    def __repr__(self):
        return repr(self.obj).replace(
            'pikepdf.Object.Dictionary', 'pikepdf.Page', 1)

    @property
    def mediabox(self):
        return self.obj.MediaBox

    def extract_text(self):
        fragments = []
        for operands, operator in parse_content_stream(self.obj.Contents):
            if operator == Object.Operator('Tj'):
                fragments.append(str(operands[0]))
                fragments.append(" ")
        print(fragments)
        return "".join(fragments)