# SPDX-FileCopyrightText: 2022 James R. Barlow
# SPDX-License-Identifier: MPL-2.0

"""Integrate JBIG2 image decoding.

Requires third-party JBIG2 decoder in the form of an external program, like
jbig2dec.
"""

from __future__ import annotations

import os
from abc import ABC, abstractmethod
from pathlib import Path
from subprocess import DEVNULL, PIPE, CalledProcessError, run
from tempfile import TemporaryDirectory

from packaging.version import Version
from PIL import Image

from pikepdf._exceptions import DependencyError


def _extract_jbig2_bytes(jbig2: bytes, jbig2_globals: bytes) -> bytes:
    with TemporaryDirectory(prefix='pikepdf-', suffix='.jbig2') as tmpdir:
        image_path = Path(tmpdir) / "image"
        global_path = Path(tmpdir) / "global"
        output_path = Path(tmpdir) / "outfile"

        args = [
            "jbig2dec",
            "--embedded",
            "--format",
            "png",
            "--output",
            os.fspath(output_path),
        ]

        # Get the raw stream, because we can't decode im_obj - that is why we are here
        # (Strictly speaking we should remove any non-JBIG2 filters if double encoded)
        image_path.write_bytes(jbig2)

        if len(jbig2_globals) > 0:
            global_path.write_bytes(jbig2_globals)
            args.append(os.fspath(global_path))

        args.append(os.fspath(image_path))

        run(args, stdout=DEVNULL, check=True)
        with Image.open(output_path) as im:
            return im.tobytes()


class JBIG2DecoderInterface(ABC):
    """pikepdf's C++ expects this Python interface to be available for JBIG2."""

    @abstractmethod
    def check_available(self) -> None:
        """Check if decoder is available. Throws DependencyError if not."""

    @abstractmethod
    def decode_jbig2(self, jbig2: bytes, jbig2_globals: bytes) -> bytes:
        """Decode JBIG2 from jbig2 and globals, returning decoded bytes."""

    def available(self) -> bool:
        """Return True if decoder is available."""
        try:
            self.check_available()
        except DependencyError:
            return False
        else:
            return True


class JBIG2Decoder(JBIG2DecoderInterface):
    """JBIG2 decoder implementation."""

    def check_available(self) -> None:
        """Check if jbig2dec is installed and usable."""
        version = self._version()
        if version < Version('0.15'):
            raise DependencyError("jbig2dec is too old (older than version 0.15)")

    def decode_jbig2(self, jbig2: bytes, jbig2_globals: bytes) -> bytes:
        """Decode JBIG2 from binary data, returning decode bytes."""
        return _extract_jbig2_bytes(jbig2, jbig2_globals)

    def _version(self) -> Version:
        try:
            proc = run(
                ['jbig2dec', '--version'], stdout=PIPE, check=True, encoding='ascii'
            )
        except (CalledProcessError, FileNotFoundError) as e:
            raise DependencyError("jbig2dec - not installed or not found") from e
        else:
            result = proc.stdout
            version_str = result.replace(
                'jbig2dec', ''
            ).strip()  # returns "jbig2dec 0.xx"
            return Version(version_str)


_jbig2_decoder = JBIG2Decoder()


def get_decoder() -> JBIG2DecoderInterface:
    """Return an instance of a JBIG2 decoder."""
    return _jbig2_decoder
