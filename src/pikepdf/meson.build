# SPDX-FileCopyrightText: 2025 James R. Barlow
# SPDX-License-Identifier: MPL-2.0

# Install all Python files in the pikepdf package
python_sources = files(
    '__init__.py',
    '_augments.py',
    '_cpphelpers.py',
    '_data.py',
    '_exceptions.py',
    '_explicit_conv.py',
    '_io.py',
    '_methods.py',
    '_version.py',
    '_xml.py',
    'canvas.py',
    'codec.py',
    'exceptions.py',
    'form.py',
    'jbig2.py',
    'objects.py',
    'settings.py',
)

py.install_sources(
    python_sources,
    subdir: 'pikepdf',
)

# Install type stubs
py.install_sources(
    files('py.typed'),
    subdir: 'pikepdf',
)

# Install .pyi files
py.install_sources(
    files('_core.pyi'),
    subdir: 'pikepdf',
)

# Install models subpackage
subdir('models')
