# SPDX-FileCopyrightText: 2026 James R. Barlow
# SPDX-License-Identifier: MPL-2.0

"""Checks on every object of the file, whether or not the walker reached it.

veraPDF applies its stream and file specification rules, and the
implementation limits, to every object in the file. The role schemas check the
objects the walker reaches, with better locations; this pass makes sure that no
other object escapes the same rules.

Embedded and associated files are denied wherever they appear, except in
PDF/A-3 where the walker checked them: file specifications and embedded file
streams it reached as ``FileSpec`` and ``EmbeddedFile``, and the catalog's own
/AF array.
"""

from __future__ import annotations

import pikepdf
from pikepdf.pdfa._context import ValidationContext
from pikepdf.pdfa._limits import LimitChecker
from pikepdf.pdfa._report import FindingKind
from pikepdf.pdfa._shallow import pdf_repr

EXTERNAL_STREAM_KEYS = ('/F', '/FFilter', '/FDecodeParms')
FILE_KEYS = frozenset({'/EF', '/AF'})
# The role whose objects may hold each file key at their top level, in PDF/A-3
FILE_KEY_ROLES = {'/EF': 'FileSpec', '/AF': 'Catalog'}
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


def _filter_names(value: pikepdf.Object) -> list[pikepdf.Object]:
    if isinstance(value, pikepdf.Array):
        return list(value)
    return [value]


class _ObjectChecker:
    """Check every object of one file, reporting each problem once per object."""

    def __init__(self, ctx: ValidationContext):
        self.ctx = ctx
        self.reported = _reported(ctx)
        self.part1 = ctx.flavour.part == 1
        self.part3 = ctx.flavour.part == 3
        self.limits = LimitChecker(ctx.flavour)

    def deny(
        self, rule: str, where: str, message: str, kind: FindingKind = 'violation'
    ) -> None:
        if (rule, where) in self.reported:
            return
        self.reported.add((rule, where))
        self.ctx.deny(rule, where, message, kind)

    def check(self, obj: pikepdf.Object) -> None:
        """Check an indirect object, or the trailer, and its direct parts."""
        # One walk of the object serves the limit checks and finds the keys of
        # its dictionaries, which is all the file specification checks need.
        keys: set[str] = set()
        problems = self.limits.problems(obj, keys=keys)
        stream = obj if isinstance(obj, pikepdf.Stream) else None
        if not problems and stream is None and keys.isdisjoint(FILE_KEYS):
            return
        where = self.ctx.describe(obj) if obj.is_indirect else 'trailer'
        self.limit_problems(problems, where)
        if stream is not None:
            self.stream(stream, where)
        if self.part3 and not keys.isdisjoint(FILE_KEYS):
            keys = self.unchecked_file_keys(obj, keys)
        self.file_keys(keys, where)

    def limit_problems(self, problems: list[tuple[str, str]], where: str) -> None:
        """Deny each limit an object breaks, once per kind of limit."""
        limits = self.limits
        reported: set[str] = set()
        for key, message in problems:
            if key in reported:
                continue
            reported.add(key)
            self.ctx.deny(limits.rule(key), where, message, limits.kind(key))

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
        if stream_dict.get('/Type') == pikepdf.Name.EmbeddedFile and not (
            self.part3 and self.ctx.roles.get(stream.objgen) == 'EmbeddedFile'
        ):
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

    def unchecked_file_keys(self, obj: pikepdf.Object, keys: set[str]) -> set[str]:
        """Remove the file keys the walker checked from an object's keys.

        A key is checked if it is in the top level of an object the walker
        reached with the role that permits it, and not also in one of the
        object's direct parts, which no role permits it in.
        """
        role = self.ctx.roles.get(obj.objgen) if obj.is_indirect else None
        exempt = {key for key, owner in FILE_KEY_ROLES.items() if owner == role}
        if not exempt & keys:
            return keys
        top = obj.stream_dict if isinstance(obj, pikepdf.Stream) else obj
        nested: set[str] = set()
        for _key, value in top.items():
            if isinstance(value, pikepdf.Object) and not value.is_indirect:
                self.limits.problems(value, keys=nested)
        return keys - (exempt - nested)

    def file_keys(self, keys: set[str], where: str) -> None:
        """Deny embedded and associated files, given the keys of an object."""
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


def check_objects(ctx: ValidationContext) -> None:
    """Check every object written to the file, and the trailer.

    Denies values beyond the implementation limits, external stream data
    (/F, /FFilter, /FDecodeParms), filters other than the standard ones
    PDF/A permits, and embedded and associated files (file specifications
    with /EF, embedded file streams, /AF) other than those the walker
    checked in PDF/A-3.
    """
    checker = _ObjectChecker(ctx)
    checker.check(ctx.pdf.trailer)
    for obj in ctx.model.objects(ctx.pdf):
        if isinstance(obj, pikepdf.Object):
            checker.check(obj)
        # else an indirect integer, real or boolean: checked where it is used
