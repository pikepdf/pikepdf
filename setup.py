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

# If CFLAGS is defined, disable any efforts to shim the build, because
# the caller is probably a maintainer and knows what they are doing.
cflags_defined = bool(environ.get('CFLAGS', ''))

if not cflags_defined:
    if qpdf_source_tree:
        # Point this to qpdf source tree built with shared libaries
        extra_includes.append(join(qpdf_source_tree, 'include'))
        extra_library_dirs.append(join(qpdf_source_tree, 'libqpdf/build/.libs'))

    if 'bsd' in sys.platform:
        extra_includes.append('/usr/local/include')
    elif 'darwin' in sys.platform and machine() == 'arm64':
        extra_includes.append('/opt/homebrew/include')
        extra_library_dirs.append('/opt/homebrew/lib')

try:
    from setuptools_scm import get_version

    __version__ = get_version()
except ImportError:
    __version__ = '0.0.1'


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
            setup_requires=[  # can be removed whenever we can drop pip 9 support
                'setuptools_scm',  # so that version will work
                'setuptools_scm_git_archive',  # enable version from github tarballs
            ],
            ext_modules=[extmodule],
            use_scm_version=True,
            cmdclass={"build_ext": build_ext},  # type: ignore
        )
