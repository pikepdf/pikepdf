# SPDX-FileCopyrightText: 2025 James R. Barlow
# SPDX-License-Identifier: MPL-2.0

project(
    'pikepdf',
    'cpp',
    version: '10.1.0',
    license: 'MPL-2.0',
    meson_version: '>= 1.2.0',
    default_options: [
        'cpp_std=c++20',
        'buildtype=release',
        'warning_level=1',
    ],
)

fs = import('fs')
py = import('python').find_installation(pure: false)

# Find pybind11 - prefer pkg-config, fall back to config-tool (pybind11-config)
pybind11_dep = dependency('pybind11', method: 'auto')

# Find libqpdf - check for local source tree first
qpdf_source_tree = get_option('qpdf_source_tree')
qpdf_build_libdir = get_option('qpdf_build_libdir')

# Auto-detect local qpdf if not specified
if qpdf_source_tree == '' and fs.is_dir('../qpdf')
    qpdf_source_tree = meson.current_source_dir() / '..' / 'qpdf'
    qpdf_build_libdir = qpdf_source_tree / 'build' / 'libqpdf'
    message('Using local qpdf source tree at', qpdf_source_tree)
endif

if qpdf_source_tree != ''
    # Use local qpdf source tree
    qpdf_inc_dir = qpdf_source_tree / 'include'
    qpdf_libdir = qpdf_build_libdir
    cpp = meson.get_compiler('cpp')
    qpdf_lib = cpp.find_library('qpdf', dirs: qpdf_libdir, required: true)
    qpdf_dep = declare_dependency(
        compile_args: ['-I' + qpdf_inc_dir],
        link_args: ['-L' + qpdf_libdir, '-Wl,-rpath,' + qpdf_libdir],
        dependencies: qpdf_lib,
    )
else
    # Find libqpdf via pkg-config/cmake
    qpdf_dep = dependency('libqpdf', version: '>= 11.0.0')
endif

# Optional: QPDF_FUTURE macro for testing upcoming qpdf features
qpdf_future = get_option('qpdf_future')
cpp_args = []
if qpdf_future
    cpp_args += ['-DQPDF_FUTURE=True']
endif

subdir('src/core')
subdir('src/pikepdf')
