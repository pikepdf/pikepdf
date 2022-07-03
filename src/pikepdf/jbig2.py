# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.
#
# Copyright (C) 2017, James R. Barlow (https://github.com/jbarlow83/)
import os
from abc import ABC, abstractmethod
from pathlib import Path
from subprocess import DEVNULL, PIPE, CalledProcessError, run
from tempfile import TemporaryDirectory
from typing import Optional, cast

import deprecation
from packaging.version import Version
from PIL import Image

import pikepdf
from pikepdf._exceptions import DependencyError


@deprecation.deprecated(
    deprecated_in="5.1.5", removed_in="6.0", details="Use extract_jbig2_bytes instead"
)
def extract_jbig2(
    im_obj: pikepdf.Object, globals_obj: Optional[pikepdf.Object] = None
) -> Image.Image:  # pragma: no cover

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
        image_path.write_bytes(cast(memoryview, im_obj.get_raw_stream_buffer()))

        if globals_obj is not None:
            # For globals, we do want to remove any encoding since it's just a binary
            # blob and won't be marked with /JBIG2Decode
            global_path.write_bytes(cast(memoryview, globals_obj.get_stream_buffer()))
            args.append(os.fspath(global_path))

        args.append(os.fspath(image_path))

        run(args, stdout=DEVNULL, check=True)
        im = Image.open(output_path)
        im.load()  # Load pixel data into memory so file/tempdir can be closed
        return im


def extract_jbig2_bytes(jbig2: bytes, jbig2_globals: bytes) -> bytes:
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


def assert_jbig2dec_available() -> None:
    try:
        proc = run(['jbig2dec', '--version'], stdout=PIPE, check=True, encoding='ascii')
    except (CalledProcessError, FileNotFoundError) as e:
        raise DependencyError("jbig2dec - not installed or not found") from e
    else:
        result = proc.stdout
        version_str = result.replace('jbig2dec', '').strip()  # returns "jbig2dec 0.xx"
        version = Version(version_str)
        if version < Version('0.15'):
            raise DependencyError("jbig2dec is too old (older than version 0.15)")


def jbig2dec_available() -> bool:
    try:
        assert_jbig2dec_available()
    except (DependencyError, CalledProcessError, FileNotFoundError):
        return False
    else:
        return True


class JBIG2DecoderInterface(ABC):
    @abstractmethod
    def available(self) -> bool:
        ...

    @abstractmethod
    def assert_available(self) -> None:
        ...

    @abstractmethod
    def decode_jbig2(self, jbig2: bytes, jbig2_globals: bytes) -> bytes:
        ...


class JBIG2Decoder(JBIG2DecoderInterface):
    def available(self) -> bool:
        return jbig2dec_available()

    def assert_available(self) -> None:
        assert_jbig2dec_available()

    def decode_jbig2(self, jbig2: bytes, jbig2_globals: bytes) -> bytes:
        return extract_jbig2_bytes(jbig2, jbig2_globals)


def get_decoder():
    return JBIG2Decoder()
