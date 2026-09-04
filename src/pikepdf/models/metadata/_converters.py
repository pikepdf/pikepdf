# SPDX-FileCopyrightText: 2022 James R. Barlow
# SPDX-License-Identifier: MPL-2.0

"""Converters for XMP <-> DocumentInfo value transformation."""

from __future__ import annotations

import re
from abc import ABC, abstractmethod
from datetime import date, datetime, timedelta, timezone
from typing import Any, NamedTuple

from pikepdf.models.metadata._constants import XMP_NS_DC, XMP_NS_PDF, XMP_NS_XMP
from pikepdf.objects import String


def encode_pdf_date(d: datetime) -> str:
    """Encode Python datetime object as PDF date string.

    From Adobe pdfmark manual:
    (D:YYYYMMDDHHmmSSOHH'mm')
    D: is an optional prefix. YYYY is the year. All fields after the year are
    optional. MM is the month (01-12), DD is the day (01-31), HH is the
    hour (00-23), mm are the minutes (00-59), and SS are the seconds
    (00-59). The remainder of the string defines the relation of local
    time to GMT. O is either + for a positive difference (local time is
    later than GMT) or - (minus) for a negative difference. HH' is the
    absolute value of the offset from GMT in hours, and mm' is the
    absolute value of the offset in minutes. If no GMT information is
    specified, the relation between the specified time and GMT is
    considered unknown. Regardless of whether or not GMT
    information is specified, the remainder of the string should specify
    the local time.

    'D:' is required in PDF/A, so we always add it.
    """
    # The formatting of %Y is not consistent as described in
    # https://bugs.python.org/issue13305 and underspecification in libc.
    # So explicitly format the year with leading zeros
    s = f"D:{d.year:04d}"
    s += d.strftime(r'%m%d%H%M%S')
    tz = d.strftime('%z')
    if tz:
        sign, tz_hours, tz_mins = tz[0], tz[1:3], tz[3:5]
        s += f"{sign}{tz_hours}'{tz_mins}"
    return s


def decode_pdf_date(s: str) -> datetime:
    """Decode a pdfmark date to a Python datetime object.

    A pdfmark date is a string in a particular format, as described in
    :func:`encode_pdf_date`.
    """
    if isinstance(s, String):
        s = str(s)
    t = s
    if t.startswith('D:'):
        t = t[2:]
    utcs = [
        "Z00'00'",  # Literal Z00'00', is incorrect but found in the wild
        "Z00'00",  # Correctly formatted UTC
        "Z",  # Alternate UTC
    ]
    for utc in utcs:
        if t.endswith(utc):
            t = t.replace(utc, "+0000")
            break
    t = t.replace("'", "")  # Remove apos from PDF time strings

    date_formats = [
        r"%Y%m%d%H%M%S%z",  # Format with timezone
        r"%Y%m%d%H%M%S",  # Format without timezone
        r"%Y%m%d",  # Date only format
    ]
    for date_format in date_formats:
        try:
            return datetime.strptime(t, date_format)
        except ValueError:
            continue
    raise ValueError(f"Date string does not match any known format: {s} (read as {t})")


# XMP Specification Part 1, 8.2.1.2: a subset of W3C Date and Time Formats.
# The time zone designator is Z or +hh:mm or -hh:mm; the colon is also
# accepted as absent, since that form is found in the wild. Fractions of a
# second may have any number of digits.
_re_xmp_date = re.compile(
    r"""
    (?P<year>\d{4})
    (?:-(?P<month>\d{2})
      (?:-(?P<day>\d{2})
        (?:T(?P<hour>\d{2}):(?P<minute>\d{2})
          (?::(?P<second>\d{2})(?:\.(?P<fraction>\d+))?)?
          (?P<tz>Z|[+-]\d{2}:?\d{2})?
        )?
      )?
    )?
    $""",
    re.VERBOSE,
)


def parse_xmp_date(s: str) -> datetime:
    """Parse an XMP date, which is a subset of ISO 8601, to a datetime.

    XMP allows any number of digits in the fraction of a second and, as
    written in the wild, a time zone offset with or without a colon.
    :meth:`datetime.fromisoformat` accepts neither on Python 3.10, so XMP
    dates are parsed here. A missing time zone gives a naive datetime, since
    XMP says the time zone is then unknown. A year or year-month alone is
    not a datetime; callers handle those forms before calling this.
    """
    m = _re_xmp_date.match(s)
    if m is None or m['day'] is None:
        raise ValueError(f"Date string is not a valid XMP date: {s!r}")
    fraction = m['fraction']
    microsecond = int(fraction[:6].ljust(6, '0')) if fraction else 0
    tzinfo = None
    if m['tz'] == 'Z':
        tzinfo = timezone.utc
    elif m['tz']:
        sign = -1 if m['tz'][0] == '-' else 1
        digits = m['tz'][1:].replace(':', '')
        offset = timedelta(hours=int(digits[:2]), minutes=int(digits[2:]))
        tzinfo = timezone(sign * offset)
    return datetime(
        int(m['year']),
        int(m['month']),
        int(m['day']),
        int(m['hour'] or 0),
        int(m['minute'] or 0),
        int(m['second'] or 0),
        microsecond,
        tzinfo=tzinfo,
    )


def encode_xmp_date(d: datetime | date) -> str:
    """Encode a datetime or date as an XMP date string.

    A time zone offset that is not a whole number of minutes is rounded to
    the nearest minute, since XMP allows only ``+hh:mm`` and ``-hh:mm``.
    """
    if not isinstance(d, datetime):
        return d.isoformat()
    offset = d.utcoffset()
    if offset is not None and offset.total_seconds() % 60:
        minutes = round(offset.total_seconds() / 60)
        d = d.replace(tzinfo=timezone(timedelta(minutes=minutes)))
    return d.isoformat()


class Converter(ABC):
    """XMP <-> DocumentInfo converter."""

    @staticmethod
    @abstractmethod
    def xmp_from_docinfo(docinfo_val: str | None) -> Any:  # type: ignore
        """Derive XMP metadata from a DocumentInfo string."""

    @staticmethod
    @abstractmethod
    def docinfo_from_xmp(xmp_val: Any) -> str | None:
        """Derive a DocumentInfo value from equivalent XMP metadata."""


class AuthorConverter(Converter):
    """Convert XMP document authors to DocumentInfo."""

    @staticmethod
    def xmp_from_docinfo(docinfo_val: str | None) -> Any:  # type: ignore
        """Derive XMP authors info from DocumentInfo."""
        return [docinfo_val]

    @staticmethod
    def docinfo_from_xmp(xmp_val):
        """Derive DocumentInfo authors from XMP.

        XMP supports multiple author values, while DocumentInfo has a string,
        so we return the values separated by semi-colons.
        """
        if isinstance(xmp_val, str):
            return xmp_val
        if xmp_val is None or xmp_val == [None]:
            return None
        return '; '.join(author for author in xmp_val if author is not None)


class DateConverter(Converter):
    """Convert XMP dates to DocumentInfo."""

    @staticmethod
    def xmp_from_docinfo(docinfo_val):
        """Derive XMP date from DocumentInfo."""
        if isinstance(docinfo_val, String):
            docinfo_val = str(docinfo_val)
        if docinfo_val == '':
            return ''
        val = docinfo_val[2:] if docinfo_val.startswith('D:') else docinfo_val
        if len(val) in (4, 6, 8) and val.isdigit():
            # Reduced precision: keep year, year-month, or date only as is
            return '-'.join(filter(None, (val[:4], val[4:6], val[6:8])))
        return decode_pdf_date(docinfo_val).isoformat()

    @staticmethod
    def docinfo_from_xmp(xmp_val):
        """Derive DocumentInfo from XMP."""
        if len(xmp_val) in (4, 7) and 'T' not in xmp_val:
            # Reduced precision: year or year-month only
            return f'D:{xmp_val.replace("-", "")}'
        if len(xmp_val) == 10 and 'T' not in xmp_val:
            d = parse_xmp_date(xmp_val)  # Validates the date
            return f'D:{d.year:04d}{d.month:02d}{d.day:02d}'
        return encode_pdf_date(parse_xmp_date(xmp_val))


class DocinfoMapping(NamedTuple):
    """Map DocumentInfo keys to their XMP equivalents, along with converter.

    ``name`` is stored as the raw PDF name string (e.g. ``"/Author"``) rather
    than as a ``pikepdf.Name`` instance. This keeps the module-level
    DOCINFO_MAPPING free of persistent ``pikepdf.Object`` references, which
    nanobind reports as shutdown leaks. Consumers can pass the string directly
    to a ``pikepdf.Dictionary`` (which accepts str keys) or wrap it in
    ``pikepdf.Name()`` if a Name instance is specifically required.
    """

    ns: str
    key: str
    name: str
    converter: type[Converter] | None


DOCINFO_MAPPING: list[DocinfoMapping] = [
    DocinfoMapping(XMP_NS_DC, 'creator', '/Author', AuthorConverter),
    DocinfoMapping(XMP_NS_DC, 'description', '/Subject', None),
    DocinfoMapping(XMP_NS_DC, 'title', '/Title', None),
    DocinfoMapping(XMP_NS_PDF, 'Keywords', '/Keywords', None),
    DocinfoMapping(XMP_NS_PDF, 'Producer', '/Producer', None),
    DocinfoMapping(XMP_NS_XMP, 'CreateDate', '/CreationDate', DateConverter),
    DocinfoMapping(XMP_NS_XMP, 'CreatorTool', '/Creator', None),
    DocinfoMapping(XMP_NS_XMP, 'ModifyDate', '/ModDate', DateConverter),
]
