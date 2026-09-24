# SPDX-FileCopyrightText: 2026 James R. Barlow
# SPDX-License-Identifier: MPL-2.0

"""What the validator sees of a document once it is written.

qpdf's writer changes some things between the in-memory object graph and the
bytes it writes: stream filters, the trailer, the version, encryption, the
cross-reference format and which objects are written at all. The validator
asks a `WriteModel` for these instead of reading them from the open `Pdf`,
so it can evaluate the written form of a document without writing it.

`WriteModel.identity` answers with the in-memory values, which is correct
for a document opened from a file that is being validated as written.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

import pikepdf
from pikepdf.pdfa._shallow import shallow_json_of


class WriteModel:
    """Predicts the written form of a document for the validator.

    Construct instances with `WriteModel.identity`.
    """

    __slots__ = ('_save_kwargs',)

    def __init__(self, save_kwargs: dict[str, Any] | None = None) -> None:
        # None means identity: the written form is the in-memory form.
        self._save_kwargs = None if save_kwargs is None else dict(save_kwargs)

    @classmethod
    def identity(cls) -> WriteModel:
        """Return a model in which the written form is the in-memory form."""
        return cls()

    @property
    def is_identity(self) -> bool:
        """True if this model reports the in-memory values unchanged."""
        return self._save_kwargs is None

    def __repr__(self) -> str:
        if self.is_identity:
            return 'WriteModel.identity()'
        return f'WriteModel({self._save_kwargs!r})'

    def stream_filters(self, stream: pikepdf.Stream) -> tuple[Any, Any]:
        """Return the stream's ``(/Filter, /DecodeParms)`` once written.

        Each is the value of the stream dictionary entry, or None if absent.
        """
        return stream.get('/Filter'), stream.get('/DecodeParms')

    def trailer_json(self, trailer: pikepdf.Dictionary) -> dict[str, Any]:
        """Return the shallow JSON encoding of the trailer once written."""
        return shallow_json_of(trailer)

    def version(self, pdf: pikepdf.Pdf) -> str:
        """Return the PDF version in the header once written, e.g. ``'1.7'``."""
        return pdf.pdf_version

    def encrypted(self, pdf: pikepdf.Pdf) -> bool:
        """Return True if the written file is encrypted."""
        return pdf.is_encrypted

    def xref_stream(self, pdf: pikepdf.Pdf) -> bool:
        """Return True if the written file uses a cross-reference stream."""
        return pdf.trailer.get('/Type') == pikepdf.Name.XRef

    def objects(self, pdf: pikepdf.Pdf) -> Iterable[pikepdf.Object]:
        """Return the indirect objects written to the file."""
        return pdf.objects
