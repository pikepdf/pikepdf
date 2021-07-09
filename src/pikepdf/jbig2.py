# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.
#
# Copyright (C) 2017, James R. Barlow (https://github.com/jbarlow83/)

import os
from distutils.version import LooseVersion
from subprocess import DEVNULL, PIPE, CalledProcessError, run
from tempfile import TemporaryDirectory

from PIL import Image

import pikepdf


def extract_jbig2(im_obj: pikepdf.Object, globals_obj: pikepdf.Object = None) -> Image:

    with TemporaryDirectory() as tmpdir:
        image_fname = os.path.join(tmpdir, "image")
        global_fname = os.path.join(tmpdir, "global")
        output_fname = os.path.join(tmpdir, "outfile")
        
        args = ["jbig2dec", "-e", "-o", output_fname]

        with open(image_fname) as img_fd:
            img_fd.write(im_obj.read_raw_bytes())

        if globals_obj is not None:
            with open(global_fname) as global_fd:
                global_fd.write(globals_obj.read_raw_bytes())
            args.append(global_fname)

        args.append(image_fname)

        run(args, stdout=DEVNULL, check=True)
        im = Image.open(output_fname)
        im.load() # Load pixel data into memory so file can be closed
        return im


def jbig2dec_available() -> bool:
    try:
        proc = run(['jbig2dec', '--version'], stdout=PIPE, check=True, encoding='ascii')
    except (CalledProcessError, FileNotFoundError):
        return False
    else:
        result = proc.stdout
        version_str = result.replace('jbig2dec', '').strip()  # returns "jbig2dec 0.xx"
        version = LooseVersion(version_str)
        return version >= LooseVersion('0.15')
