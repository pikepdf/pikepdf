# SPDX-FileCopyrightText: 2026 James R. Barlow
# SPDX-License-Identifier: MPL-2.0

"""Regression tests for nanobind shutdown-time reference leaks.

nanobind reports leaks of bound types, instances, and functions on interpreter
shutdown when reference cycles cannot be broken. These tests run a fresh Python
subprocess that imports pikepdf and then exits; any nanobind leak warnings
printed to stderr cause the test to fail. This guards against regressions from
patterns like:

- Module-level ``pikepdf.Object`` constants (Names, Operators, etc.)
- Default arguments in C++ bindings that construct ``QPDFObjectHandle`` or
  other nanobind-bound types at module init time
- Default arguments in ``@augments``-patched Python methods that evaluate
  ``Name.X`` or similar at class definition time
- Static C++ caches of ``py::object`` values
"""

from __future__ import annotations

import subprocess
import sys


def _run_and_capture(code: str) -> str:
    """Execute a Python snippet in a subprocess and return stderr.

    We always use a subprocess so that nanobind's shutdown leak reporter runs
    against a clean interpreter lifecycle (no pytest fixtures or plugin state
    holding references into the module).
    """
    result = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stderr


def _assert_no_nanobind_leaks(stderr: str) -> None:
    if "nanobind: leaked" in stderr:
        raise AssertionError(
            "nanobind reported shutdown-time reference leaks:\n" + stderr
        )


def test_import_pikepdf_does_not_leak():
    """Importing the top-level pikepdf package must not leak."""
    _assert_no_nanobind_leaks(_run_and_capture("import pikepdf"))


def test_import_pikepdf_core_does_not_leak():
    """Importing pikepdf._core directly must not leak."""
    _assert_no_nanobind_leaks(_run_and_capture("import pikepdf._core"))
