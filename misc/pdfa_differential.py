#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 James R. Barlow
# SPDX-License-Identifier: MPL-2.0

"""Differential testing of pikepdf's PDF/A validator against veraPDF.

Every input is first made into a PDF/A candidate, and only the candidates are
validated: raw inputs are never validated. A candidate is made by opening the
input, running `pikepdf.pdfa.prepare`, checking the document with
`pikepdf.pdfa.check` (the *predicted* verdict) and saving it with the settings
that check reports. The saved file is then validated with
`pikepdf.pdfa.validate_written` (the *written* verdict, called ``ours``) and
by veraPDF, and the verdicts are compared.

Candidates are saved with ``Pdf.save`` rather than ``pikepdf.pdfa.save`` so
that denied candidates still exist and can be given to veraPDF with
``--check-denied``. ``--via-save`` uses ``pikepdf.pdfa.save`` instead, which
exercises its atomic write path.

The verdict classes are:

``agree``
    Both validators reached the same verdict.
``false-approval``
    pikepdf approved a candidate veraPDF rejects. This is a bug in the
    validator.
``no-result``
    pikepdf approved a candidate but veraPDF produced no validation result,
    typically because it considered the file too broken to parse. This is
    treated as a false approval.
``prediction-mismatch``
    The predicted verdict or set of rule ids differs from the written one:
    ``check`` did not describe the file ``save`` wrote. This is a bug.
``over-denial``
    pikepdf denied a candidate veraPDF accepts. The validator is conservative
    by design, so this is not a bug, but the count is a useful measure of how
    conservative it is.
``not-checked``
    pikepdf found constructs it does not check (verdict ``not_checked``).
    veraPDF's verdict is recorded when it was run.

veraPDF is run once per flavour over a directory of candidates, so the JVM
starts only once per flavour. It is found through the ``PIKEPDF_VERAPDF``
environment variable, ``~/verapdf/verapdf``, ``verapdf`` on PATH or the
veraPDF flatpak, in that order.

Subcommands:

``one <pdf> [flavours...]``
    Convert one file and show both verdicts in detail.
``corpus <dir>``
    Convert every PDF under a directory, for example a checkout of
    https://github.com/veraPDF/veraPDF-corpus.
``fuzz <candidate-dir>``
    Apply seeded random mutations to approved candidates (such as those kept
    by ``corpus --keep-approved``), convert the mutants and compare verdicts.

The exit code is 1 if any false approval, no-result or prediction mismatch
was found, else 0. Candidates involved in a disagreement are kept in the
output directory, along with ``results.json`` describing every candidate.
"""

from __future__ import annotations

import argparse
import functools
import json
import logging
import os
import random
import re
import shutil
import subprocess
import sys
import tempfile
import traceback
import warnings
from collections import Counter
from collections.abc import Callable, Iterable, Sequence
from concurrent.futures import ProcessPoolExecutor
from dataclasses import asdict, dataclass, field
from decimal import Decimal
from pathlib import Path
from typing import Any

import pikepdf
from pikepdf import Array, Dictionary, Name, String, pdfa

FLAVOURS = ('1b', '2b', '3b')

AGREE = 'agree'
FALSE_APPROVAL = 'false-approval'
NO_RESULT = 'no-result'
OVER_DENIAL = 'over-denial'
NOT_CHECKED = 'not-checked'
PREDICTION_MISMATCH = 'prediction-mismatch'
FAILING_VERDICTS = (FALSE_APPROVAL, NO_RESULT, PREDICTION_MISMATCH)
KEPT_VERDICTS = (*FAILING_VERDICTS, OVER_DENIAL)

# How many findings of each report to keep in a record
MAX_FINDINGS = 10


def normalize_flavour(value: str) -> str:
    """Accept ``2b``, ``2``, ``pdfa-2`` or ``PDF/A-2b`` and return ``2b``."""
    match = re.search(r'([123])b?$', value.strip().lower())
    if not match:
        raise argparse.ArgumentTypeError(f"not a PDF/A-1b/2b/3b flavour: {value}")
    return f'{match.group(1)}b'


def parse_flavours(value: str) -> list[str]:
    """Parse a comma-separated list of flavours."""
    return [normalize_flavour(v) for v in value.split(',') if v.strip()]


# --- veraPDF -------------------------------------------------------------


@dataclass
class VeraResult:
    """veraPDF's verdict on one file.

    ``compliant`` is None if veraPDF produced no validation result.
    """

    compliant: bool | None
    failed_rules: list[str] = field(default_factory=list)
    message: str = ''


@functools.cache
def verapdf_command() -> list[str] | None:
    """Return the command that runs veraPDF, or None if it is not available.

    Tries, in order: the ``PIKEPDF_VERAPDF`` environment variable,
    ``~/verapdf/verapdf``, ``verapdf`` on PATH and the veraPDF flatpak.
    """
    env = os.environ.get('PIKEPDF_VERAPDF')
    if env:
        return [env]
    home_install = Path.home() / 'verapdf' / 'verapdf'
    if home_install.is_file():
        return [os.fspath(home_install)]
    on_path = shutil.which('verapdf')
    if on_path:
        return [on_path]
    flatpak = [
        'flatpak',
        'run',
        '--filesystem=host:ro',
        f'--filesystem={tempfile.gettempdir()}:ro',
        '--command=verapdf',
        'org.verapdf.veraPDF',
    ]
    try:
        subprocess.run(
            [*flatpak, '--version'],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return flatpak


def parse_verapdf_report(report: dict[str, Any]) -> dict[str, VeraResult]:
    """Parse veraPDF's ``--format json`` output.

    Returns:
        A mapping from each job's item name (the path veraPDF was given or
        found) to its result.
    """
    results: dict[str, VeraResult] = {}
    for job in report['report']['jobs']:
        name = job['itemDetails']['name']
        validation = job.get('validationResult') or []
        if not validation:
            exc = job.get('taskException') or job.get('taskResult') or {}
            message = exc.get('exceptionMessage') or exc.get('exception') or ''
            results[name] = VeraResult(None, [], str(message) or "no result")
            continue
        verdict = validation[0]
        rules = [
            f"{rule['clause']}-{rule['testNumber']}"
            for rule in verdict.get('details', {}).get('ruleSummaries', [])
            if rule.get('ruleStatus') == 'FAILED'
        ]
        results[name] = VeraResult(
            bool(verdict.get('compliant')), rules, verdict.get('statement', '')
        )
    return results


def run_verapdf(target: Path, flavour: str) -> dict[Path, VeraResult]:
    """Run veraPDF once over *target*, a file or a directory of PDFs.

    Returns:
        A mapping from resolved file path to result.

    Raises:
        RuntimeError: If veraPDF is not available or did not write a
            parseable report.
    """
    command = verapdf_command()
    if command is None:
        raise RuntimeError(
            "veraPDF not found; set PIKEPDF_VERAPDF to the verapdf executable"
        )
    target = target.resolve()
    if command[0] == 'flatpak':
        # The flatpak sandbox sees the host read-only but not every
        # directory under /tmp, so grant access to the candidates.
        where = target if target.is_dir() else target.parent
        command = [*command[:2], f'--filesystem={where}:ro', *command[2:]]
    args = [*command, '-f', flavour, '--format', 'json']
    args += ['--maxfailuresdisplayed', '1']
    if target.is_dir():
        args.append('-r')
    args.append(str(target))
    proc = subprocess.run(args, capture_output=True, text=True, check=False)
    try:
        report = json.loads(proc.stdout)
    except json.JSONDecodeError as e:
        raise RuntimeError(
            f"veraPDF did not produce a JSON report (exit {proc.returncode}): "
            f"{proc.stderr[-1000:]}"
        ) from e
    return {
        Path(name).resolve(): result
        for name, result in parse_verapdf_report(report).items()
    }


# --- Candidate records ---------------------------------------------------


@dataclass
class Record:
    """One candidate and the verdicts on it.

    ``predicted`` is the verdict of `pikepdf.pdfa.check` before saving and
    ``ours`` the verdict of `pikepdf.pdfa.validate_written` on the saved
    candidate; each is ``'pass'``, ``'fail'``, ``'not_checked'`` or None if
    the candidate never got that far. ``rules`` and ``predicted_rules`` are
    the sorted rule ids of every finding in each report.
    """

    flavour: str
    label: str
    candidate: str | None
    stage: str = ''
    predicted: str | None = None
    ours: str | None = None
    findings: list[str] = field(default_factory=list)
    predicted_findings: list[str] = field(default_factory=list)
    rules: list[str] = field(default_factory=list)
    predicted_rules: list[str] = field(default_factory=list)
    mismatch: bool = False
    error: str = ''
    vera: VeraResult | None = None
    verdict: str = ''


def classify(ours: str, vera: VeraResult) -> str:
    """Compare pikepdf's written verdict with veraPDF's."""
    if ours == 'not_checked':
        return NOT_CHECKED
    ours_passed = ours == 'pass'
    if vera.compliant is None:
        return NO_RESULT if ours_passed else AGREE
    if ours_passed == vera.compliant:
        return AGREE
    return FALSE_APPROVAL if ours_passed else OVER_DENIAL


def settle(record: Record) -> None:
    """Set *record*'s verdict from its verdicts and veraPDF's result.

    A false approval or no-result outranks a prediction mismatch, which
    outranks every other class. Without a veraPDF result, the verdict is
    only set for a prediction mismatch or a not_checked candidate.
    """
    if record.ours is None:
        return
    verdict = classify(record.ours, record.vera) if record.vera else ''
    if not verdict and record.ours == 'not_checked':
        verdict = NOT_CHECKED
    if record.mismatch and verdict not in (FALSE_APPROVAL, NO_RESULT):
        verdict = PREDICTION_MISMATCH
    record.verdict = verdict


def prediction_mismatch(predicted: pdfa.Report, written: pdfa.Report) -> bool:
    """True if the predicted report does not describe the written file."""
    if predicted.verdict != written.verdict:
        return True
    return {f.rule for f in predicted.findings} != {f.rule for f in written.findings}


def _quiet_worker() -> None:
    logging.disable(logging.CRITICAL)
    warnings.simplefilter('ignore')


def _save_via_pdfa_save(
    pdf: pikepdf.Pdf, candidate: Path, flavour: str, predicted: pdfa.Report
) -> pdfa.Report:
    """Save with ``pikepdf.pdfa.save`` and return the report on the result."""
    from pikepdf.pdfa import (  # type: ignore[attr-defined, unused-ignore]
        save as pdfa_save,
    )

    try:
        result = pdfa_save(pdf, candidate, flavour)
    except pdfa.PdfaError as e:
        candidate.unlink(missing_ok=True)
        return e.report
    if isinstance(result, pdfa.Report):
        return result
    return pdfa.validate_written(candidate, flavour, save_kwargs=predicted.save_kwargs)


def convert_and_validate(
    source: Path,
    candidate: Path,
    flavour: str,
    label: str,
    via_save: bool = False,
) -> Record:
    """Make a PDF/A candidate of *source*, then validate it with pikepdf."""
    record = Record(flavour, label, str(candidate))
    try:
        with pikepdf.open(source) as pdf:
            pdfa.prepare(pdf, flavour)
            try:
                predicted = pdfa.check(pdf, flavour)
            except Exception:  # noqa: BLE001
                record.stage = 'validator-crash'
                record.candidate = None
                record.error = traceback.format_exc()[-800:]
                return record
            if via_save:
                written = _save_via_pdfa_save(pdf, candidate, flavour, predicted)
            else:
                pdf.save(candidate, **predicted.save_kwargs)
                written = None
    except Exception as e:  # noqa: BLE001
        candidate.unlink(missing_ok=True)
        record.stage = 'convert-failed'
        record.candidate = None
        record.error = f"{type(e).__name__}: {e}"[:300]
        return record
    if not candidate.exists():
        record.candidate = None
    try:
        if written is None:
            written = pdfa.validate_written(
                candidate, flavour, save_kwargs=predicted.save_kwargs
            )
    except Exception:  # noqa: BLE001
        record.stage = 'validator-crash'
        record.error = traceback.format_exc()[-800:]
        return record
    record.stage = 'validated'
    record.predicted = predicted.verdict
    record.ours = written.verdict
    record.findings = [str(f) for f in written.findings[:MAX_FINDINGS]]
    record.predicted_findings = [str(f) for f in predicted.findings[:MAX_FINDINGS]]
    record.rules = sorted({f.rule for f in written.findings})
    record.predicted_rules = sorted({f.rule for f in predicted.findings})
    record.mismatch = prediction_mismatch(predicted, written)
    settle(record)
    return record


def _convert_job(job: tuple[Path, Path, str, str, bool]) -> Record:
    return convert_and_validate(*job)


def run_parallel(
    fn: Callable[[Any], Record], jobs: Sequence[Any], workers: int
) -> list[Record]:
    """Map *fn* over *jobs* in worker processes, preserving order."""
    if workers <= 1:
        _quiet_worker()
        return [fn(job) for job in jobs]
    with ProcessPoolExecutor(workers, initializer=_quiet_worker) as pool:
        return list(pool.map(fn, jobs, chunksize=4))


def compare_with_verapdf(
    records: list[Record],
    flavour: str,
    candidate_dir: Path,
    *,
    check_denied: bool = False,
) -> None:
    """Run veraPDF over *candidate_dir* and fill in each record's verdict.

    Candidates pikepdf did not approve are removed before veraPDF runs
    unless *check_denied* is set.
    """
    for record in records:
        denied = record.ours is not None and record.ours != 'pass'
        if denied and not check_denied and record.candidate:
            Path(record.candidate).unlink(missing_ok=True)
            record.candidate = None
    wanted = [r for r in records if r.ours is not None and r.candidate]
    if wanted:
        vera = run_verapdf(candidate_dir, flavour)
        for record in wanted:
            assert record.candidate is not None
            result = vera.get(Path(record.candidate).resolve())
            if result is None:
                result = VeraResult(None, [], "file missing from veraPDF report")
            record.vera = result
    for record in records:
        settle(record)


def prune_candidates(records: Iterable[Record], *, keep_approved: bool) -> None:
    """Delete candidates that are not needed for inspection."""
    for record in records:
        if not record.candidate:
            continue
        keep = record.verdict in KEPT_VERDICTS
        keep |= record.stage == 'validator-crash'
        keep |= keep_approved and record.ours == 'pass'
        if not keep:
            Path(record.candidate).unlink(missing_ok=True)
            record.candidate = None


# --- Report --------------------------------------------------------------


def top_rules(records: Iterable[Record], verdict: str, n: int = 10) -> list[str]:
    """The *n* rule ids most often found in records with *verdict*.

    Each rule id is counted once per record.
    """
    counts = Counter(rule for r in records if r.verdict == verdict for rule in r.rules)
    return [f"{count:5d} {rule}" for rule, count in counts.most_common(n)]


def _describe_record(record: Record) -> list[str]:
    lines = [f"   {record.verdict.upper()} {record.label}"]
    if record.mismatch:
        lines.append(
            f"       predicted {record.predicted} {record.predicted_rules}, "
            f"written {record.ours} {record.rules}"
        )
    if record.vera is not None:
        if record.vera.failed_rules:
            lines.append(f"       veraPDF fails: {', '.join(record.vera.failed_rules)}")
        elif record.vera.compliant is None:
            lines.append(f"       veraPDF: {record.vera.message[:200]}")
    lines.extend(f"       ours: {finding}" for finding in record.findings[:3])
    if record.candidate:
        lines.append(f"       candidate: {record.candidate}")
    return lines


def format_report(records: Sequence[Record], *, show_over_denials: bool) -> str:
    """Summarize *records* per flavour and list every disagreement."""
    lines: list[str] = []
    for flavour in FLAVOURS:
        subset = [r for r in records if r.flavour == flavour]
        if not subset:
            continue
        stages = Counter(r.stage for r in subset)
        ours = Counter(r.ours for r in subset if r.ours)
        verdicts = Counter(r.verdict for r in subset if r.verdict)
        mismatches = sum(1 for r in subset if r.mismatch)
        lines.append(
            f"== {flavour}: {len(subset)} inputs, "
            f"{stages['convert-failed']} conversion failed, "
            f"{stages['validator-crash']} validator crashed, "
            f"{ours['pass']} approved, {ours['fail']} denied, "
            f"{ours['not_checked']} not_checked"
            + ''.join(
                f", {count} {stage}"
                for stage, count in sorted(stages.items())
                if stage not in ('validated', 'convert-failed', 'validator-crash')
            )
        )
        lines.append(
            f"   veraPDF: {verdicts[AGREE]} agree, "
            f"{verdicts[FALSE_APPROVAL]} FALSE-APPROVAL, "
            f"{verdicts[NO_RESULT]} NO-RESULT, "
            f"{verdicts[OVER_DENIAL]} over-denial, "
            f"{verdicts[NOT_CHECKED]} not-checked"
        )
        lines.append(f"   {mismatches} PREDICTION-MISMATCH")
        not_checked_vera = Counter(
            {True: 'pass', False: 'fail', None: 'no result'}[r.vera.compliant]
            for r in subset
            if r.verdict == NOT_CHECKED and r.vera is not None
        )
        if not_checked_vera:
            lines.append(
                "   not-checked by veraPDF: "
                + ', '.join(f"{n} {v}" for v, n in sorted(not_checked_vera.items()))
            )
        for verdict in (NOT_CHECKED, OVER_DENIAL):
            rules = top_rules(subset, verdict)
            if rules:
                lines.append(f"   top rules for {verdict}:")
                lines.extend(f"     {rule}" for rule in rules)
        shown = KEPT_VERDICTS if show_over_denials else FAILING_VERDICTS
        for record in subset:
            if record.stage == 'validator-crash':
                lines.append(f"   VALIDATOR-CRASH {record.label}")
                lines.append(f"       {record.error.strip().splitlines()[-1]}")
            if record.verdict in shown or (record.mismatch and record.verdict):
                lines.extend(_describe_record(record))
    return '\n'.join(lines)


def is_failure(records: Iterable[Record]) -> bool:
    """True if any record is a false approval, no-result or mismatch."""
    return any(r.verdict in FAILING_VERDICTS or r.mismatch for r in records)


def finish(records: list[Record], out_dir: Path, *, show_over_denials: bool) -> int:
    """Write ``results.json``, print the report and return the exit code."""
    with (out_dir / 'results.json').open('w') as f:
        json.dump([asdict(r) for r in records], f, indent=1)
    print(format_report(records, show_over_denials=show_over_denials))
    print(f"Results and kept candidates are in {out_dir}")
    return 1 if is_failure(records) else 0


def _output_dir(value: Path | None) -> Path:
    out = value or Path(tempfile.mkdtemp(prefix='pdfa-differential-'))
    out.mkdir(parents=True, exist_ok=True)
    return out


def _safe_name(relative: Path) -> str:
    return re.sub(r'[^A-Za-z0-9._-]+', '_', '__'.join(relative.parts))


# --- one -----------------------------------------------------------------


def cmd_one(args: argparse.Namespace) -> int:
    """Convert one PDF and show both validators' verdicts in detail."""
    out_dir = _output_dir(args.out)
    flavours = [normalize_flavour(f) for f in args.flavours] or ['2b']
    records = []
    for flavour in flavours:
        flavour_dir = out_dir / flavour
        flavour_dir.mkdir(exist_ok=True)
        candidate = flavour_dir / f'{args.pdf.stem}.candidate.pdf'
        _quiet_worker()
        record = convert_and_validate(
            args.pdf, candidate, flavour, str(args.pdf), args.via_save
        )
        compare_with_verapdf([record], flavour, candidate, check_denied=True)
        records.append(record)
        if record.ours is None:
            print(f"[{flavour}] ours: {record.stage.upper()} {record.error}")
        else:
            print(f"[{flavour}] predicted: {record.predicted.upper()}")  # type: ignore[union-attr]
            for finding in record.predicted_findings:
                print(f"     {finding}")
            print(f"[{flavour}] ours (written): {record.ours.upper()}")
            for finding in record.findings:
                print(f"     {finding}")
        if record.vera is not None:
            vera = {True: "PASS", False: "FAIL", None: "NO RESULT"}
            print(f"[{flavour}] veraPDF: {vera[record.vera.compliant]}")
            for rule in record.vera.failed_rules:
                print(f"     {rule}")
            if record.vera.compliant is None:
                print(f"     {record.vera.message}")
        print(f"[{flavour}] => {record.verdict or 'n/a'}; candidate {candidate}")
    with (out_dir / 'results.json').open('w') as f:
        json.dump([asdict(r) for r in records], f, indent=1)
    return 1 if is_failure(records) else 0


# --- corpus --------------------------------------------------------------


def corpus_records(
    sources: Sequence[Path],
    root: Path,
    flavour: str,
    out_dir: Path,
    *,
    workers: int,
    check_denied: bool = False,
    via_save: bool = False,
) -> list[Record]:
    """Convert and validate *sources* for *flavour*, then run veraPDF once.

    Candidates are written to ``out_dir/<flavour>/``; nothing is pruned.
    """
    flavour_dir = out_dir / flavour
    flavour_dir.mkdir(parents=True, exist_ok=True)
    jobs = [
        (
            source,
            flavour_dir / f'{_safe_name(source.relative_to(root).with_suffix(""))}.pdf',
            flavour,
            str(source.relative_to(root)),
            via_save,
        )
        for source in sources
    ]
    records = run_parallel(_convert_job, jobs, workers)
    compare_with_verapdf(records, flavour, flavour_dir, check_denied=check_denied)
    return records


def cmd_corpus(args: argparse.Namespace) -> int:
    """Convert every PDF under a directory and compare verdicts."""
    out_dir = _output_dir(args.out)
    root = args.directory.resolve()
    sources = sorted(p for p in root.rglob('*.pdf') if p.is_file())
    if args.limit:
        sources = sources[: args.limit]
    records: list[Record] = []
    for flavour in args.flavours:
        print(f"{flavour}: converting {len(sources)} files", file=sys.stderr)
        flavour_records = corpus_records(
            sources,
            root,
            flavour,
            out_dir,
            workers=args.jobs,
            check_denied=args.check_denied,
            via_save=args.via_save,
        )
        prune_candidates(flavour_records, keep_approved=args.keep_approved)
        records += flavour_records
    return finish(records, out_dir, show_over_denials=args.check_denied)


# --- fuzz ----------------------------------------------------------------

VALUES: list[Callable[[], Any]] = [
    lambda: Name('/Foo'),
    lambda: 0,
    lambda: 1,
    lambda: -1,
    lambda: 2**31,
    lambda: 2**31 - 1,
    lambda: 40000.0,
    lambda: 1e-40,
    lambda: String('x' * 40000),
    lambda: String(''),
    lambda: Array([]),
    lambda: Dictionary(),
    lambda: True,
    lambda: False,
    lambda: Name('/' + 'A' * 130),
    lambda: Name('/Identity'),
    lambda: Name('/None'),
    lambda: Name('/DeviceCMYK'),
    lambda: Name('/DeviceRGB'),
    lambda: Name('/DeviceGray'),
    lambda: 2,
    lambda: 3,
    lambda: 4,
    lambda: 8,
    lambda: 16,
    lambda: 0.5,
    lambda: Array([0, 0, 0, 0]),
    lambda: Array([Name('/FlateDecode')]),
    lambda: String('D:20200101120000'),
    lambda: String('2020-01-01T12:00:00Z'),
    lambda: Array([1, 2, 3]),
]

INSERT_KEYS = [
    '/OPI',
    '/Alternates',
    '/TR',
    '/TR2',
    '/HTP',
    '/SMask',
    '/BM',
    '/Interpolate',
    '/F',
    '/AA',
    '/OC',
    '/Ref',
    '/PS',
    '/Subtype2',
    '/EF',
    '/AF',
    '/CA',
    '/ca',
    '/Intent',
    '/RI',
    '/Encoding',
    '/Differences',
    '/CIDToGIDMap',
    '/CIDSet',
    '/CharSet',
    '/FontFile',
    '/FontFile3',
    '/Widths',
    '/FirstChar',
    '/LastChar',
    '/Flags',
    '/Alternate',
    '/N',
    '/Decode',
    '/Mask',
    '/ImageMask',
    '/BitsPerComponent',
    '/ColorSpace',
    '/Group',
    '/Resources',
    '/UserUnit',
    '/Rotate',
    '/MediaBox',
    '/CropBox',
    '/Version',
    '/Lang',
    '/Trapped',
    '/Title',
    '/Author',
    '/CreationDate',
    '/ModDate',
    '/Subtype',
    '/Type',
    '/BaseFont',
    '/DW',
    '/W',
    '/CIDSystemInfo',
    '/ToUnicode',
    '/WMode',
    '/UseCMap',
    '/CMapName',
    '/Popup',
    '/Parent',
    '/Rect',
    '/AP',
    '/AS',
    '/Contents',
    '/Annots',
    '/Metadata',
    '/OutputIntents',
    '/Length1',
    '/Length2',
    '/Length3',
    '/FontMatrix',
    '/FontBBox',
    '/CharProcs',
    '/Filter',
    '/DecodeParms',
    '/DL',
    '/Matte',
    '/SMaskInData',
    '/StructParent',
    '/IC',
    '/C',
    '/Border',
    '/BS',
    '/Dest',
    '/A',
    '/Next',
    '/S',
    '/D',
    '/URI',
]

CONTENT_SNIPPETS = [
    b' BX /Foo sh EX',
    b' 5 Tr',
    b' 99999 w',
    b' /DeviceCMYK cs 0 0 0 1 sc',
    b' 0 0 0 1 k',
    b' q ' * 30 + b' Q ' * 30,
    b' /GS0 gs',
    b' /Im99 Do',
    b' BT /F99 12 Tf (x) Tj ET',
    b' 1 0 0 RG',
    b' /Pattern cs /P0 scn',
    b' BT 7 Tr (x) Tj ET',
    b' /Foo ri',
    b' BI /W 1 /H 1 /BPC 8 /CS /RGB /F /LZW ID \x00\x00\x00 EI',
    b' BI /W 1 /H 1 /BPC 8 /CS /G /I true ID \x00 EI',
    b' /Span <</MCID 0>> BDC EMC',
    b' /OC /oc1 BDC EMC',
    b' 0.00000000000000000000000000000000000000001 w',
    b' 3.5e38 w',
    b' (' + b'x' * 33000 + b') Tj',
    b' /' + b'N' * 128 + b' gs',
    b' 2147483648 J',
    b' -2147483649 j',
    b' 32768 w',
    b' 32767.5 w',
    b' T* TL',
    b' 1 1 1 rg',
    b' /DeviceN cs',
    b' [/ICCBased 1 0 R] cs',
    b' d0',
    b' 1 0 0 1 0 0 d1',
    b' 0.5 g 0.5 G',
    b' /Cs1 cs 0.5 sc',
    b' BT <48455> Tj ET',
]

NUMBER_PERTURBATIONS: list[tuple[str, Callable[[Any], Any]]] = [
    ('negate', lambda x: -x),
    ('zero', lambda x: 0),
    ('double', lambda x: x * 2),
    ('increment', lambda x: x + 1),
    ('32768', lambda x: 32768),
    ('14401', lambda x: 14401),
    ('2.5', lambda x: 2.5),
    ('1e-39', lambda x: 1e-39),
]

MUTATION_KINDS = [
    'delete',
    'set',
    'set',
    'insert',
    'insert',
    'stream',
    'content',
    'number',
    'number',
    'trailer',
]


def _objects(pdf: pikepdf.Pdf) -> list[pikepdf.Object]:
    return [obj for obj in pdf.objects if isinstance(obj, (Dictionary, pikepdf.Stream))]


def _describe(value: Any) -> str:
    text = repr(value)
    return text if len(text) <= 80 else text[:77] + '...'


def _is_number(value: Any) -> bool:
    # pikepdf returns PDF integers as int and PDF reals as Decimal
    return isinstance(value, int | Decimal) and not isinstance(value, bool)


def _mutate_stream(obj: pikepdf.Stream, rng: random.Random) -> str | None:
    data = obj.read_bytes()
    op = rng.choice(['truncate', 'zero', 'random', 'flip', 'empty', 'double'])
    if op == 'truncate':
        data = data[: len(data) // 2]
    elif op == 'zero':
        data = b'\0' * len(data)
    elif op == 'random':
        data = bytes(rng.getrandbits(8) for _ in range(min(len(data), 4096)))
    elif op == 'flip':
        if not data:
            return None
        i = rng.randrange(len(data))
        data = data[:i] + bytes([data[i] ^ 0xFF]) + data[i + 1 :]
    elif op == 'empty':
        data = b''
    elif op == 'double':
        data += data
    obj.write(data)
    return (
        f"stream {op} in obj {obj.objgen} ({obj.get('/Type')}, {obj.get('/Subtype')})"
    )


def _mutate_content(pdf: pikepdf.Pdf, rng: random.Random) -> str | None:
    pageno = rng.randrange(len(pdf.pages))
    snippet = rng.choice(CONTENT_SNIPPETS)
    contents = pdf.pages[pageno].obj.get('/Contents')
    if isinstance(contents, Array) and len(contents):
        contents = contents[-1]
    if not isinstance(contents, pikepdf.Stream):
        return None
    where = rng.choice(['append', 'prepend'])
    data = contents.read_bytes()
    contents.write(data + snippet if where == 'append' else snippet + b' ' + data)
    return f"content {where} {snippet[:60]!r} on page {pageno + 1}"


def mutate(pdf: pikepdf.Pdf, rng: random.Random) -> str | None:
    """Apply one random mutation to *pdf*.

    Returns:
        A description of the mutation, or None if the chosen mutation could
        not be applied to this file.
    """
    objs = _objects(pdf)
    if not objs:
        return None
    kind = rng.choice(MUTATION_KINDS)
    obj = rng.choice(objs)
    keys = sorted(obj.keys())
    if isinstance(obj, pikepdf.Stream):
        # pikepdf refuses to delete or replace a stream's /Length
        keys = [k for k in keys if k != '/Length']
    if kind == 'delete' and keys:
        key = rng.choice(keys)
        del obj[key]
        return f"delete {key} from obj {obj.objgen}"
    if kind in ('set', 'insert'):
        if kind == 'set' and not keys:
            return None
        key = rng.choice(keys if kind == 'set' else INSERT_KEYS)
        value = rng.choice(VALUES)()
        if isinstance(obj, pikepdf.Stream) and key == '/Length':
            return None
        obj[key] = value
        return f"{kind} {key} = {_describe(value)} in obj {obj.objgen}"
    if kind == 'stream' and isinstance(obj, pikepdf.Stream):
        return _mutate_stream(obj, rng)
    if kind == 'content' and len(pdf.pages):
        return _mutate_content(pdf, rng)
    if kind == 'number':
        numeric = [k for k in keys if _is_number(obj.get(k))]
        if not numeric:
            return None
        key = rng.choice(numeric)
        old: Any = obj.get(key)
        old_value = old if isinstance(old, int) else float(old)
        name, perturb = rng.choice(NUMBER_PERTURBATIONS)
        new = perturb(old_value)
        obj[key] = new
        return f"number {name} {key}: {old_value} -> {new} in obj {obj.objgen}"
    if kind == 'trailer':
        key = rng.choice(['/Info', '/ID', '/Encrypt', '/Root'])
        value = rng.choice(VALUES)()
        pdf.trailer[key] = value
        return f"trailer {key} = {_describe(value)}"
    return None


def mutant_rng(seed: int, seed_name: str, index: int) -> random.Random:
    """Random generator for one mutant, independent of every other mutant."""
    return random.Random(f'{seed}:{seed_name}:{index}')


def fuzz_one(job: tuple[Path, int, int, str, Path]) -> Record:
    """Create one mutant of a seed file, convert it and validate it.

    The random generator is seeded from the global seed, the seed file's
    name and the mutant index, so every mutant can be reproduced on its own.
    """
    seed_file, index, seed, flavour, out_dir = job
    label = f'{seed_file.name}#{index}'
    mutant = out_dir / f'{seed_file.stem}.m{index}.pdf'
    candidate = out_dir / f'{seed_file.stem}.m{index}.cand.pdf'
    rng = mutant_rng(seed, seed_file.name, index)
    record = Record(flavour, label, None)
    try:
        with pikepdf.open(seed_file) as pdf:
            description = mutate(pdf, rng)
            if description is None:
                record.stage = 'skipped'
                return record
            record.label = f'{label}: {description}'
            pdf.save(mutant)
    except Exception as e:  # noqa: BLE001
        record.stage = 'mutate-failed'
        record.error = f"{type(e).__name__}: {e}"[:300]
        mutant.unlink(missing_ok=True)
        return record
    try:
        return convert_and_validate(mutant, candidate, flavour, record.label)
    finally:
        mutant.unlink(missing_ok=True)


def cmd_fuzz(args: argparse.Namespace) -> int:
    """Mutate seed PDFs, convert the mutants and compare verdicts."""
    out_dir = _output_dir(args.out)
    seeds = sorted(args.candidate_dir.glob('*.pdf'))
    if not seeds:
        print(f"No PDFs in {args.candidate_dir}", file=sys.stderr)
        return 2
    records: list[Record] = []
    for flavour in args.flavours:
        flavour_dir = out_dir / flavour
        flavour_dir.mkdir(exist_ok=True)
        jobs = [
            (seed_file, i, args.seed, flavour, flavour_dir)
            for seed_file in seeds
            for i in range(args.per_file)
        ]
        print(f"{flavour}: {len(jobs)} mutants", file=sys.stderr)
        flavour_records = run_parallel(fuzz_one, jobs, args.jobs)
        compare_with_verapdf(flavour_records, flavour, flavour_dir)
        prune_candidates(flavour_records, keep_approved=False)
        records += flavour_records
    mutations = {
        'seed': args.seed,
        'per_file': args.per_file,
        'candidate_dir': str(args.candidate_dir),
        'mutants': [
            {'flavour': r.flavour, 'mutation': r.label, 'stage': r.stage}
            for r in records
        ],
    }
    with (out_dir / 'mutations.json').open('w') as f:
        json.dump(mutations, f, indent=1)
    return finish(records, out_dir, show_over_denials=False)


# --- Command line --------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    """Build the command line parser."""
    parser = argparse.ArgumentParser(
        description=(
            "Compare pikepdf's PDF/A validator with veraPDF on candidates "
            "made by pikepdf.pdfa.prepare. Exits with status 1 if pikepdf "
            "approved anything veraPDF rejects or cannot validate, or if a "
            "predicted verdict differs from the verdict on the written file."
        ),
    )
    sub = parser.add_subparsers(dest='command', required=True)

    def common(p: argparse.ArgumentParser) -> None:
        p.add_argument(
            '--out',
            type=Path,
            help="output directory for results.json and kept candidates "
            "(default: a new temporary directory)",
        )

    def via_save(p: argparse.ArgumentParser) -> None:
        p.add_argument(
            '--via-save',
            action='store_true',
            help="write candidates with pikepdf.pdfa.save (denied candidates "
            "are then not written, so veraPDF cannot check them)",
        )

    def batch(p: argparse.ArgumentParser, default_flavours: str) -> None:
        common(p)
        p.add_argument(
            '--flavours',
            type=parse_flavours,
            default=parse_flavours(default_flavours),
            help=f"comma-separated PDF/A flavours (default: {default_flavours})",
        )
        p.add_argument(
            '-j',
            '--jobs',
            type=int,
            default=os.cpu_count() or 1,
            help="worker processes for conversion and validation",
        )

    one = sub.add_parser(
        'one', help="check one file in detail", description=cmd_one.__doc__
    )
    one.add_argument('pdf', type=Path, help="input PDF")
    one.add_argument('flavours', nargs='*', help="flavours such as 1b 2b 3b")
    common(one)
    via_save(one)
    one.set_defaults(func=cmd_one)

    corpus = sub.add_parser(
        'corpus',
        help="check every PDF under a directory",
        description=cmd_corpus.__doc__,
    )
    corpus.add_argument('directory', type=Path, help="e.g. a veraPDF-corpus checkout")
    batch(corpus, '1b,2b,3b')
    via_save(corpus)
    corpus.add_argument(
        '--keep-approved',
        action='store_true',
        help="keep every approved candidate, e.g. as seeds for fuzz",
    )
    corpus.add_argument(
        '--check-denied',
        action='store_true',
        help="also run veraPDF on denied and not_checked candidates and list "
        "over-denials",
    )
    corpus.add_argument('--limit', type=int, help="only the first N files")
    corpus.set_defaults(func=cmd_corpus)

    fuzz = sub.add_parser(
        'fuzz',
        help="mutate approved candidates and compare verdicts on the mutants",
        description=(
            "Apply seeded random mutations to each PDF in CANDIDATE_DIR, "
            "convert each mutant to a PDF/A candidate and compare verdicts. "
            "The mutation applied to each mutant is recorded in "
            "mutations.json; a mutant is reproducible from its seed, file "
            "name and index."
        ),
    )
    fuzz.add_argument('candidate_dir', type=Path, help="directory of seed PDFs")
    batch(fuzz, '2b')
    fuzz.add_argument('--seed', type=int, default=0, help="random seed")
    fuzz.add_argument('--per-file', type=int, default=10, help="mutants per seed file")
    fuzz.set_defaults(func=cmd_fuzz)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Run the command line."""
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == '__main__':
    sys.exit(main())
