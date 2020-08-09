import sys
from glob import glob
from os import cpu_count, environ
from os.path import dirname, exists, join, sep
from tempfile import TemporaryDirectory

import setuptools
from setuptools import Extension, setup
from setuptools.command.build_ext import build_ext


class get_pybind_include(object):
    """Helper class to determine the pybind11 include path

    The purpose of this class is to postpone importing pybind11
    until it is actually installed, so that the ``get_include()``
    method can be invoked. """

    def __str__(self):
        # If we are vendoring use the vendored version
        if exists('src/vendor/pybind11'):
            return 'src/vendor/pybind11/include'
        import pybind11

        return pybind11.get_include()


extra_includes = []
extra_library_dirs = []
qpdf_source_tree = environ.get('QPDF_SOURCE_TREE', None)
if qpdf_source_tree:
    # Point this to qpdf source tree built with shared libaries
    extra_includes.append(join(qpdf_source_tree, 'include'))
    extra_library_dirs.append(join(qpdf_source_tree, 'libqpdf/build/.libs'))
if 'bsd' in sys.platform:
    extra_includes.append('/usr/local/include')


ext_modules = [
    Extension(
        'pikepdf._qpdf',
        sorted(glob('src/qpdf/*.cpp')),
        depends=sorted(glob('src/qpdf/*.h')),
        include_dirs=[
            # Path to pybind11 headers
            get_pybind_include(),
            *extra_includes,
        ],
        library_dirs=[*extra_library_dirs],
        libraries=['qpdf'],
        language='c++',
    )
]


# As of Python 3.6, CCompiler has a `has_flag` method.
# cf http://bugs.python.org/issue26689
def has_flag(compiler, flagname):
    """Return a boolean indicating whether a flag name is supported on
    the specified compiler.
    """
    with TemporaryDirectory(prefix='has_flag__') as tmpdir:
        fname = join(tmpdir, 'flagcheck.cpp')
        with open(fname, "w") as f:
            f.write('int main (int argc, char **argv) { return 0; }')
        try:
            # distutils/ccompiler.py, unixcompiler.py, etc.
            # compiler.compile generates output file at
            # os.path.join(output_dir, fname[1:]) - drops leading /,
            # so we use output_dir == '/' to put it back on
            # not sure what Windows does so leave it alone
            outdir = sep if sys.platform != 'win32' else None
            compiler.compile([fname], extra_postargs=[flagname], output_dir=outdir)
        except setuptools.distutils.errors.CompileError:
            return False
    return True


def cpp_flag(compiler):
    """Return the -std=c++[XX] compiler flag.

    Notes on c++17 and macOS:
    https://github.com/pybind/python_example/issues/44
    """
    if sys.platform == 'cygwin':
        flags = ['-std=gnu++14']  # For strdup()
    else:
        flags = ['-std=c++14']

    for flag in flags:
        if has_flag(compiler, flag):
            return flag
    raise RuntimeError('Unsupported compiler -- at least C++14 support ' 'is needed!')


class BuildExt(build_ext):
    """A custom build extension for adding compiler-specific options."""

    c_opts = {'msvc': ['/EHsc'], 'unix': []}
    l_opts = {'msvc': [], 'unix': []}

    if sys.platform == 'darwin':
        darwin_opts = ['-stdlib=libc++', '-mmacosx-version-min=10.9']
        c_opts['unix'] += darwin_opts
        l_opts['unix'] += darwin_opts

    def finalize_options(self):
        super().finalize_options()
        if not self.parallel:
            try:
                self.parallel = int(environ.get("MAX_CONCURRENCY", min(4, cpu_count())))
            except TypeError:
                self.parallel = None

    def build_extensions(self):
        ct = self.compiler.compiler_type
        opts = self.c_opts.get(ct, [])
        link_opts = self.l_opts.get(ct, [])
        if ct == 'unix':
            opts.append(cpp_flag(self.compiler))
            if has_flag(self.compiler, '-fvisibility=hidden'):
                opts.append('-fvisibility=hidden')

        for ext in self.extensions:
            ext.define_macros = [
                ('VERSION_INFO', '"{}"'.format(self.distribution.get_version()))
            ]
            ext.extra_compile_args = opts
            ext.extra_link_args = link_opts
        super().build_extensions()


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
    if sys.version_info >= (3, 6):
        try:
            import mp_compile

            mp_compile.install()
        except ModuleNotFoundError:
            pass
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
        extras_require={'docs': docs_require},
        cmdclass={'build_ext': BuildExt},
        zip_safe=False,
        python_requires='>=3.5',
        setup_requires=[
            'setuptools_scm',
            'setuptools_scm_git_archive',
            'pybind11 >= 2.4.3, < 3',
        ],
        use_scm_version=True,
        tests_require=tests_require,
        package_dir={'': 'src'},
        packages=setuptools.find_packages('src'),
        package_data={'': ['*.txt'], 'pikepdf': ['*.dll']},
        classifiers=[
            "Development Status :: 5 - Production/Stable",
            "Intended Audience :: Developers",
            "Intended Audience :: Information Technology",
            "License :: OSI Approved :: Mozilla Public License 2.0 (MPL 2.0)",
            "Programming Language :: Python :: 3.5",
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
