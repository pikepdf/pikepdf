# SPDX-FileCopyrightText: 2022 James R. Barlow
# SPDX-License-Identifier: MPL-2.0

"""pikepdf global settings."""

from __future__ import annotations

from pikepdf._core import (
    _get_qpdf_global,
    _set_qpdf_global,
    get_decimal_precision,
    set_decimal_precision,
    set_flate_compression_level,
)

__all__ = [
    'disable_qpdf_default_limits',
    'get_decimal_precision',
    'get_qpdf_limits',
    'qpdf_limit_errors',
    'set_decimal_precision',
    'set_flate_compression_level',
    'set_qpdf_limits',
]

_QPDF_INT_LIMITS = (
    'doc_max_warnings',
    'parser_max_nesting',
    'parser_max_errors',
    'parser_max_container_size',
    'parser_max_container_size_damaged',
    'max_stream_filters',
    'dct_max_memory',
    'dct_max_progressive_scans',
    'flate_max_memory',
    'png_max_memory',
    'run_length_max_memory',
    'tiff_max_memory',
)
_QPDF_BOOL_OPTIONS = ('dct_throw_on_corrupt_data',)
_UINT32_MAX = 2**32 - 1


def get_qpdf_limits() -> dict[str, int | bool]:
    """Return qpdf's current global limits, keyed by name.

    The keys are the keyword arguments accepted by :func:`set_qpdf_limits`, so
    the result can be saved and later restored with
    ``set_qpdf_limits(**saved)``.
    """
    limits: dict[str, int | bool] = {
        name: _get_qpdf_global(name) for name in _QPDF_INT_LIMITS
    }
    for name in _QPDF_BOOL_OPTIONS:
        limits[name] = bool(_get_qpdf_global(name))
    return limits


def set_qpdf_limits(
    *,
    doc_max_warnings: int | None = None,
    parser_max_nesting: int | None = None,
    parser_max_errors: int | None = None,
    parser_max_container_size: int | None = None,
    parser_max_container_size_damaged: int | None = None,
    max_stream_filters: int | None = None,
    dct_max_memory: int | None = None,
    dct_max_progressive_scans: int | None = None,
    flate_max_memory: int | None = None,
    png_max_memory: int | None = None,
    run_length_max_memory: int | None = None,
    tiff_max_memory: int | None = None,
    dct_throw_on_corrupt_data: bool | None = None,
) -> dict[str, int | bool]:
    """Set qpdf's global limits, which guard against malicious or damaged PDFs.

    Arguments left as ``None`` are unchanged. All values are checked before any
    is applied, so an invalid argument leaves every limit as it was.

    These limits are process-wide: they affect every :class:`pikepdf.Pdf` in the
    process, including those used by other libraries, and qpdf does not
    synchronize access to them. Set them once at startup, before other threads
    use pikepdf. :meth:`pikepdf.JobBuilder.limits` changes the same settings.

    Args:
        doc_max_warnings: Maximum number of warnings a newly opened
            :class:`pikepdf.Pdf` accepts before giving up; ``0`` (the default)
            means no limit.
        parser_max_nesting: Maximum nesting depth of arrays and dictionaries
            while parsing. Default 499.
        parser_max_errors: Maximum number of errors while parsing an object or
            content stream before qpdf gives up; ``0`` means no limit. Default 15.
            Content stream parsing stops silently, apart from a warning, when
            this limit is reached, so raise it or set it to ``0`` to recover as
            much of a badly damaged content stream as possible.
        parser_max_container_size: Maximum number of items in an array or
            dictionary while parsing. Default 4294967295.
        parser_max_container_size_damaged: As ``parser_max_container_size``,
            while recovering a damaged file. Default 5000.
        max_stream_filters: Maximum number of filters a stream may have and
            still be decoded. Default 25.
        dct_max_memory: Maximum memory in bytes for decoding a DCT (JPEG)
            stream; ``0`` (the default) means no limit.
        dct_max_progressive_scans: Maximum number of progressive scans when
            decoding a DCT (JPEG) stream; ``0`` (the default) means no limit.
        flate_max_memory: Maximum memory in bytes for decoding a Flate stream;
            ``0`` (the default) means no limit.
        png_max_memory: Maximum memory in bytes for PNG predictors; ``0`` (the
            default) means no limit.
        run_length_max_memory: Maximum memory in bytes for decoding a
            RunLength stream; ``0`` (the default) means no limit.
        tiff_max_memory: Maximum memory in bytes for TIFF predictors; ``0``
            (the default) means no limit.
        dct_throw_on_corrupt_data: If True (the default), decoding corrupt DCT
            (JPEG) data raises an error; if False, qpdf decodes as much as it
            can.

    Returns:
        The previous values of the limits that were given, so that
        ``set_qpdf_limits(**previous)`` restores them.
    """
    requested = dict(locals())  # exactly the keyword arguments
    changes: dict[str, int | bool] = {}
    for name, value in requested.items():
        if value is None:
            continue
        if name in _QPDF_BOOL_OPTIONS:
            if not isinstance(value, bool):
                raise TypeError(f"{name} must be a bool")
        else:
            if isinstance(value, bool) or not isinstance(value, int):
                raise TypeError(f"{name} must be an int")
            if not 0 <= value <= _UINT32_MAX:
                raise ValueError(f"{name} must be between 0 and {_UINT32_MAX}")
        changes[name] = value

    previous = get_qpdf_limits()
    for name, value in changes.items():
        _set_qpdf_global(name, int(value))
    return {name: previous[name] for name in changes}


def disable_qpdf_default_limits() -> None:
    """Disable qpdf's optional default limits, for the rest of the process.

    ``parser_max_errors`` becomes unlimited, and ``max_stream_filters`` and
    ``parser_max_container_size_damaged`` become effectively unlimited, unless
    they were already set explicitly. ``parser_max_nesting`` still applies,
    since it prevents stack overflows. Limits set explicitly afterward with
    :func:`set_qpdf_limits` still apply.

    This cannot be undone. Like :func:`set_qpdf_limits`, it affects the whole
    process.
    """
    _set_qpdf_global('default_limits', 0)


def qpdf_limit_errors() -> int:
    """Return how many times any qpdf global limit has been exceeded.

    The count covers the whole process since startup and never decreases,
    which makes it useful for noticing that a limit was hit when qpdf only
    issued a warning, such as content stream parsing stopping at
    ``parser_max_errors``.
    """
    return _get_qpdf_global('limit_errors')
