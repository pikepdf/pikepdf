# SPDX-FileCopyrightText: 2025 James R. Barlow
# SPDX-License-Identifier: CC0-1.0

"""Tests for the release helper in bin/bump_version.py."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

pytest.importorskip("cyclopts")
pytest.importorskip("packaging")

BUMP_VERSION_PATH = Path(__file__).parent.parent / "bin" / "bump_version.py"

if not BUMP_VERSION_PATH.exists():
    pytest.skip("bin/bump_version.py not available", allow_module_level=True)


def _load_bump_version():
    spec = importlib.util.spec_from_file_location(
        "bump_version_under_test", BUMP_VERSION_PATH
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


bump_version = _load_bump_version()


@pytest.mark.parametrize(
    'entered, expected',
    [
        ('10.13.0', '10.13.0'),
        ('10.13.0.post1', '10.13.0.post1'),
        ('10.13.0-post1', '10.13.0.post1'),
        ('10.13.0-1', '10.13.0.post1'),
        ('10.14.0rc1', '10.14.0rc1'),
        ('10.14.0-rc1', '10.14.0rc1'),
        ('10.14.0.RC1', '10.14.0rc1'),
        ('  10.14.0b2  ', '10.14.0b2'),
        ('10.14.0.dev3', '10.14.0.dev3'),
        ('v10.13.0', '10.13.0'),
        ('10.13.0.post', '10.13.0.post0'),
    ],
)
def test_normalize_version(entered, expected):
    assert bump_version.normalize_version(entered) == expected


@pytest.mark.parametrize(
    'entered', ['', 'not-a-version', '10.13.0.postX', '10.13.0 final']
)
def test_normalize_version_rejects_invalid(entered):
    with pytest.raises(bump_version.InvalidVersion):
        bump_version.normalize_version(entered)


@pytest.mark.parametrize(
    'version, expected',
    [
        ('10.13.0', ['10.13.0']),
        ('10.13.0.post1', ['10.13.0.post1', '10.13.0']),
        ('10.14.0rc1', ['10.14.0rc1', '10.14.0']),
        ('10.14.0.dev3', ['10.14.0.dev3', '10.14.0']),
        ('10.14rc1', ['10.14rc1', '10.14.0']),
    ],
)
def test_release_notes_candidates(version, expected):
    assert bump_version.release_notes_candidates(version) == expected


@pytest.fixture
def release_notes(tmp_path: Path) -> Path:
    notes = tmp_path / 'docs' / 'releasenotes'
    notes.mkdir(parents=True)
    (notes / 'version10.md').write_text(
        '# v10\n\n## v10.14.0\n\nSome notes.\n\n## v10.13.0\n\nOlder notes.\n',
        encoding='utf8',
    )
    return tmp_path


@pytest.mark.parametrize(
    'version',
    ['10.13.0', '10.14.0', '10.14.0rc1', '10.14.0.post1', '10.13.0.post2'],
)
def test_validate_release_notes_accepts_base_version(release_notes, version):
    assert bump_version.validate_release_notes(version, root=release_notes)


@pytest.mark.parametrize('version', ['10.15.0', '10.15.0rc1', '11.0.0'])
def test_validate_release_notes_rejects_undocumented(release_notes, version):
    assert not bump_version.validate_release_notes(version, root=release_notes)


def test_validate_release_notes_accepts_exact_suffixed_header(tmp_path: Path):
    notes = tmp_path / 'docs' / 'releasenotes'
    notes.mkdir(parents=True)
    (notes / 'version10.md').write_text('# v10\n\n## v10.6.0rc1\n', encoding='utf8')
    assert bump_version.validate_release_notes('10.6.0rc1', root=tmp_path)
