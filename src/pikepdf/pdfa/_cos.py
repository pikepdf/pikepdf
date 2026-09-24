# SPDX-FileCopyrightText: 2026 James R. Barlow
# SPDX-License-Identifier: MPL-2.0

"""Checks on every object of the file, whether or not the walker reached it.

veraPDF applies its stream and file specification rules to every object in
the file. The role schemas check the objects the walker reaches, with better
locations; this pass makes sure that no other object escapes the same rules.
"""

from __future__ import annotations

from typing import Any

import pikepdf
from pikepdf.pdfa._context import ValidationContext
from pikepdf.pdfa._limits import MAX_NESTING
from pikepdf.pdfa._report import FindingKind
from pikepdf.pdfa._shallow import pdf_repr

EXTERNAL_STREAM_KEYS = ('/F', '/FFilter', '/FDecodeParms')
PERMITTED_FILTERS = frozenset(
    {
        '/ASCIIHexDecode',
        '/ASCII85Decode',
        '/FlateDecode',
        '/RunLengthDecode',
        '/CCITTFaxDecode',
        '/JBIG2Decode',
        '/DCTDecode',
        '/JPXDecode',
    }
)


def _reported(ctx: ValidationContext) -> set[tuple[str, str]]:
    """(rule id, object) of the findings reported so far."""
    return {
        (finding.rule, finding.where.split(' (', 1)[0])
        for finding in ctx.report.findings
    }


def _filter_names(value: Any) -> list[Any]:
    if isinstance(value, pikepdf.Array):
        return [pikepdf.unbox(item) for item in value]
    return [pikepdf.unbox(value)]


class _ObjectChecker:
    """Check every object of one file, reporting each problem once per object."""

    def __init__(self, ctx: ValidationContext):
        self.ctx = ctx
        self.reported = _reported(ctx)
        self.part1 = ctx.flavour.part == 1

    def deny(
        self, rule: str, where: str, message: str, kind: FindingKind = 'violation'
    ) -> None:
        if (rule, where) in self.reported:
            return
        self.reported.add((rule, where))
        self.ctx.deny(rule, where, message, kind)

    def check(self, obj: Any) -> None:
        where = self.ctx.describe(obj)
        if isinstance(obj, pikepdf.Stream):
            self.stream(obj, where)
        self.contents(obj, where, 0)

    def stream(self, stream: pikepdf.Stream, where: str) -> None:
        """Deny external stream data and filters PDF/A does not permit.

        The filters checked are those the write model says will be written.
        """
        stream_dict = stream.stream_dict
        keys = set(stream_dict.keys())
        found = [key for key in EXTERNAL_STREAM_KEYS if key in keys]
        if found:
            self.deny(
                self.ctx.rule('6.1.7-3', '6.1.7.1-3'),
                where,
                f"stream dictionary contains {', '.join(found)}",
            )
        if stream_dict.get('/Type') == pikepdf.Name.EmbeddedFile:
            self.deny(
                'pikepdf:embedded-file',
                where,
                "embedded files are not supported",
                'unsupported',
            )
        filters, _decode_parms = self.ctx.model.stream_filters(stream)
        if filters is None:
            return
        for item in _filter_names(filters):
            if not isinstance(item, pikepdf.Name):
                self.deny(
                    'pikepdf:filter',
                    where,
                    f"stream filter {pdf_repr(item)} is not a name",
                    'unsupported',
                )
                continue
            name = str(item)
            if name in PERMITTED_FILTERS:
                continue
            if name == '/LZWDecode' or not self.part1:
                self.deny(
                    self.ctx.rule('6.1.10-1', '6.1.7.2-1'),
                    where,
                    f"stream filter {name} is not permitted",
                )
            else:
                self.deny(
                    'pikepdf:filter',
                    where,
                    f"stream filter {name} is not supported",
                    'unsupported',
                )

    def contents(self, value: Any, where: str, depth: int) -> None:
        """Deny embedded and associated files in an object and its direct parts."""
        if depth > MAX_NESTING:
            return  # reported by the limit checks
        if isinstance(value, pikepdf.Stream):
            if depth > 0:
                return  # an indirect object of its own
            items = list(value.stream_dict.items())
            keys = {key for key, _ in items}
        elif isinstance(value, pikepdf.Dictionary):
            if depth > 0 and value.is_indirect:
                return
            items = list(value.items())
            keys = {key for key, _ in items}
        elif isinstance(value, pikepdf.Array):
            if depth > 0 and value.is_indirect:
                return
            for item in value:
                self.contents(item, where, depth + 1)
            return
        else:
            return
        if '/EF' in keys:
            if self.part1:
                self.deny(
                    self.ctx.rule('6.1.11-1', None),
                    where,
                    "embedded files are not permitted in PDF/A-1",
                )
            else:
                self.deny(
                    'pikepdf:embedded-file',
                    where,
                    "embedded files are not supported",
                    'unsupported',
                )
        if '/AF' in keys:
            self.deny(
                'pikepdf:associated-files',
                where,
                "associated files (/AF) are not supported",
                'unsupported',
            )
        for _, item in items:
            self.contents(item, where, depth + 1)


def check_objects(ctx: ValidationContext) -> None:
    """Check every object in the file.

    Denies external stream data (/F, /FFilter, /FDecodeParms), filters
    other than the standard ones PDF/A permits, and embedded and associated
    files (file specifications with /EF, embedded file streams, /AF).
    """
    checker = _ObjectChecker(ctx)
    checker.contents(ctx.pdf.trailer, 'trailer', 0)
    for obj in ctx.model.objects(ctx.pdf):
        checker.check(obj)
