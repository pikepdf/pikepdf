# SPDX-FileCopyrightText: 2022 James R. Barlow
# SPDX-License-Identifier: MPL-2.0

from __future__ import annotations

import sys
from glob import glob
from itertools import chain
from os import environ
from os.path import exists, join
from platform import machine
from typing import cast

from pybind11.setup_helpers import ParallelCompile, Pybind11Extension, build_ext
from setuptools import Extension, setup

extra_includes = []
extra_library_dirs = []
qpdf_source_tree = environ.get('QPDF_SOURCE_TREE', '')
qpdf_build_libdir = environ.get('QPDF_BUILD_LIBDIR', '')

if qpdf_source_tree:
    # Point this to qpdf source tree built with shared libraries
    extra_includes.append(join(qpdf_source_tree, 'include'))
    if not qpdf_build_libdir:
        raise Exception(
            'Please set QPDF_BUILD_LIBDIR to the directory'
            ' containing your libqpdf.so built from'
            ' $QPDF_SOURCE_TREE'
        )
    extra_library_dirs.append(join(qpdf_build_libdir))

# Here we have two different use cases. Some users will end up here because
# their package manager couldn't find a suitable binary wheel and they have to
# compile from source. Also downstream maintainers prefer sdists.
# Our priority is trying to make things work as cleanly as possible for users
# who want to do a source build. It's an imperfect test, but downstream build
# environments usually define CFLAGS to something interesting, and users who call
# "pip install pikepdf" probably don't. So we use this to check if we activate
# shims.
cflags_defined = bool(environ.get('CFLAGS', ''))
shims_enabled = not cflags_defined

# If shims are enabled, we add some known locations where QPDF and other third party
# libraries might be installed, in hopes the build will succeed if we suggest the
# obvious.
if shims_enabled and not qpdf_source_tree:
    if 'bsd' in sys.platform:
        shim_includes = ['/usr/local/include']
        shim_libdirs = []
    elif 'darwin' in sys.platform and machine() == 'arm64':
        shim_includes = ['/opt/homebrew/include', '/opt/local/include']
        shim_libdirs = ['/opt/homebrew/lib', '/opt/local/lib']
    else:
        shim_includes = []
        shim_libdirs = []
    extra_includes.extend(shim for shim in shim_includes if exists(shim))
    extra_library_dirs.extend(shim for shim in shim_libdirs if exists(shim))

# Regardless of shimming, we want to let users know when some parameter they supplied
# resulted in a non-existent path being added to the list, so they can figure out
# what went wrong.
for extra_path in chain([qpdf_source_tree], extra_includes, extra_library_dirs):
    if extra_path and not exists(extra_path):
        raise FileNotFoundError(extra_path)

# Use cast because mypy has trouble seeing Pybind11Extension is a subclass of
# Extension.
extmodule: Extension = cast(
    Extension,
    Pybind11Extension(
        'pikepdf._core',
        sources=sorted(glob('src/core/*.cpp')),
        depends=sorted(glob('src/core/*.h')),
        include_dirs=[
            # Path to pybind11 headers
            *extra_includes,
        ],
        define_macros=[('POINTERHOLDER_TRANSITION', '4')],
        library_dirs=[*extra_library_dirs],
        libraries=['qpdf'],
        cxx_std=17,
    ),
)

if shims_enabled:
    eca = extmodule.extra_compile_args
    if sys.platform == 'cygwin':
        # On cygwin, use gnu++17 instead of c++17
        eca[eca.index('-std=c++17')] = '-std=gnu++17'

    # Debug build
    # eca.append('-g3')

    if qpdf_source_tree:
        for lib in extra_library_dirs:
            extmodule.extra_link_args.append(f'-Wl,-rpath,{lib}')  # type: ignore

if __name__ == '__main__':
    with ParallelCompile("PIKEPDF_NUM_BUILD_JOBS"):  # optional envvar
        setup(
            ext_modules=[extmodule],
            cmdclass={"build_ext": build_ext},  # type: ignore
        )
