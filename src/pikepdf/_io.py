# SPDX-FileCopyrightText: 2023 James R. Barlow
# SPDX-License-Identifier: MPL-2.0

from __future__ import annotations

from contextlib import suppress
from io import TextIOBase
from pathlib import Path


def check_stream_is_usable(stream):
    """Check that a stream is seekable and binary."""
    if isinstance(stream, TextIOBase):
        raise TypeError("stream must be binary (no transcoding) and seekable")


def check_different_files(file1, file2):
    """Check that two files are different."""
    with suppress(FileNotFoundError):
        if Path(file1) == Path(file2) or Path(file1).samefile(Path(file2)):
            raise ValueError(
                "Cannot overwrite input file. Open the file with "
                "pikepdf.open(..., allow_overwriting_input=True) to "
                "allow overwriting the input file."
            )
