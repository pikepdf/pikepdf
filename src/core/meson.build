# SPDX-FileCopyrightText: 2025 James R. Barlow
# SPDX-License-Identifier: MPL-2.0

core_sources = files(
    'acroform.cpp',
    'annotation.cpp',
    'embeddedfiles.cpp',
    'job.cpp',
    'logger.cpp',
    'matrix.cpp',
    'namepath.cpp',
    'nametree.cpp',
    'numbertree.cpp',
    'object.cpp',
    'object_convert.cpp',
    'object_equality.cpp',
    'object_repr.cpp',
    'page.cpp',
    'parsers.cpp',
    'pikepdf.cpp',
    'pipeline.cpp',
    'qpdf.cpp',
    'qpdf_pagelist.cpp',
    'rectangle.cpp',
    'tokenfilter.cpp',
)

py.extension_module(
    '_core',
    core_sources,
    dependencies: [pybind11_dep, qpdf_dep],
    cpp_args: cpp_args,
    install: true,
    subdir: 'pikepdf',
)
