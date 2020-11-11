import sys
from glob import glob
from os import environ
from os.path import dirname, join

from setuptools import find_packages, setup

try:
    from pybind11.setup_helpers import Pybind11Extension, build_ext
except ImportError:
    from setuptools import Extension as Pybind11Extension
    from setuptools.command.build_ext import build_ext

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

setup_py_cwd = dirname(__file__)

with open(join(setup_py_cwd, 'requirements/docs.txt')) as f:
    docs_require = [
        line.strip() for line in f if line.strip() and not line.strip().startswith('#')
    ]


with open(join(setup_py_cwd, 'requirements/test.txt')) as f:
    tests_require = [
        line.strip() for line in f if line.strip() and not line.strip().startswith('#')
    ]

with open(join(setup_py_cwd, 'README.md'), encoding='utf-8') as f:
    readme = f.read()

if __name__ == '__main__':  # for mp_compile
    setup(
        name='pikepdf',
        author='James R. Barlow',
        author_email='james@purplerock.ca',
        url='https://github.com/pikepdf/pikepdf',
        description='Read and write PDFs with Python, powered by qpdf',
        long_description=readme,
        long_description_content_type='text/markdown',
        ext_modules=ext_modules,
        install_requires=[
            'lxml >= 4.0',
            'Pillow >= 6',  # only needed for manipulating images
        ],
        setup_requires=[
            'setuptools >= 50',
            'wheel >= 0.35',
            'setuptools_scm[toml] >= 4.1',
            'setuptools_scm_git_archive',
            'pybind11 >= 2.6.0, <3',
        ],
        extras_require={'docs': docs_require},
        zip_safe=False,
        python_requires='>=3.6',
        use_scm_version=True,
        tests_require=tests_require,
        cmd_class={"build_ext": build_ext},
        package_dir={'': 'src'},
        packages=find_packages('src'),
        package_data={'': ['*.txt'], 'pikepdf': ['*.dll', 'py.typed']},
        classifiers=[
            "Development Status :: 5 - Production/Stable",
            "Intended Audience :: Developers",
            "Intended Audience :: Information Technology",
            "License :: OSI Approved :: Mozilla Public License 2.0 (MPL 2.0)",
            "Programming Language :: Python :: 3.6",
            "Programming Language :: Python :: 3.7",
            "Programming Language :: Python :: 3.8",
            "Programming Language :: Python :: 3.9",
            "Programming Language :: Python :: 3 :: Only",
            "Programming Language :: C++",
            "Topic :: Multimedia :: Graphics",
            "Topic :: Software Development :: Libraries",
        ],
        project_urls={
            'Documentation': 'https://pikepdf.readthedocs.io/',
            'Source': 'https://github.com/pikepdf/pikepdf',
            'Tracker': 'https://github.com/pikepdf/pikepdf/issues',
        },
    )
