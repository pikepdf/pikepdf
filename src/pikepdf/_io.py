# SPDX-FileCopyrightText: 2023 James R. Barlow
# SPDX-License-Identifier: MPL-2.0

from __future__ import annotations

from io import TextIOBase


def check_stream_is_usable(stream):
    """Check that a stream is seekable and binary."""
    if isinstance(stream, TextIOBase):
        raise TypeError("stream must be binary (no transcoding) and seekable")
