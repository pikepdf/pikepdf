# SPDX-FileCopyrightText: 2022 James R. Barlow
# SPDX-License-Identifier: MPL-2.0

"""Exceptions raised while extracting images.

These live outside the ``image`` package because they are also raised by
:mod:`pikepdf.models._transcoding`, which sits beside that package rather than
inside it. Importing them from ``image._shared`` would make ``_transcoding``
depend on the ``image`` package, whose ``__init__`` in turn imports
``_transcoding`` -- a cycle. This module imports nothing but the standard
library, so both sides can depend on it.

The names are re-exported by :mod:`pikepdf.models.image` and
:mod:`pikepdf.exceptions`; those are the supported import locations.
"""

from __future__ import annotations


class UnsupportedImageTypeError(Exception):
    """This image is formatted in a way pikepdf does not supported."""


class NotExtractableError(Exception):
    """Indicates that an image cannot be directly extracted."""


class HifiPrintImageNotTranscodableError(NotExtractableError):
    """Image contains high fidelity printing information and cannot be extracted."""


class InvalidPdfImageError(Exception):
    """This image is not valid according to the PDF 1.7 specification."""


class ImageDecompressionError(Exception):
    """Image decompression error."""
