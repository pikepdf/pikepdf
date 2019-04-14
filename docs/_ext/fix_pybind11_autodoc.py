# pybind11 generates some docstrings and function signatures that are functionally
# correct but encourage users to rely on implementation details. Fix these here.

replacements = {
    'pikepdf._qpdf.Object': 'pikepdf.Object',
    'pikepdf._qpdf.Pdf': 'pikepdf.Pdf',
    'QPDFObjectHandle': 'pikepdf.Object',
    'QPDFExc': 'pikepdf.PdfError',
}


def fix_sigs(app, what, name, obj, options, signature, return_annotation):
    for from_, to in replacements.items():
        if signature:
            signature = signature.replace(from_, to)
        if return_annotation:
            return_annotation = return_annotation.replace(from_, to)
    return signature, return_annotation


def fix_doc(app, what, name, obj, options, lines):
    for n, line in enumerate(lines[:]):
        for from_, to in replacements.items():
            lines[n] = lines[n].replace(from_, to)


def setup(app):
    app.connect('autodoc-process-signature', fix_sigs)
    app.connect('autodoc-process-docstring', fix_doc)

    return {'version': '0.1', 'parallel_read_safe': True, 'parallel_write_safe': True}
