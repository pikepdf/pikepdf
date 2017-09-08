from . import _qpdf

from ._qpdf import Object, ObjectType, QPDFError, QPDF


class OperandGrouper(_qpdf.StreamParser):
    def __init__(self):
        super().__init__()
        self.groups = []
        self.operands = []

    def handle_object(self, obj):
        if obj.type_code == ObjectType.ot_operator:
            self.groups.append((self.operands, obj))
            self.operands = []
        else:
            self.operands.append(obj)

    def handle_eof(self):
        if self.operands:
            raise EOFError("Unexpected end of stream")