# SPDX-FileCopyrightText: 2022 James R. Barlow
# SPDX-License-Identifier: MPL-2.0

# The exception hierarchy, created in src/core/pikepdf.cpp.
# See pikepdf/_core/__init__.pyi for how this stub package is laid out.

# pylint: disable=no-method-argument,unused-argument,no-self-use,too-many-public-methods
# ruff: noqa: D418
# mypy: disable-error-code="misc"

from __future__ import annotations

class PikepdfError(Exception):
    """Root of the pikepdf exception hierarchy.

    Every exception pikepdf raises on its own behalf derives from this, so
    ``except PikepdfError`` catches all of them. It does not catch the built-in
    exceptions pikepdf raises for ordinary programming errors (``ValueError``,
    ``TypeError``, ``KeyError``, ``NotImplementedError``), the ``OSError``
    family raised by file access, or exceptions raised by Pillow during image
    extraction.

    .. versionadded:: 10.13
    """

class PdfError(PikepdfError):
    """General pikepdf-specific exception.

    Raised when a document is defective in some way. See also its subclasses
    :class:`DataDecodingError` and :class:`ReferenceCycleError`.
    """

class DataDecodingError(PdfError):
    """Exception thrown when a stream object in a PDF cannot be decoded.

    .. versionchanged:: 10.13
        Now derives from :class:`PdfError`, so ``except PdfError`` around
        :meth:`Object.read_bytes` also catches undecodable streams. Previously
        it was a sibling of ``PdfError``.
    """

class JobUsageError(PikepdfError):
    """Exception thrown when the pikepdf.Job interface is used incorrectly."""

class PasswordError(PikepdfError):
    """Exception thrown when the supplied password is incorrect.

    Deliberately *not* a :class:`PdfError`: a wrong password does not mean the
    document is defective. Handlers that distinguish the two can order
    ``except PdfError`` before ``except PasswordError`` safely.
    """

class ReferenceCycleError(PdfError):
    """When a direct (non-indirect) object would be made to contain itself.

    A direct object may not contain itself, directly or indirectly. Make one of
    the objects indirect with :meth:`Pdf.make_indirect` to create a reference
    cycle.

    .. versionadded:: 10.8
    """

class ForeignObjectError(PikepdfError):
    """When a complex object is copied into a foreign PDF without proper methods.

    Use :meth:`Pdf.copy_foreign`.
    """

class DeletedObjectError(PikepdfError):
    """When a required object is accessed after deletion.

    Thrown when accessing a :class:`Object` that relies on a :class:`Pdf`
    that was deleted using the Python ``delete`` statement or collected by the
    Python garbage collector. To resolve this error, you must retain a reference
    to the Pdf for the whole time you may be accessing it.

    .. versionadded:: 7.0
    """
