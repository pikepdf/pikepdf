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
        # Pre-cmake qpdf build
        old_libdir = join(qpdf_source_tree, 'libqpdf/build/.libs')
        if exists(old_libdir):
            qpdf_build_libdir = old_libdir
    if not qpdf_build_libdir:
        raise Exception(
            'Please set QPDF_BUILD_LIBDIR to the directory'
            ' containing your libqpdf.so built from'
            ' $QPDF_SOURCE_TREE'
        )
    extra_library_dirs.append(join(qpdf_build_libdir))

# If CFLAGS is not defined, a user may be trying to install a sdist. Look around
# their system for places QPDF might be installed.
# If defined, we assume the user is a package maintainer who does not want us
# to be clever.
cflags_defined = bool(environ.get('CFLAGS', ''))
if not cflags_defined and not qpdf_source_tree:
    if 'bsd' in sys.platform:
        extra_includes.append('/usr/local/include')
    elif 'darwin' in sys.platform and machine() == 'arm64':
        extra_includes.append('/opt/homebrew/include')
        extra_library_dirs.append('/opt/homebrew/lib')


for extra_path in chain([qpdf_source_tree], extra_includes, extra_library_dirs):
    if extra_path and not exists(extra_path):
        raise FileNotFoundError(extra_path)

# Use cast because mypy has trouble seeing Pybind11Extension is a subclass of
# Extension.
extmodule: Extension = cast(
    Extension,
    Pybind11Extension(
        'pikepdf._qpdf',
        sorted(glob('src/qpdf/*.cpp')),
        depends=sorted(glob('src/qpdf/*.h')),
        include_dirs=[
            # Path to pybind11 headers
            *extra_includes,
        ],
        library_dirs=[*extra_library_dirs],
        libraries=['qpdf'],
        cxx_std=17,
    ),
)

if not cflags_defined:
    if sys.platform == 'cygwin':
        # On cygwin, use gnu++17 instead of c++17
        eca = extmodule.extra_compile_args
        eca[eca.index('-std=c++17')] = '-std=gnu++17'

    # Debug build
    # module[0].extra_compile_args.append('-g3')

    if qpdf_source_tree:
        for lib in extra_library_dirs:
            extmodule.extra_link_args.append(f'-Wl,-rpath,{lib}')  # type: ignore

if __name__ == '__main__':
    with ParallelCompile("PIKEPDF_NUM_BUILD_JOBS"):  # optional envvar
        setup(
            ext_modules=[extmodule],
            cmdclass={"build_ext": build_ext},  # type: ignore
        )
