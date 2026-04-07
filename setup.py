# SPDX-FileCopyrightText: 2022 James R. Barlow
# SPDX-License-Identifier: MPL-2.0

"""Obsolete setup script. pikepdf now uses scikit-build-core + nanobind.

Use: pip install -e .
"""

raise RuntimeError(
    "pikepdf no longer uses setuptools for building. "
    "Use 'pip install -e .' or 'pip install .' instead."
)
