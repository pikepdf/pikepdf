# SPDX-FileCopyrightText: 2025 James R. Barlow
# SPDX-License-Identifier: MPL-2.0

models_sources = files(
    '__init__.py',
    '_content_stream.py',
    '_transcoding.py',
    'ctm.py',
    'encryption.py',
    'image.py',
    'outlines.py',
)

py.install_sources(
    models_sources,
    subdir: 'pikepdf/models',
)

# Install metadata subpackage
subdir('metadata')
