# SPDX-FileCopyrightText: 2022 James R. Barlow
# SPDX-License-Identifier: MPL-2.0

"""Converters for XMP <-> DocumentInfo value transformation."""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any, NamedTuple

from pikepdf.models.metadata._constants import XMP_NS_DC, XMP_NS_PDF, XMP_NS_XMP
from pikepdf.objects import Name, String


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
        if len(val) in (4, 6) and val.isdigit():
            return val if len(val) == 4 else f'{val[:4]}-{val[4:]}'
        return decode_pdf_date(docinfo_val).isoformat()

    @staticmethod
    def docinfo_from_xmp(xmp_val):
        """Derive DocumentInfo from XMP."""
        if len(xmp_val) in (4, 7) and 'T' not in xmp_val:
            return f'D:{xmp_val.replace("-", "")}'
        if xmp_val.endswith('Z'):
            xmp_val = xmp_val[:-1] + '+00:00'
        return encode_pdf_date(datetime.fromisoformat(xmp_val))


class DocinfoMapping(NamedTuple):
    """Map DocumentInfo keys to their XMP equivalents, along with converter."""

    ns: str
    key: str
    name: Name
    converter: type[Converter] | None


DOCINFO_MAPPING: list[DocinfoMapping] = [
    DocinfoMapping(XMP_NS_DC, 'creator', Name.Author, AuthorConverter),
    DocinfoMapping(XMP_NS_DC, 'description', Name.Subject, None),
    DocinfoMapping(XMP_NS_DC, 'title', Name.Title, None),
    DocinfoMapping(XMP_NS_PDF, 'Keywords', Name.Keywords, None),
    DocinfoMapping(XMP_NS_PDF, 'Producer', Name.Producer, None),
    DocinfoMapping(XMP_NS_XMP, 'CreateDate', Name.CreationDate, DateConverter),
    DocinfoMapping(XMP_NS_XMP, 'CreatorTool', Name.Creator, None),
    DocinfoMapping(XMP_NS_XMP, 'ModifyDate', Name.ModDate, DateConverter),
]
