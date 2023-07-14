# SPDX-FileCopyrightText: 2023 James R. Barlow
# SPDX-License-Identifier: MPL-2.0

from __future__ import annotations

from contextlib import contextmanager, suppress
from io import TextIOBase
from pathlib import Path
from tempfile import NamedTemporaryFile


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


@contextmanager
def atomic_overwrite(filename: Path):
    if not filename.exists():
        try:
            with filename.open("wb") as stream:
                yield stream
        except Exception:
            with suppress(FileNotFoundError):
                filename.unlink()
            raise
        return

    with filename.open("ab") as stream:
        pass  # To confirm we have write permission without truncating

    with NamedTemporaryFile(
        dir=filename.parent, prefix=f".pikepdf.{filename.name}", delete=False
    ) as tf:
        try:
            yield tf
        except Exception:
            tf.close()
            Path(tf.name).unlink()
            raise
        tf.flush()
        tf.close()
        Path(tf.name).replace(filename)
