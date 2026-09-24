# SPDX-FileCopyrightText: 2026 James R. Barlow
# SPDX-License-Identifier: MPL-2.0

"""Attaching the local time zone to dates that have none."""

from __future__ import annotations

import datetime as dt

from pikepdf.models.metadata import decode_pdf_date, encode_pdf_date
from pikepdf.models.metadata._converters import parse_xmp_date


def _attach_local_time_zone(naive: dt.datetime) -> dt.datetime | None:
    """Return *naive* with the local time zone attached, or None on failure.

    ``astimezone()`` interprets a naive datetime as local time. Some platforms
    cannot convert dates outside the range of the C library's time functions,
    such as dates before 1970 on Windows.
    """
    try:
        return naive.astimezone()
    except (ValueError, OverflowError, OSError):
        return None


def assume_local_time_zone(pdf_date: str) -> tuple[str, bool]:
    """Attach the local time zone to a PDF date string that has none.

    PDF dates may omit the time zone, in which case their relation to UTC is
    unknown. PDF/A validators disagree on how to interpret such dates, so we
    assume the date is local time on this machine.

    Args:
        pdf_date: A PDF date string, such as ``D:20160119123847``.

    Returns:
        The date string, with the local time zone attached if it had none,
        and True if it was changed. Strings that are not PDF dates, or already
        have a time zone, are returned unchanged.
    """
    try:
        parsed = decode_pdf_date(pdf_date)
    except (ValueError, TypeError):
        return pdf_date, False
    if parsed.tzinfo is not None:
        return pdf_date, False
    zoned = _attach_local_time_zone(parsed)
    if zoned is None:
        return pdf_date, False
    return encode_pdf_date(zoned), True


def assume_local_time_zone_iso(xmp_date: str) -> tuple[str, bool]:
    """Attach the local time zone to an XMP (ISO 8601) date that has none.

    Args:
        xmp_date: An XMP date, such as ``2016-01-19T12:38:47``.

    Returns:
        The date, with the local time zone attached if it had none, and True
        if it was changed. Strings that cannot be parsed, or already have a
        time zone, are returned unchanged.
    """
    try:
        parsed = parse_xmp_date(xmp_date.strip())
    except (ValueError, TypeError, AttributeError):
        return xmp_date, False
    if parsed.tzinfo is not None:
        return xmp_date, False
    zoned = _attach_local_time_zone(parsed)
    if zoned is None:
        return xmp_date, False
    return zoned.isoformat(), True
