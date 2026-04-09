# SPDX-FileCopyrightText: 2026 James R. Barlow
# SPDX-License-Identifier: MPL-2.0

"""Runtime memory leak tests.

These tests exercise common PDF operation lifecycles in a loop and assert that
RSS (resident set size) does not grow unboundedly. Unlike test_import_leaks.py
(which checks for nanobind shutdown-time leak warnings), these tests catch
runtime leaks in both the Python and C++ layers — e.g. reference cycles between
nanobind-bound types and Python objects that the garbage collector cannot break.
"""

from __future__ import annotations

import gc
import platform
from io import BytesIO
from pathlib import Path

import pytest

psutil = pytest.importorskip("psutil", reason="psutil required for RSS measurement")

from pikepdf import Pdf, parse_content_stream  # noqa: E402

TESTS_ROOT = Path(__file__).parent
RESOURCES = TESTS_ROOT / "resources"
TEST_PDF = RESOURCES / "fourpages.pdf"

# Number of warmup iterations (not measured — lets allocator pools stabilize)
WARMUP = 3
# Number of measured iterations
ITERATIONS = 50
# Maximum acceptable RSS growth per iteration. A genuine object-level leak
# would grow linearly; this threshold tolerates OS page-granularity noise
# and allocator fragmentation while catching ~100 KB/iter steady leaks.
MAX_GROWTH_PER_ITER = 100 * 1024  # 100 KB


def _get_rss() -> int:
    """Return current RSS in bytes after a full GC cycle."""
    gc.collect()
    gc.collect()  # second pass to break reference cycles
    return psutil.Process().memory_info().rss


def _exercise_pdf_lifecycle() -> None:
    """Run one cycle of common PDF operations.

    Each operation exercises a different C++ lifecycle path:
    - Pdf.open(path): QPDF lifecycle, file-based InputSource
    - Page iteration: QPDFPageObjectHelper creation/destruction
    - parse_content_stream: OperandGrouper + py::list
    - Pdf.save(BytesIO, progress=...): Pl_PythonOutput + PikeProgressReporter
    - Pdf.open(stream): PythonStreamInputSource lifecycle
    """
    # Open from file path, iterate pages, parse content, save with progress
    with Pdf.open(TEST_PDF) as pdf:
        for page in pdf.pages:
            _ = page.mediabox
        for page in pdf.pages:
            parse_content_stream(page)
        bio = BytesIO()
        pdf.save(bio, progress=lambda pct: None)

    # Open from Python stream
    with open(TEST_PDF, "rb") as f:
        with Pdf.open(f) as pdf:
            for page in pdf.pages:
                _ = page.mediabox


@pytest.mark.skipif(
    platform.python_implementation() != "CPython",
    reason="RSS-based memory test is only reliable on CPython",
)
def test_pdf_operations_do_not_leak_memory():
    """Repeated PDF open/parse/save cycles must not cause unbounded RSS growth."""
    for _ in range(WARMUP):
        _exercise_pdf_lifecycle()

    baseline_rss = _get_rss()

    for _ in range(ITERATIONS):
        _exercise_pdf_lifecycle()

    final_rss = _get_rss()

    growth = final_rss - baseline_rss
    growth_per_iter = growth / ITERATIONS

    assert growth_per_iter < MAX_GROWTH_PER_ITER, (
        f"Memory grew by {growth / 1024:.1f} KB over {ITERATIONS} iterations "
        f"({growth_per_iter / 1024:.1f} KB/iter). "
        f"Baseline: {baseline_rss / 1024 / 1024:.1f} MB, "
        f"Final: {final_rss / 1024 / 1024:.1f} MB"
    )
