# SPDX-FileCopyrightText: 2023 James R. Barlow
# SPDX-License-Identifier: MPL-2.0

from __future__ import annotations

import errno
import io
import os
import secrets
import stat
import tempfile
from collections.abc import Callable, Generator, Iterator
from contextlib import contextmanager, suppress
from io import TextIOBase
from os import PathLike
from pathlib import Path
from shutil import copyfileobj, copystat
from tempfile import NamedTemporaryFile
from typing import IO


def check_stream_is_usable(stream: IO) -> None:
    """Check that a stream is seekable and binary."""
    if isinstance(stream, TextIOBase):
        raise TypeError("stream must be binary (no transcoding) and seekable")


_PLAIN_FILE_TYPES = (io.FileIO, io.BufferedWriter, io.BufferedRandom)


def output_fd(stream: IO) -> int | None:
    """Return the file descriptor of a stream that can be written to directly.

    Saving writes straight to this descriptor instead of calling the stream's
    ``write()``, which avoids a Python call for every chunk qpdf emits. Only
    plain binary files from :func:`open` qualify: subclasses may override
    ``write()``, and pipes and other special files have write semantics
    (partial writes, non-blocking I/O) best left to Python.
    """
    if type(stream) not in _PLAIN_FILE_TYPES:
        return None
    try:
        if not stream.writable():
            return None
        fd = stream.fileno()
        if not stat.S_ISREG(os.fstat(fd).st_mode):
            return None
    except (OSError, ValueError):
        return None
    return fd


_OVERWRITE_INPUT = (
    "Cannot overwrite input file. Open the file with "
    "pikepdf.open(..., allow_overwriting_input=True) to "
    "allow overwriting the input file."
)


def check_different_files(file1: str | PathLike, file2: str | PathLike) -> None:
    """Check that two files are different."""
    with suppress(FileNotFoundError):
        if Path(file1) == Path(file2) or Path(file1).samefile(Path(file2)):
            raise ValueError(_OVERWRITE_INPUT)


def _fstat(stream: IO) -> os.stat_result | None:
    try:
        return os.fstat(stream.fileno())
    except (AttributeError, OSError, ValueError):
        # No file descriptor (BytesIO), or the stream is closed
        return None


def check_stream_is_not_input(
    stream: IO, input_stream: IO | None, original_filename: Path | None
) -> None:
    """Check that a destination stream does not write over a Pdf's input.

    qpdf reads the input lazily, including while saving, so writing over it
    would corrupt both the output and the open Pdf. A stream is the input if
    it is the stream the Pdf was opened from, or a stream on the same file.
    """
    if input_stream is not None and stream is input_stream:
        raise ValueError(_OVERWRITE_INPUT)
    out_stat = _fstat(stream)
    if out_stat is None:
        return
    if input_stream is not None:
        in_stat = _fstat(input_stream)
        if in_stat is not None and os.path.samestat(out_stat, in_stat):
            raise ValueError(_OVERWRITE_INPUT)
    if original_filename is not None:
        with suppress(OSError):
            if os.path.samestat(out_stat, os.stat(original_filename)):
                raise ValueError(_OVERWRITE_INPUT)


@contextmanager
def atomic_overwrite(filename: Path) -> Generator[IO[bytes], None, None]:
    """Atomically ovewrite a file.

    If the destination file does not exist, it is created. If writing fails,
    the destination file is deleted.

    If the destination file does exist, a temporaryfile is created in the same
    directory, and data is written to that file. If writing succeeds, the temporary
    file is renamed to the destination file. If writing fails, the temporary file
    is deleted and the original destination file is left untouched.
    """
    try:
        # Try to create the file using exclusive creation mode
        stream = filename.open("xb")
    except FileExistsError:
        pass
    else:
        # We were able to create the file, so we can use it directly
        try:
            with stream:
                yield stream
        except (Exception, KeyboardInterrupt):
            # ...but if an error occurs while using it, clean up
            with suppress(OSError):
                filename.unlink()
            raise
        return

    # If we get here, the file already exists.
    if not stat.S_ISREG(os.stat(filename).st_mode):
        # /dev/null, a FIFO, a character device: renaming over it would replace
        # the special file with a regular one (if we have permission to, as root
        # does), so write into it directly.
        with filename.open("wb") as stream:
            yield stream
        return

    # Use a temporary file, then rename it to the destination file if we
    # succeed. Destination file is not touched if we fail.
    with filename.open("ab") as stream:
        pass  # Confirm we will be able to write to the indicated destination

    tf = None
    try:
        try:
            # First try to create the file in the same directory, so that Path.replace()
            # is more likely to be atomic.
            tf = NamedTemporaryFile(
                dir=filename.parent, prefix=f".pikepdf.{filename.name}", delete=False
            )
        except PermissionError:
            # If same directory fails, write to stand temporary folder (losing
            # atomicity, if different file systems)
            tf = NamedTemporaryFile(prefix=f".pikepdf.{filename.name}", delete=False)
        # Yield the underlying file object rather than the wrapper, so that
        # saving can write to its file descriptor directly (see output_fd).
        yield tf.file
        tf.flush()
        tf.close()
        with suppress(OSError):
            # Copy permissions, create time, etc. from the original
            copystat(filename, Path(tf.name))
        Path(tf.name).replace(filename)
        with suppress(OSError):
            # Update modified time of the destination file
            filename.touch()
    finally:
        if tf is not None:
            with suppress(OSError):
                tf.close()
            with suppress(OSError):
                Path(tf.name).unlink()


_TEMP_CREATE_ATTEMPTS = 100


def _create_temp_in(directory: Path, name: str) -> tuple[int, Path]:
    """Exclusively create ``.pikepdf.{name}.{token}`` in *directory*.

    The file is created with mode 0o666 so the process umask decides the final
    permissions, as for any newly created file.
    """
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, 'O_BINARY', 0)
    for _ in range(_TEMP_CREATE_ATTEMPTS):
        path = directory / f".pikepdf.{name}.{secrets.token_hex(6)}"
        try:
            return os.open(path, flags, 0o666), path
        except FileExistsError:
            continue
    raise FileExistsError(
        errno.EEXIST, "No usable temporary file name", str(directory / name)
    )


def _create_temp_for(filename: Path) -> tuple[int, Path]:
    try:
        return _create_temp_in(filename.parent, filename.name)
    except PermissionError:
        return _create_temp_in(Path(tempfile.gettempdir()), filename.name)


def _copy_bytes_into(src: Path, dest: Path) -> None:
    with src.open('rb') as fsrc, dest.open('wb') as fdest:
        copyfileobj(fsrc, fdest)


def _install_verified(tmp: Path, filename: Path) -> None:
    try:
        dest_mode: int | None = os.stat(filename).st_mode
    except FileNotFoundError:
        dest_mode = None

    if dest_mode is not None and not stat.S_ISREG(dest_mode):
        # /dev/null, a FIFO, a character device: it cannot be replaced by a
        # rename, so write the verified bytes into it.
        _copy_bytes_into(tmp, filename)
        return

    if dest_mode is not None:
        with suppress(OSError):
            copystat(filename, tmp)
    try:
        os.replace(tmp, filename)
    except OSError as e:
        if e.errno != errno.EXDEV:
            raise
        # The temporary file fell back to a directory on another filesystem.
        _copy_bytes_into(tmp, filename)
        return
    with suppress(OSError):
        filename.touch()


@contextmanager
def atomic_write_verified(
    filename: Path, verify: Callable[[Path], None]
) -> Iterator[IO[bytes]]:
    """Write a file, verify it on disk, and only then put it in place.

    Yields a seekable binary stream backed by a new temporary file named
    ``.pikepdf.{name}.{token}`` in the destination's directory (or in the
    system temporary directory, if the destination's directory is not
    writable). When the ``with`` block exits normally, the stream is closed and
    ``verify`` is called with the temporary file's path; it should raise to
    reject the file. If it returns, the temporary file replaces *filename*.

    Guarantees:

    - If the ``with`` block or ``verify`` raises (including
      ``KeyboardInterrupt``), the temporary file is removed, the exception
      propagates, and *filename* is left untouched if it existed, or absent if
      it did not.
    - Only bytes that ``verify`` accepted are ever written to *filename*.
    - An existing regular destination keeps its permission bits and other
      metadata (via :func:`shutil.copystat`); its modification time is then
      updated. A new destination gets permissions from the process umask.

    - A regular destination that cannot be opened for writing raises
      :class:`PermissionError` before anything is written.

    Non-guarantees:

    - A symlink at *filename* is replaced by a regular file; the symlink's
      target is not modified.
    - If the destination is not a regular file (e.g. ``/dev/null`` or a FIFO),
      the verified bytes are copied into it instead of renaming over it.
    - If the temporary file had to be created on a different filesystem, the
      verified bytes are copied into *filename*, which is not atomic: a crash
      during that copy can leave a partial file.
    - Durability across power loss is not guaranteed (no ``fsync``).
    """
    filename = Path(filename)
    with suppress(FileNotFoundError):
        if stat.S_ISREG(os.stat(filename).st_mode):
            # Replacing the file needs only permission on its directory; as
            # for atomic_overwrite, also require that the file be writable.
            with filename.open('ab'):
                pass
    fd, tmp = _create_temp_for(filename)
    try:
        try:
            stream = os.fdopen(fd, 'wb')
        except BaseException:
            os.close(fd)
            raise
        with stream:
            yield stream
        verify(tmp)
        _install_verified(tmp, filename)
    finally:
        # After a successful rename the temporary file no longer exists.
        with suppress(OSError):
            tmp.unlink()
