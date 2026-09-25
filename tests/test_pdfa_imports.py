# SPDX-FileCopyrightText: 2026 James R. Barlow
# SPDX-License-Identifier: MPL-2.0

"""pikepdf.pdfa is optional: lazy import, clear errors, and thread use."""

from __future__ import annotations

import subprocess
import sys
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

import pikepdf

RESOURCES = Path(__file__).parent / 'resources' / 'pdfa'


@pytest.mark.abi3_smoke
def test_import_pikepdf_does_not_load_pdfa():
    code = r"""
import sys
import pikepdf

for mod in sys.modules:
    if mod == 'pikepdf.pdfa' or mod.startswith(
        ('pikepdf.pdfa.', 'jsonschema', 'referencing', 'fontTools')
    ):
        raise SystemExit(f"eager import detected: {mod}")
print("OK")
"""
    result = subprocess.run(
        [sys.executable, '-c', code], capture_output=True, text=True, check=False
    )
    assert result.returncode == 0, result.stderr or result.stdout


def test_pdfa_reachable_as_attribute():
    pytest.importorskip('jsonschema')
    pytest.importorskip('fontTools')
    module = pikepdf.pdfa
    assert module.__name__ == 'pikepdf.pdfa'
    assert callable(module.check)


def test_from_pikepdf_import_pdfa():
    pytest.importorskip('jsonschema')
    pytest.importorskip('fontTools')
    from pikepdf import pdfa

    assert pdfa is sys.modules['pikepdf.pdfa']
    assert pdfa.Flavour('2b') is pdfa.Flavour.PDFA_2B


def test_missing_dependency_names_the_extra(monkeypatch):
    pytest.importorskip('jsonschema')
    pytest.importorskip('fontTools')
    from pikepdf.pdfa import _deps

    real_find_spec = _deps.find_spec

    def find_spec(name, *args, **kwargs):
        if name == 'fontTools':
            return None
        return real_find_spec(name, *args, **kwargs)

    monkeypatch.setattr(_deps, 'find_spec', find_spec)
    with pytest.raises(ImportError, match=r"pikepdf\[pdfa\]") as excinfo:
        _deps.require()
    assert 'fontTools' in str(excinfo.value)
    assert excinfo.value.name == 'fontTools'


def test_check_in_threads():
    pytest.importorskip('jsonschema')
    pytest.importorskip('fontTools')
    from pikepdf import pdfa

    n_threads = 8
    barrier = threading.Barrier(n_threads)

    def work(_index: int):
        with pikepdf.open(RESOURCES / 'francais.pdf') as pdf:
            barrier.wait()
            before = pdfa.check(pdf, '2b')
            pdfa.prepare(pdf, '2b')
            after = pdfa.check(pdf, '2b')
            return (
                before.verdict,
                [(f.rule, f.kind) for f in before.findings],
                after.verdict,
                after.findings,
            )

    with ThreadPoolExecutor(max_workers=n_threads) as pool:
        results = list(pool.map(work, range(n_threads)))

    assert results[0][0] == 'fail'
    assert results[0][2] == 'pass'
    assert all(result == results[0] for result in results)
