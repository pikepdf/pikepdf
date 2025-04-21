# SPDX-FileCopyrightText: 2025 James R. Barlow
# SPDX-License-Identifier: MPL-2.0

"""Benchmark the performance of pikepdf."""

from __future__ import annotations

import time
from tempfile import NamedTemporaryFile

import pikepdf


def main():
    start = time.monotonic()
    with pikepdf.open("tests/resources/private/PDF-RM1.7.pdf") as pdf:
        for p in pdf.pages:
            p.Contents.read_bytes()
        for o in pdf.objects:
            if isinstance(o, (pikepdf.Stream, pikepdf.Dictionary, pikepdf.Array)):
                o.unparse()
        with NamedTemporaryFile(suffix=".pdf") as f:
            pdf.save(
                f,
                object_stream_mode=pikepdf.ObjectStreamMode.generate,
                normalize_content=True,
                recompress_flate=True,
            )
    end = time.monotonic()
    print(f"Time: {end - start}s")


if __name__ == "__main__":
    main()
