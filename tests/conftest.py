# SPDX-FileCopyrightText: 2022 James R. Barlow
# SPDX-License-Identifier: CC0-1.0

from __future__ import annotations

import functools
import json
import os
import platform
import shutil
import subprocess
import sys
import tempfile
import time
import xml.etree.ElementTree as ET
from pathlib import Path

from packaging.version import Version

try:
    from pikepdf import __libqpdf_version__
except ImportError:
    __libqpdf_version__ = '0.0.0'


import pytest

TESTS_ROOT = os.path.abspath(os.path.dirname(__file__))
PROJECT_ROOT = os.path.dirname(TESTS_ROOT)


@pytest.fixture(scope="session")
def resources():
    return Path(TESTS_ROOT) / 'resources'


@pytest.fixture(scope="function")
def outdir(tmp_path):
    return tmp_path


@pytest.fixture(scope="function")
def outpdf(tmp_path):
    return tmp_path / 'out.pdf'


@pytest.fixture
def refcount():
    if platform.python_implementation() == 'PyPy':
        pytest.skip(reason="test isn't valid for PyPy")
    return sys.getrefcount


skip_if_pypy = pytest.mark.skipif(
    platform.python_implementation() == 'PyPy', reason="test isn't valid for PyPy"
)
fails_if_pypy = pytest.mark.xfail(
    platform.python_implementation() == 'PyPy', reason="test known to fail on PyPy"
)
skip_if_ci = pytest.mark.skipif(
    os.environ.get('CI', '') == 'true', reason="test too slow for CI"
)
fails_if_no_mutool = pytest.mark.xfail(
    shutil.which("mutool") is None, reason="test fails without mutool"
)


def needs_libqpdf_v(version: str, *, reason=None):
    if reason is None:
        reason = "installed libqpdf is too old for this test"
    return pytest.mark.skipif(
        Version(__libqpdf_version__) <= Version(version),
        reason=reason,
    )


def needs_python_v(version: str, *, reason=None):
    if reason is None:
        reason = "only works on newer Python versions"
    return pytest.mark.skipif(
        Version(platform.python_version()) <= Version(version), reason=reason
    )


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


def verapdf_validate(filename) -> bool:
    """Return True if veraPDF finds *filename* compliant with the PDF/A it claims."""
    command = verapdf_command()
    assert command
    proc = subprocess.run(
        [*command, os.fspath(filename)],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=True,
    )
    result = proc.stdout.decode('utf-8')
    xml_start = result.find('<?xml version')
    xml = result[xml_start:]
    root = ET.fromstring(xml)
    node = root.find(".//validationReport")
    if node is None:
        raise NotImplementedError("Unexpected XML returned by verapdf")

    compliant = node.attrib['isCompliant'] == 'true'
    if not compliant:
        print(result)
    return compliant


def verapdf_failed_rules(path, flavour: str) -> set[str] | None:
    """Return the ids of the veraPDF rules *path* fails, or None without veraPDF.

    Ids have the form ``ISO_19005_2:6.2.2-2``.
    """
    command = verapdf_command()
    if command is None:
        return None
    proc = subprocess.run(
        [*command, '--format', 'json', '-f', flavour, os.fspath(path)],
        capture_output=True,
        text=True,
        check=False,
    )
    result = json.loads(proc.stdout)['report']['jobs'][0]['validationResult'][0]
    return {
        f"ISO_19005_{flavour[0]}:{rule['clause']}-{rule['testNumber']}"
        for rule in result['details']['ruleSummaries']
        if rule.get('ruleStatus', 'FAILED') == 'FAILED'
    }


@pytest.fixture
def verapdf():
    if verapdf_command() is None:
        pytest.skip("verapdf not available")
    return verapdf_validate


@pytest.fixture
def los_angeles_tz(monkeypatch):
    """Make America/Los_Angeles the local time zone for the test.

    Skipped where time.tzset() is unavailable (Windows), since the local zone
    cannot be changed from within the process there.
    """
    if not hasattr(time, 'tzset'):
        pytest.skip("time.tzset() is not available on this platform")
    monkeypatch.setenv('TZ', 'America/Los_Angeles')
    time.tzset()
    yield
    monkeypatch.undo()
    time.tzset()


@pytest.fixture(autouse=True)
def _pdfa_explicit_conversion(request):
    """Run the PDF/A tests in explicit conversion mode.

    pikepdf.pdfa works in explicit mode: its entry points switch to it, and
    its internals, which many tests call directly, expect it. Every test in
    a ``test_pdfa*`` module runs inside `pikepdf.explicit_conversion`, which
    affects only the thread running the test; test_pdfa_explicit.py checks
    the entry points from implicit mode.
    """
    module = request.node.module
    if module is None:
        yield
        return
    if not module.__name__.rpartition('.')[2].startswith('test_pdfa'):
        yield
        return
    import pikepdf

    with pikepdf.explicit_conversion():
        yield
