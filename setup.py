import sys
from glob import glob
from os import environ
from os.path import dirname, join

from setuptools import find_packages, setup

try:
    from pybind11.setup_helpers import ParallelCompile, Pybind11Extension, build_ext
except ImportError:
    from setuptools import Extension as Pybind11Extension
    from setuptools.command.build_ext import build_ext

    ParallelCompile = None
    print("pybind11.setup_helpers NOT loaded - you might need to pip install pybind11")

if ParallelCompile:
    try:
        # Prevent parallel compile on platforms that lack semaphores
        # e.g. Android/Termux, AWS Lambda
        import multiprocessing.synchronize  # pylint: disable=unused-import lgtm [py/unused-import]
    except ImportError:
        ParallelCompile = None

extra_includes = []
extra_library_dirs = []
qpdf_source_tree = environ.get('QPDF_SOURCE_TREE', None)
if qpdf_source_tree:
    # Point this to qpdf source tree built with shared libaries
    extra_includes.append(join(qpdf_source_tree, 'include'))
    extra_library_dirs.append(join(qpdf_source_tree, 'libqpdf/build/.libs'))
if 'bsd' in sys.platform:
    extra_includes.append('/usr/local/include')

try:
    from setuptools_scm import get_version

    __version__ = get_version()
except ImportError:
    __version__ = '0.0.1'


ext_modules = [
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
        cxx_std=14,
    )
]

if sys.platform == 'cygwin':
    # On cygwin, use gnu++14 instead of c++14
    eca = ext_modules[0].extra_compile_args
    eca[eca.index('-std=c++14')] = '-std=gnu++14'

# Debug build
# ext_modules[0].extra_compile_args.append('-g3')


if __name__ == '__main__':
    if ParallelCompile:
        ParallelCompile().install()
    setup(
        setup_requires=[  # can be removed whenever we can drop pip 9 support
            'setuptools_scm',  # so that version will work
            'setuptools_scm_git_archive',  # enable version from github tarballs
        ],
        ext_modules=ext_modules,
        use_scm_version=True,
        cmdclass={"build_ext": build_ext},
    )
