# SPDX-FileCopyrightText: 2026 James R. Barlow
# SPDX-License-Identifier: CC0-1.0

"""Guard the third-party license attribution shipped in binary wheels.

pikepdf wheels vendor compiled third-party libraries (qpdf, libjpeg-turbo,
OpenSSL, the GnuTLS stack, ...) that auditwheel/delocate/delvewheel copy in.
Their licenses have to travel with the wheel. That declaration lived in
setup.cfg's `license_files` until the move to pyproject.toml silently dropped
it, and the omission went unnoticed for years because nothing checked. These
tests are that check.

They deliberately run against the repository source rather than an installed
distribution, so they hold in an editable dev install where no wheel exists.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

try:
    import tomllib
except ModuleNotFoundError:
    import tomli as tomllib  # type: ignore

REPO_ROOT = Path(__file__).parent.parent
THIRD_PARTY = REPO_ROOT / 'third-party-licenses'

pytestmark = pytest.mark.skipif(
    not (REPO_ROOT / 'pyproject.toml').is_file(),
    reason="not running from a source checkout",
)


@pytest.fixture(scope='module')
def pyproject():
    with open(REPO_ROOT / 'pyproject.toml', 'rb') as f:
        return tomllib.load(f)


@pytest.fixture(scope='module')
def license_files(pyproject):
    """Every file matched by the PEP 639 license-files globs."""
    patterns = pyproject['project']['license-files']
    return {
        path.relative_to(REPO_ROOT)
        for pattern in patterns
        for path in REPO_ROOT.glob(pattern)
        if path.is_file()
    }


def test_license_files_declared(pyproject):
    # PEP 639 license-files must be declared explicitly. Relying on the build
    # backend's default glob is what let licenses-for-wheels.txt end up in
    # Windows wheels only: the default pattern LICEN[CS]E* matched it on
    # case-insensitive filesystems and nowhere else.
    assert 'license-files' in pyproject['project']
    assert pyproject['project']['license'] == 'MPL-2.0'


def test_every_license_glob_matches_something(pyproject):
    for pattern in pyproject['project']['license-files']:
        matched = [p for p in REPO_ROOT.glob(pattern) if p.is_file()]
        assert matched, f"license-files pattern {pattern!r} matches no files"


def test_own_license_included(license_files):
    assert Path('LICENSE.txt') in license_files


def test_third_party_licenses_included(license_files):
    # Each license text in third-party-licenses/ must actually ship. A text
    # that exists in the repo but is not covered by license-files would not
    # reach the wheel, which is the failure mode this whole directory exists
    # to prevent.
    on_disk = {p.relative_to(REPO_ROOT) for p in THIRD_PARTY.iterdir() if p.is_file()}
    assert on_disk, "third-party-licenses/ is empty"
    assert on_disk <= license_files, (
        f"not shipped in wheels: {sorted(map(str, on_disk - license_files))}"
    )


def test_readme_references_resolve():
    # The mapping from component to license text is only useful if every text
    # it names is really there.
    readme = THIRD_PARTY / 'README.md'
    body = readme.read_text(encoding='utf-8')
    referenced = set(re.findall(r'\]\((?!https?:)([^)#]+)\)', body))
    assert referenced, "README.md links no license texts"
    missing = sorted(name for name in referenced if not (THIRD_PARTY / name).is_file())
    assert not missing, f"README.md references missing files: {missing}"


def test_every_license_text_is_documented():
    # ...and conversely, a text nobody explains is attribution without a
    # mapping, which is exactly what issue #736 asked us to fix.
    readme = THIRD_PARTY / 'README.md'
    body = readme.read_text(encoding='utf-8')
    undocumented = sorted(
        p.name
        for p in THIRD_PARTY.iterdir()
        if p.is_file() and p != readme and p.name not in body
    )
    assert not undocumented, f"license texts not mentioned in README.md: {undocumented}"


def test_obsolete_combined_license_file_is_gone():
    # Superseded by third-party-licenses/. It was stale (no OpenSSL, zlib, or
    # GnuTLS entries) and shipped inconsistently across platforms.
    assert not (REPO_ROOT / 'licenses-for-wheels.txt').exists()


def test_sdist_excludes_vendored_qpdf_source(pyproject):
    # CI unpacks qpdf's source tree into ./qpdf to build libqpdf. It is a build
    # prerequisite, not pikepdf source, and sweeping it into the sdist made an
    # MPL-2.0 sdist carry ~2900 files of Apache-2.0 code.
    assert 'qpdf' in pyproject['tool']['scikit-build']['sdist']['exclude']
