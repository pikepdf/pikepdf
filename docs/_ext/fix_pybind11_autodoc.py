# pybind11 generates some docstrings and function signatures that are functionally
# correct but encourage users to rely on implementation details. Fix these here.

import re

replacements = [
    (re.compile(r'pikepdf._qpdf.(\w+)\b'), r'pikepdf.\1'),
    (re.compile(r'QPDFTokenizer::Token\b'), 'pikepdf.Token'),
    (re.compile(r'QPDFObjectHandle'), 'pikepdf.Object'),
    (re.compile(r'QPDFExc'), 'pikepdf.PdfError'),
]


def fix_sigs(app, what, name, obj, options, signature, return_annotation):
    for from_, to in replacements:
        if signature:
            signature = from_.sub(to, signature)
        if return_annotation:
            return_annotation = from_.sub(to, return_annotation)
    return signature, return_annotation


def fix_doc(app, what, name, obj, options, lines):
    for n, line in enumerate(lines[:]):
        for from_, to in replacements:
            lines[n] = from_.sub(to, lines[n])


def setup(app):
    app.connect('autodoc-process-signature', fix_sigs)
    app.connect('autodoc-process-docstring', fix_doc)

    return {'version': '0.1', 'parallel_read_safe': True, 'parallel_write_safe': True}
