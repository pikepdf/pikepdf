# SPDX-FileCopyrightText: 2026 James R. Barlow
# SPDX-License-Identifier: MPL-2.0

"""Differential tests of the PDF/A validator against veraPDF.

The corpus test needs veraPDF and a checkout of
https://github.com/veraPDF/veraPDF-corpus named by the environment variable
``PIKEPDF_VERAPDF_CORPUS``. The other tests check the differential script
``misc/pdfa_differential.py`` itself and need neither.
"""

from __future__ import annotations

import pytest

pytest.importorskip('jsonschema')

import importlib  # noqa: E402
import json  # noqa: E402
import os  # noqa: E402
import re  # noqa: E402
import sys  # noqa: E402
import warnings  # noqa: E402
from pathlib import Path  # noqa: E402

from conftest import verapdf_command  # noqa: E402

import pikepdf  # noqa: E402
from pikepdf import pdfa  # noqa: E402

SCRIPT = Path(__file__).parent.parent / 'misc' / 'pdfa_differential.py'
RESOURCES = Path(__file__).parent / 'resources'


def _load_script():
    # Import by module name from a sys.path entry, rather than from a file
    # location, so that worker processes started with spawn or forkserver
    # can import it too.
    if str(SCRIPT.parent) not in sys.path:
        sys.path.append(str(SCRIPT.parent))
    return importlib.import_module(SCRIPT.stem)


diff = _load_script()

# Corpus files (relative to the corpus root) whose candidates the validator
# approves although veraPDF rejects them, with the reason.
KNOWN_DISAGREEMENTS: dict[str, str] = {}

CORPUS_ENV = 'PIKEPDF_VERAPDF_CORPUS'


@pytest.fixture
def verapdf_corpus() -> Path:
    value = os.environ.get(CORPUS_ENV)
    if not value or not Path(value).is_dir():
        pytest.skip(f"set {CORPUS_ENV} to a veraPDF-corpus checkout")
    if verapdf_command() is None:
        pytest.skip("veraPDF not available")
    return Path(value)


def _corpus_sources(root: Path, flavour: str) -> list[Path]:
    """Corpus files to convert to *flavour*."""
    dirs = {
        '1b': ['PDF_A-1b', 'Isartor test files'],
        '2b': ['PDF_A-2b'],
        '3b': ['PDF_A-3b'],
    }[flavour]
    sources = [p for d in dirs for p in (root / d).rglob('*.pdf')]
    part = flavour[0]
    sources += [
        p
        for p in (root / 'TWG test files').glob('*.pdf')
        if re.search(rf'pdfa{part}-', p.name)
    ]
    return sorted(sources)


@pytest.mark.slow
@pytest.mark.parametrize('flavour', ['1b', '2b', '3b'])
def test_no_false_approvals_on_verapdf_corpus(flavour, tmp_path, verapdf_corpus):
    """Approvals must agree with veraPDF and predictions with the saved file."""
    root = verapdf_corpus
    sources = _corpus_sources(root, flavour)
    assert sources, f"no corpus files found for {flavour} under {root}"

    workers = max(1, (os.cpu_count() or 2) // 2)
    records = diff.corpus_records(sources, root, flavour, tmp_path, workers=workers)

    crashes = [r.label for r in records if r.stage == 'validator-crash']
    assert not crashes, f"validator crashed on {crashes}"
    unexpected = []
    for record in records:
        if record.verdict in diff.FAILING_VERDICTS or record.mismatch:
            if record.label not in KNOWN_DISAGREEMENTS:
                if record.mismatch:
                    detail = (
                        f"predicted {record.predicted} {record.predicted_rules}, "
                        f"written {record.ours} {record.rules}"
                    )
                else:
                    assert record.vera is not None
                    detail = str(record.vera.failed_rules or [record.vera.message])
                unexpected.append(f"{record.verdict} {record.label}: {detail}")
        elif record.label in KNOWN_DISAGREEMENTS and record.verdict:
            warnings.warn(
                f"{record.label} now agrees with veraPDF for {flavour}; "
                "remove it from KNOWN_DISAGREEMENTS",
                stacklevel=1,
            )
    assert not unexpected, '\n'.join(unexpected)


# veraPDF 1.30 output for a compliant file, a non-compliant file and a file
# it could not parse, run as ``verapdf -f 1b --format json -r <dir>``.
VERAPDF_REPORT = r"""
{"report": {"jobs": [
  {"itemDetails": {"name": "/tmp/fixture/pass.pdf", "size": 23159},
   "validationResult": [{"details": {"passedRules": 129, "failedRules": 0,
     "passedChecks": 401, "failedChecks": 0, "ruleSummaries": []},
     "jobEndStatus": "normal", "profileName": "PDF/A-1b validation profile",
     "statement": "PDF file is compliant with Validation Profile requirements.",
     "compliant": true}]},
  {"itemDetails": {"name": "/tmp/fixture/fail.pdf", "size": 23163},
   "validationResult": [{"details": {"passedRules": 128, "failedRules": 1,
     "passedChecks": 400, "failedChecks": 1, "ruleSummaries": [
       {"ruleStatus": "FAILED", "specification": "ISO 19005-1:2005",
        "clause": "6.1.12", "testNumber": 2, "status": "failed",
        "failedChecks": 1,
        "description": "Absolute real value must be less than or equal to 32767.0",
        "object": "CosReal",
        "test": "(realValue >= -32767.0) && (realValue <= 32767.0)",
        "checks": [{"status": "failed",
          "context": "root/document[0]/pages[0](7 0 obj PDPage)/contentStream[0](10 0 obj PDContentStream)/operators[4]/scale[0]",
          "errorMessage": "Real value 60000.1 out of range",
          "errorArguments": ["60000.1"]}]}]},
     "jobEndStatus": "normal", "profileName": "PDF/A-1b validation profile",
     "statement": "PDF file is not compliant with Validation Profile requirements.",
     "compliant": false}]},
  {"itemDetails": {"name": "/tmp/fixture/broken.pdf", "size": 17},
   "taskException": {"exception": "Couldn't parse stream", "type": "PARSE",
     "executed": true, "success": false,
     "exceptionMessage": "Exception: Couldn't parse stream caused by exception: Document doesn't contain startxref keyword"}}
 ],
 "batchSummary": {"totalJobs": 3, "failedParsingJobs": 1}}}
"""


def test_parse_verapdf_report():
    results = diff.parse_verapdf_report(json.loads(VERAPDF_REPORT))
    assert set(results) == {
        '/tmp/fixture/pass.pdf',
        '/tmp/fixture/fail.pdf',
        '/tmp/fixture/broken.pdf',
    }
    passed = results['/tmp/fixture/pass.pdf']
    assert passed.compliant is True
    assert passed.failed_rules == []

    failed = results['/tmp/fixture/fail.pdf']
    assert failed.compliant is False
    assert failed.failed_rules == ['6.1.12-2']

    broken = results['/tmp/fixture/broken.pdf']
    assert broken.compliant is None
    assert 'startxref' in broken.message


@pytest.mark.parametrize(
    'ours, compliant, verdict',
    [
        ('pass', True, 'agree'),
        ('fail', False, 'agree'),
        ('pass', False, 'false-approval'),
        ('pass', None, 'no-result'),
        ('fail', None, 'agree'),
        ('fail', True, 'over-denial'),
        ('not_checked', True, 'not-checked'),
        ('not_checked', False, 'not-checked'),
        ('not_checked', None, 'not-checked'),
    ],
)
def test_classify(ours, compliant, verdict):
    assert diff.classify(ours, diff.VeraResult(compliant)) == verdict


def _finding(rule: str, kind: str = 'violation') -> pdfa.Finding:
    return pdfa.Finding(rule, 'obj 1 0', 'message', kind)  # type: ignore[arg-type]


def _report(*findings: pdfa.Finding) -> pdfa.Report:
    return pdfa.Report(pdfa.Flavour('2b'), list(findings))


def test_prediction_mismatch():
    a = _finding('ISO_19005_2:6.2.2-1')
    b = _finding('ISO_19005_2:6.2.4.3-2')
    assert not diff.prediction_mismatch(_report(), _report())
    assert not diff.prediction_mismatch(_report(a, b), _report(b, a))
    assert diff.prediction_mismatch(_report(), _report(a))
    assert diff.prediction_mismatch(_report(a), _report(b))
    unsupported = _finding('ISO_19005_2:6.2.2-1', 'unsupported')
    assert diff.prediction_mismatch(_report(a), _report(unsupported))


@pytest.mark.parametrize(
    'ours, compliant, mismatch, verdict',
    [
        ('pass', True, True, 'prediction-mismatch'),
        ('fail', True, True, 'prediction-mismatch'),
        ('pass', False, True, 'false-approval'),
        ('pass', None, True, 'no-result'),
        ('fail', None, False, 'agree'),
    ],
)
def test_settle_with_verapdf(ours, compliant, mismatch, verdict):
    record = diff.Record('2b', 'x.pdf', None, 'validated', ours=ours)
    record.mismatch = mismatch
    record.vera = diff.VeraResult(compliant)
    diff.settle(record)
    assert record.verdict == verdict


@pytest.mark.parametrize(
    'ours, mismatch, verdict',
    [
        ('fail', False, ''),
        ('fail', True, 'prediction-mismatch'),
        ('not_checked', False, 'not-checked'),
        (None, True, ''),
    ],
)
def test_settle_without_verapdf(ours, mismatch, verdict):
    record = diff.Record('2b', 'x.pdf', None, ours=ours)
    record.mismatch = mismatch
    diff.settle(record)
    assert record.verdict == verdict


def test_report_lists_disagreements():
    vera_fail = diff.VeraResult(False, ['6.1.6-1'])
    records = [
        diff.Record(
            '2b', 'good.pdf', None, 'validated', 'pass', 'pass', verdict='agree'
        ),
        diff.Record(
            '2b',
            'bad.pdf',
            '/out/2b/bad.pdf',
            'validated',
            'pass',
            'pass',
            vera=vera_fail,
            verdict='false-approval',
        ),
        diff.Record(
            '2b',
            'drift.pdf',
            None,
            'validated',
            'pass',
            'fail',
            rules=['ISO_19005_2:6.1.3-1'],
            mismatch=True,
            verdict='prediction-mismatch',
        ),
        diff.Record(
            '2b',
            'odd.pdf',
            None,
            'validated',
            'not_checked',
            'not_checked',
            rules=['pikepdf:internal'],
            vera=diff.VeraResult(True),
            verdict='not-checked',
        ),
        diff.Record(
            '2b',
            'strict.pdf',
            None,
            'validated',
            'fail',
            'fail',
            rules=['ISO_19005_2:6.2.2-1'],
            vera=diff.VeraResult(True),
            verdict='over-denial',
        ),
        diff.Record('2b', 'broken.pdf', None, 'convert-failed'),
    ]
    text = diff.format_report(records, show_over_denials=False)
    assert "2b: 6 inputs, 1 conversion failed" in text
    assert "2 approved, 2 denied, 1 not_checked" in text
    assert "1 agree, 1 FALSE-APPROVAL, 0 NO-RESULT, 1 over-denial" in text
    assert "1 PREDICTION-MISMATCH" in text
    assert "FALSE-APPROVAL bad.pdf" in text
    assert "6.1.6-1" in text
    assert "PREDICTION-MISMATCH drift.pdf" in text
    assert "not-checked by veraPDF: 1 pass" in text
    assert re.search(r"top rules for not-checked:\n\s+1 pikepdf:internal", text)
    assert re.search(r"top rules for over-denial:\n\s+1 ISO_19005_2:6.2.2-1", text)
    assert "good.pdf" not in text
    assert "OVER-DENIAL strict.pdf" not in text
    assert diff.is_failure(records)
    assert not diff.is_failure(records[:1] + records[3:])

    text = diff.format_report(records, show_over_denials=True)
    assert "OVER-DENIAL strict.pdf" in text


def test_convert_and_validate(tmp_path):
    candidate = tmp_path / 'graph.pdf'
    record = diff.convert_and_validate(
        RESOURCES / 'graph.pdf', candidate, '2b', 'graph.pdf'
    )
    assert record.stage == 'validated'
    assert record.predicted == record.ours == 'pass'
    assert not record.mismatch
    assert record.verdict == ''
    assert record.candidate == str(candidate)
    with pikepdf.open(candidate) as pdf:
        assert pdf.open_metadata().pdfa_status == '2B'


def test_convert_failure_is_recorded(tmp_path):
    source = tmp_path / 'broken.pdf'
    source.write_bytes(b'not a pdf')
    record = diff.convert_and_validate(source, tmp_path / 'out.pdf', '2b', 'broken.pdf')
    assert record.stage == 'convert-failed'
    assert record.candidate is None
    assert record.ours is None
    assert not (tmp_path / 'out.pdf').exists()


def test_mutations_are_reproducible():
    def mutations(seed: int) -> list[str | None]:
        descriptions = []
        for i in range(20):
            rng = diff.mutant_rng(seed, 'graph.pdf', i)
            with pikepdf.open(RESOURCES / 'graph.pdf') as pdf:
                descriptions.append(diff.mutate(pdf, rng))
        return descriptions

    first = mutations(1)
    assert first == mutations(1)
    assert first != mutations(2)
    assert any(first)


def test_fuzz_one(tmp_path):
    seed_file = RESOURCES / 'graph.pdf'
    records = [diff.fuzz_one((seed_file, i, 0, '2b', tmp_path)) for i in range(4)]
    for record in records:
        assert record.stage in (
            'validated',
            'skipped',
            'mutate-failed',
            'convert-failed',
        )
        assert record.stage != 'validator-crash'
    validated = [r for r in records if r.stage == 'validated']
    assert validated
    assert all(r.label.startswith('graph.pdf#') for r in records)
    # Mutants are removed; only candidates remain
    assert not list(tmp_path.glob('*.m?.pdf'))
