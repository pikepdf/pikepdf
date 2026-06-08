# SPDX-FileCopyrightText: 2026 James R. Barlow
# SPDX-License-Identifier: CC0-1.0

"""Microbenchmark for object construction hot paths.

Run directly: ``uv run python examples/bench_object_construct.py``
"""

from __future__ import annotations

import timeit

from pikepdf import Array, Dictionary, Name


def main() -> None:
    """Run microbenchmarks for object construction hot paths."""
    n = 1_000_000
    cases = {
        "Name.Resources": lambda: Name.Resources,
        "Name('/Resources')": lambda: Name('/Resources'),
        "Array([1,2,3])": lambda: Array([1, 2, 3]),
        "Dictionary(A=1,B=2)": lambda: Dictionary(A=1, B=2),
    }
    for label, fn in cases.items():
        secs = timeit.timeit(fn, number=n)
        print(f"{label:24s} {secs / n * 1e9:8.1f} ns/op")


if __name__ == "__main__":
    main()
