# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.
#
# Copyright (C) 2017, James R. Barlow (https://github.com/jbarlow83/)

from distutils.version import LooseVersion
from subprocess import DEVNULL, PIPE, CalledProcessError, run
from tempfile import NamedTemporaryFile as NamedTemp

from PIL import Image

import pikepdf


def extract_jbig2(im_obj: pikepdf.Object, globals_obj: pikepdf.Object = None) -> Image:
    with NamedTemp() as imgfile, NamedTemp() as globalfile, NamedTemp() as outfile:
        imgfile.write(im_obj.read_raw_bytes())
        imgfile.seek(0)

        args = ['jbig2dec', '-e', '-o', outfile.name]
        if globals_obj is not None:
            globalfile.write(globals_obj.read_raw_bytes())
            globalfile.seek(0)
            args.append(globalfile.name)
        args.append(imgfile.name)

        run(args, stdout=DEVNULL, check=True)
        im = Image.open(outfile)
        im.load()  # Load pixel data into memory so file can be closed
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
