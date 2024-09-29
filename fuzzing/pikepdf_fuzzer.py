# SPDX-FileCopyrightText: 2024 ennamarie19
# SPDX-License-Identifier: MIT

import io
import sys
from contextlib import contextmanager

import atheris
from fuzz_helpers import EnhancedFuzzedDataProvider

with atheris.instrument_imports(exclude=['pikepdf.settings']):
    import pikepdf
    from pikepdf import PdfError  # type: ignore


@contextmanager
def silence():
    so = sys.stdout
    se = sys.stderr
    sys.stdout = io.StringIO()
    sys.stderr = io.StringIO()
    yield
    sys.stdout = so
    sys.stderr = se


def TestOneInput(data):
    fdp = EnhancedFuzzedDataProvider(data)
    try:
        with fdp.ConsumeMemoryFile(all_data=True) as pdf_f, io.BytesIO() as out_f:
            with pikepdf.Pdf.open(pdf_f) as my_pdf:
                for page in my_pdf.pages:
                    page.rotate(180, relative=True)
                my_pdf.save(out_f)
    except PdfError:
        return -1
    except SystemError:
        return -1


def main():
    atheris.Setup(sys.argv, TestOneInput)
    atheris.Fuzz()


if __name__ == "__main__":
    main()
