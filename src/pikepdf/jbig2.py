# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.
#
# Copyright (C) 2017, James R. Barlow (https://github.com/jbarlow83/)

import os
from pathlib import Path
from subprocess import DEVNULL, PIPE, CalledProcessError, run
from tempfile import TemporaryDirectory
from typing import Optional, cast

from packaging.version import Version
from PIL import Image

import pikepdf


def extract_jbig2(
    im_obj: pikepdf.Object, globals_obj: Optional[pikepdf.Object] = None
) -> Image.Image:

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


def jbig2dec_available() -> bool:
    try:
        proc = run(['jbig2dec', '--version'], stdout=PIPE, check=True, encoding='ascii')
    except (CalledProcessError, FileNotFoundError):
        return False
    else:
        result = proc.stdout
        version_str = result.replace('jbig2dec', '').strip()  # returns "jbig2dec 0.xx"
        version = Version(version_str)
        return version >= Version('0.15')
