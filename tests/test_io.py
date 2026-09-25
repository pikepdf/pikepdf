# SPDX-FileCopyrightText: 2022 James R. Barlow
# SPDX-License-Identifier: CC0-1.0

from __future__ import annotations

import errno
import io
import logging
import os
import os.path
import pathlib
import stat
import subprocess
import sys
import tempfile
import threading
from io import BytesIO, FileIO
from shutil import copy

import pytest

import pikepdf
from pikepdf import Pdf, PdfError
from pikepdf._io import atomic_overwrite, atomic_write_verified, output_fd

# pylint: disable=redefined-outer-name


@pytest.fixture
def sandwich(resources):
    # Has XMP, docinfo, <?adobe-xap-filters esc="CRLF"?>, shorthand attribute XMP
    with Pdf.open(resources / 'sandwich.pdf') as pdf:
        yield pdf


class LimitedBytesIO(BytesIO):
    """Version of BytesIO that only accepts small reads/writes."""

    def write(self, b):
        amt = min(len(b), 100)
        return super().write(b[:amt])


def test_weird_output_stream(sandwich):
    bio = BytesIO()
    lbio = LimitedBytesIO()
    sandwich.save(bio, static_id=True)
    sandwich.save(lbio, static_id=True)
    assert bio.getvalue() == lbio.getvalue()


def test_overwrite_with_memory_file(outdir):
    (outdir / 'example.pdf').touch()
    pdf = Pdf.new()
    pdf.save(outdir / 'example.pdf')


def test_overwrite_input(resources, outdir):
    copy(resources / 'sandwich.pdf', outdir / 'sandwich.pdf')
    with Pdf.open(outdir / 'sandwich.pdf') as p:
        with pytest.raises(ValueError, match=r'overwrite input file'):
            p.save(outdir / 'sandwich.pdf')


def test_fail_only_overwrite_input_check(monkeypatch, resources, outdir):
    copy(resources / 'sandwich.pdf', outdir / 'sandwich.pdf')
    with Pdf.open(outdir / 'sandwich.pdf') as p:

        def mockraise(*args):
            raise OSError("samefile mocked")

        monkeypatch.setattr(pathlib.Path, 'samefile', mockraise)
        with pytest.raises(OSError, match=r'samefile mocked'):
            p.save(outdir / 'wouldwork.pdf')


class BadBytesIO(BytesIO):
    """Version of BytesIO that reports more bytes written than actual."""

    def write(self, b):
        super().write(b)
        return len(b) + 1


class WrongTypeBytesIO(BytesIO):
    """Returns wrong type."""

    def write(self, b):  # pylint: disable=unused-argument
        return None  # most likely wrong return type


class NegativeOneBytesIO(BytesIO):
    def write(self, b):  # pylint: disable=unused-argument
        return -1


@pytest.mark.parametrize(
    'bio_class,exc_type',
    [
        (BadBytesIO, ValueError),
        (WrongTypeBytesIO, TypeError),
        (NegativeOneBytesIO, PdfError),
    ],
)
def test_invalid_output_stream(sandwich, bio_class, exc_type):
    bio = bio_class()
    with pytest.raises(exc_type):
        sandwich.save(bio, static_id=True)


class ExpectedError(Exception):
    pass


def test_file_without_fileno(resources):
    class FileWithoutFileNo(FileIO):
        def fileno(self):
            raise ExpectedError("nope!")

    f = FileWithoutFileNo(resources / 'pal.pdf', 'rb')
    with pytest.raises(ExpectedError):
        Pdf.open(f, access_mode=pikepdf._core.AccessMode.mmap_only)

    # Confirm we automatically fallback to stream
    with Pdf.open(f, access_mode=pikepdf._core.AccessMode.mmap) as pdf:
        assert pdf.filename


def test_file_deny_mmap(resources, monkeypatch):
    import mmap

    def raises_oserror(*args, **kwargs):
        raise OSError("This file is temporarily not mmap-able")

    monkeypatch.setattr(mmap, 'mmap', raises_oserror)
    with pytest.raises(OSError):
        Pdf.open(resources / 'pal.pdf', access_mode=pikepdf._core.AccessMode.mmap_only)

    with Pdf.open(
        resources / 'pal.pdf', access_mode=pikepdf._core.AccessMode.default
    ) as pdf:
        assert len(pdf.pages) == 1


def test_mmap_only_file(resources):
    class UnreadableFile(FileIO):
        def readinto(self, *args):
            raise ExpectedError("can't read, you have to mmap me")

        read = readinto  # PyPy uses read() not readinto()

    f = UnreadableFile(resources / 'pal.pdf', 'rb')
    with pytest.raises(ExpectedError):
        Pdf.open(f, access_mode=pikepdf._core.AccessMode.stream)


def test_save_bytesio(resources, outpdf):
    with Pdf.open(resources / 'fourpages.pdf') as input_:
        pdf = Pdf.new()
        for page in input_.pages:
            pdf.pages.append(page)
        bio = BytesIO()
        pdf.save(bio, static_id=True)
        bio_value = bio.getvalue()
        assert bio_value != b''
        pdf.save(outpdf, static_id=True)
        assert outpdf.read_bytes() == bio_value


@pytest.mark.skipif(
    hasattr(os, 'geteuid') and os.geteuid() == 0, reason="root can override permissions"
)
def test_save_failure(sandwich, outdir):
    dest = outdir / 'notwritable.pdf'

    # This should work on Windows since Python maps the read-only bit
    dest.touch(mode=0o444, exist_ok=False)
    if dest.stat().st_mode & 0o400 != 0o400:
        pytest.skip("Couldn't create a read-only file")

    # Now try to overwrite
    with pytest.raises(PermissionError, match="denied"):
        sandwich.save(dest)


@pytest.mark.filterwarnings("ignore::pytest.PytestUnraisableExceptionWarning")
def test_stop_iteration_on_close(resources):
    class StopIterationOnClose(BytesIO):
        def close(self):
            raise StopIteration('To simulate weird generator behavior')

    # Inspired by https://github.com/pikepdf/pikepdf/issues/114
    stream = StopIterationOnClose((resources / 'pal-1bit-trivial.pdf').read_bytes())
    pdf = Pdf.open(stream)  # no with clause
    pdf.close()


def test_read_after_close(resources):
    pdf = Pdf.open(resources / 'pal.pdf')  # no with clause
    contents = pdf.pages[0].Contents
    pdf.close()
    with pytest.raises(PdfError, match="closed input source"):
        contents.read_raw_bytes()


# Regression for https://github.com/pikepdf/pikepdf/issues/732
#
# Opening a Pdf from a filename makes pikepdf open the file as a Python stream;
# the input source's destructor then calls back into Python to close it. If the
# Pdf is held only by a transient on the evaluation stack (the list literal
# below) and a *later* element raises, the Pdf is deallocated while a Python
# exception is still in flight. The destructor must neither let an exception
# escape (which calls std::terminate -> SIGABRT) nor swallow the in-flight
# exception.
_UNWIND_REPRO = """
import sys
import pikepdf

path = sys.argv[1]
access_mode = getattr(pikepdf.AccessMode, sys.argv[2])

def boom():
    raise ValueError("oops")

# The freshly-opened Pdf is a transient list element; boom() raises while the
# Pdf is still only referenced by the half-built list, so it is freed mid-unwind
# with the Python error indicator set.
[pikepdf.open(path, access_mode=access_mode), boom()]
"""


@pytest.mark.parametrize("access_mode", ["stream", "mmap_only"])
def test_close_during_exception_unwind(resources, access_mode):
    result = subprocess.run(
        [sys.executable, "-c", _UNWIND_REPRO, str(resources / 'pal.pdf'), access_mode],
        capture_output=True,
        text=True,
        check=False,
    )
    # Must not abort: SIGABRT shows up as a negative return code (e.g. -6).
    assert result.returncode == 1, (
        f"expected clean ValueError exit, got returncode={result.returncode}\n"
        f"stderr:\n{result.stderr}"
    )
    # The in-flight exception must propagate normally, not be swallowed.
    assert "ValueError: oops" in result.stderr


def test_logging(caplog):
    caplog.set_level(logging.INFO)
    pikepdf._core._test.log_info("test log message")
    assert [("pikepdf._core", logging.INFO)] == [
        (rec[0], rec[1]) for rec in caplog.record_tuples
    ]


def test_atomic_overwrite_new(tmp_path):
    new_file = tmp_path / 'new.pdf'
    assert not new_file.exists()

    with pytest.raises(ValueError, match='oops'), atomic_overwrite(new_file) as f:
        f.write(b'a failed write should not produce an invalid file')
        raise ValueError('oops')
    assert not new_file.exists()

    assert list(tmp_path.glob('*.pikepdf')) == [], "Temporary files were not cleaned up"


def test_atomic_overwrite_existing(tmp_path):
    existing_file = tmp_path / 'existing.pdf'
    existing_file.write_bytes(b'existing')

    with atomic_overwrite(existing_file) as f:
        f.write(b'new')
    assert existing_file.read_bytes() == b'new'

    with pytest.raises(ValueError, match='oops'), atomic_overwrite(existing_file) as f:
        f.write(b'a failed update should not corrupt the file')
        raise ValueError('oops')
    assert existing_file.read_bytes() == b'new'

    assert list(tmp_path.glob('*.pikepdf')) == [], "Temporary files were not cleaned up"


def test_atomic_ovewrite_stat_preservation(tmp_path):
    existing_file = tmp_path / 'existing.pdf'
    existing_file.touch(0o755)
    os.utime(existing_file, ns=(0, 0))

    ctime = existing_file.stat().st_ctime
    with atomic_overwrite(existing_file) as f:
        f.write(b'new')
    stat = existing_file.stat()
    assert stat.st_ctime >= ctime
    assert stat.st_mtime > 0
    if os.name != 'nt':
        # st_mode is not preserved on Windows
        assert stat.st_mode & 0o777 == 0o755


def test_memory_to_path(resources, tmp_path):
    bio = BytesIO((resources / 'sandwich.pdf').read_bytes())
    with Pdf.open(bio) as pdf:
        assert len(pdf.pages) == 1
        pdf.save(str(tmp_path / 'out.pdf'))


def test_newline_handling(resources):
    with Pdf.open(
        resources / 'newline-buffer-test.pdf',
        access_mode=pikepdf._core.AccessMode.mmap_only,
    ) as pdf:
        assert pdf.check_pdf_syntax() == []
    with Pdf.open(
        resources / 'newline-buffer-test.pdf',
        access_mode=pikepdf._core.AccessMode.stream,
    ) as pdf:
        assert pdf.check_pdf_syntax() == []


def test_save_to_dev_null():
    with Pdf.new() as pdf:
        pdf.save(os.devnull)
    assert not pathlib.Path(os.devnull).is_file()


@pytest.mark.skipif(not hasattr(os, 'mkfifo'), reason="needs FIFOs")
def test_save_to_fifo_writes_into_it(tmp_path):
    fifo = tmp_path / 'out.pdf'
    os.mkfifo(fifo)
    received = []
    reader = threading.Thread(target=lambda: received.append(fifo.read_bytes()))
    reader.start()
    with Pdf.new() as pdf:
        pdf.save(fifo)
    reader.join(timeout=10)
    assert stat.S_ISFIFO(fifo.stat().st_mode)
    assert received and received[0].startswith(b'%PDF')


def _pikepdf_temps(directory):
    return list(pathlib.Path(directory).glob('.pikepdf.*'))


def test_atomic_write_verified_new(tmp_path):
    dest = tmp_path / 'new.pdf'
    seen = {}

    def verify(tmp):
        seen['path'] = tmp
        seen['exists'] = tmp.exists()
        seen['content'] = tmp.read_bytes()
        seen['dest_exists'] = dest.exists()

    with atomic_write_verified(dest, verify) as f:
        assert f.seekable()
        f.write(b'hello')

    assert dest.read_bytes() == b'hello'
    assert seen['path'].parent == tmp_path
    assert seen['path'].name.startswith('.pikepdf.new.pdf.')
    assert seen['exists']
    assert seen['content'] == b'hello'
    assert not seen['dest_exists']
    assert _pikepdf_temps(tmp_path) == []


def test_atomic_write_verified_existing(tmp_path):
    dest = tmp_path / 'existing.pdf'
    dest.write_bytes(b'old')
    if os.name != 'nt':
        dest.chmod(0o640)
    os.utime(dest, (1_000_000, 1_000_000))

    with atomic_write_verified(dest, lambda tmp: None) as f:
        f.write(b'new')

    assert dest.read_bytes() == b'new'
    st = dest.stat()
    assert st.st_mtime > 1_000_000
    if os.name != 'nt':
        assert st.st_mode & 0o777 == 0o640
    assert _pikepdf_temps(tmp_path) == []


class VerifyRejected(Exception):
    pass


def _reject(tmp):
    raise VerifyRejected('bad bytes')


def test_atomic_write_verified_reject_new(tmp_path):
    dest = tmp_path / 'new.pdf'
    with pytest.raises(VerifyRejected), atomic_write_verified(dest, _reject) as f:
        f.write(b'unverified')
    assert not dest.exists()
    assert _pikepdf_temps(tmp_path) == []


def test_atomic_write_verified_reject_existing(tmp_path):
    dest = tmp_path / 'existing.pdf'
    dest.write_bytes(b'original')
    os.utime(dest, (1_000_000, 1_000_000))
    with pytest.raises(VerifyRejected), atomic_write_verified(dest, _reject) as f:
        f.write(b'unverified')
    assert dest.read_bytes() == b'original'
    assert dest.stat().st_mtime == 1_000_000
    assert _pikepdf_temps(tmp_path) == []


@pytest.mark.parametrize('exists', [False, True])
def test_atomic_write_verified_body_raises(tmp_path, exists):
    dest = tmp_path / 'dest.pdf'
    if exists:
        dest.write_bytes(b'original')
        os.utime(dest, (1_000_000, 1_000_000))
    called = []
    with (
        pytest.raises(ValueError, match='oops'),
        atomic_write_verified(dest, called.append) as f,
    ):
        f.write(b'partial')
        raise ValueError('oops')
    assert called == []
    if exists:
        assert dest.read_bytes() == b'original'
        assert dest.stat().st_mtime == 1_000_000
    else:
        assert not dest.exists()
    assert _pikepdf_temps(tmp_path) == []


def test_atomic_write_verified_keyboard_interrupt(tmp_path):
    dest = tmp_path / 'dest.pdf'
    with pytest.raises(KeyboardInterrupt), atomic_write_verified(dest, _reject) as f:
        f.write(b'partial')
        raise KeyboardInterrupt
    assert not dest.exists()
    assert _pikepdf_temps(tmp_path) == []


_UMASK_REPRO = """
import os, sys
from pathlib import Path
from pikepdf._io import atomic_write_verified

os.umask(0o027)
dest = Path(sys.argv[1])
with atomic_write_verified(dest, lambda tmp: None) as f:
    f.write(b'x')
print(oct(dest.stat().st_mode & 0o777))
"""


@pytest.mark.skipif(os.name == 'nt', reason="POSIX permissions")
def test_atomic_write_verified_umask(tmp_path):
    dest = tmp_path / 'umask.pdf'
    result = subprocess.run(
        [sys.executable, '-c', _UMASK_REPRO, str(dest)],
        capture_output=True,
        text=True,
        check=True,
    )
    assert result.stdout.strip() == '0o640'
    assert dest.stat().st_mode & 0o777 == 0o640


@pytest.mark.skipif(os.name == 'nt', reason="no /dev/null semantics on Windows")
def test_atomic_write_verified_devnull():
    verified = []
    with atomic_write_verified(pathlib.Path(os.devnull), verified.append) as f:
        f.write(b'discard me')
    assert len(verified) == 1
    assert pathlib.Path(os.devnull).exists()
    assert not pathlib.Path(os.devnull).is_file()


def test_atomic_write_verified_exdev(tmp_path, monkeypatch):
    dest = tmp_path / 'dest.pdf'
    dest.write_bytes(b'original')
    real_replace = os.replace
    calls = []

    def fake_replace(src, dst, *args, **kwargs):
        if not calls:
            calls.append((src, dst))
            raise OSError(errno.EXDEV, 'Invalid cross-device link')
        return real_replace(src, dst, *args, **kwargs)

    monkeypatch.setattr(os, 'replace', fake_replace)
    with atomic_write_verified(dest, lambda tmp: None) as f:
        f.write(b'verified bytes')
    assert calls
    assert dest.read_bytes() == b'verified bytes'
    assert _pikepdf_temps(tmp_path) == []


def test_atomic_write_verified_permission_fallback(tmp_path, monkeypatch):
    dest = tmp_path / 'dest.pdf'
    real_open = os.open
    opened = []

    def fake_open(path, flags, *args, **kwargs):
        p = pathlib.Path(path)
        if p.parent == tmp_path and p.name.startswith('.pikepdf.'):
            raise PermissionError(errno.EACCES, 'denied', str(path))
        opened.append(p)
        return real_open(path, flags, *args, **kwargs)

    monkeypatch.setattr(os, 'open', fake_open)
    seen = []
    with atomic_write_verified(dest, seen.append) as f:
        f.write(b'via tempdir')
    assert dest.read_bytes() == b'via tempdir'
    assert seen[0].parent == pathlib.Path(tempfile.gettempdir())
    assert seen[0].name.startswith('.pikepdf.dest.pdf.')
    assert not seen[0].exists()
    assert _pikepdf_temps(tmp_path) == []


@pytest.mark.skipif(os.name == 'nt', reason="symlinks need privileges on Windows")
def test_atomic_write_verified_symlink(tmp_path):
    target = tmp_path / 'target.pdf'
    target.write_bytes(b'target')
    link = tmp_path / 'link.pdf'
    link.symlink_to(target)
    with atomic_write_verified(link, lambda tmp: None) as f:
        f.write(b'new')
    assert not link.is_symlink()
    assert link.is_file()
    assert link.read_bytes() == b'new'
    assert target.read_bytes() == b'target'
    assert _pikepdf_temps(tmp_path) == []


class _SubclassedWriter(io.BufferedWriter):
    pass


@pytest.mark.parametrize(
    'opener',
    [
        lambda p: open(p, 'wb'),
        lambda p: open(p, 'w+b'),
        lambda p: open(p, 'ab'),
        lambda p: open(p, 'wb', buffering=0),
    ],
    ids=['wb', 'w+b', 'ab', 'unbuffered'],
)
def test_output_fd_plain_files(tmp_path, opener):
    with opener(tmp_path / 'out.pdf') as f:
        assert output_fd(f) == f.fileno()


def test_output_fd_rejects(tmp_path):
    path = tmp_path / 'out.pdf'
    path.write_bytes(b'')
    assert output_fd(BytesIO()) is None
    with open(path, 'w') as f:
        assert output_fd(f) is None  # text stream
    with open(path, 'rb') as f:
        assert output_fd(f) is None  # BufferedReader
    with FileIO(path, 'rb') as f:
        assert output_fd(f) is None  # not writable
    with _SubclassedWriter(FileIO(path, 'wb')) as f:
        assert output_fd(f) is None  # write() may be overridden
    closed = open(path, 'wb')
    closed.close()
    assert output_fd(closed) is None


@pytest.mark.skipif(not hasattr(os, 'pipe'), reason="needs pipes")
def test_output_fd_rejects_pipe():
    r, w = os.pipe()
    with open(r, 'rb'), open(w, 'wb') as writer:
        assert output_fd(writer) is None


def test_atomic_overwrite_existing_yields_plain_file(tmp_path):
    existing = tmp_path / 'existing.pdf'
    existing.write_bytes(b'existing')
    with atomic_overwrite(existing) as f:
        assert output_fd(f) is not None


def _reference_bytes(pdf):
    bio = BytesIO()
    pdf.save(bio, static_id=True)
    return bio.getvalue()


@pytest.mark.parametrize('mode', ['wb', 'w+b', 'ab'])
@pytest.mark.parametrize('buffering', [-1, 0])
def test_save_to_file_object_uses_fd(sandwich, tmp_path, monkeypatch, mode, buffering):
    import pikepdf._io

    calls = []
    real_output_fd = pikepdf._io.output_fd

    def spy(stream):
        fd = real_output_fd(stream)
        calls.append(fd)
        return fd

    monkeypatch.setattr(pikepdf._io, 'output_fd', spy)
    expected = _reference_bytes(sandwich)
    path = tmp_path / 'out.pdf'
    if mode == 'ab':
        path.write_bytes(b'existing')
    with open(path, mode, buffering=buffering) as f:
        f.write(b'prefix')  # left in the Python buffer, unflushed
        sandwich.save(f, static_id=True)
        assert calls and calls[-1] == f.fileno()
        start = len(b'existing') if mode == 'ab' else 0
        assert f.tell() == start + len(b'prefix') + len(expected)
        f.write(b'suffix')
    head = b'existing' if mode == 'ab' else b''
    assert path.read_bytes() == head + b'prefix' + expected + b'suffix'


def test_save_to_file_object_mid_file(sandwich, tmp_path):
    expected = _reference_bytes(sandwich)
    path = tmp_path / 'out.pdf'
    path.write_bytes(b'x' * 100)
    with open(path, 'r+b') as f:
        f.read(10)  # BufferedRandom has read ahead past the logical position
        sandwich.save(f, static_id=True)
        assert f.tell() == 10 + len(expected)
    data = path.read_bytes()
    assert data[:10] == b'x' * 10
    assert data[10 : 10 + len(expected)] == expected


@pytest.mark.skipif(sys.platform != 'linux', reason="needs RLIMIT_FSIZE semantics")
def test_save_to_file_object_write_error(resources, tmp_path):
    script = f"""
import errno, resource, signal
import pikepdf
signal.signal(signal.SIGXFSZ, signal.SIG_IGN)
resource.setrlimit(resource.RLIMIT_FSIZE, (1000, 1000))
with pikepdf.open({str(resources / 'sandwich.pdf')!r}) as pdf:
    with open({str(tmp_path / 'out.pdf')!r}, 'wb') as f:
        try:
            pdf.save(f)
        except OSError as e:
            assert e.errno == errno.EFBIG, e
            print('OK')
"""
    result = subprocess.run(
        [sys.executable, '-c', script], capture_output=True, text=True, check=False
    )
    assert result.stdout.strip() == 'OK', result.stderr
