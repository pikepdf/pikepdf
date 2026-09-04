# SPDX-FileCopyrightText: 2022 James R. Barlow
# SPDX-License-Identifier: MPL-2.0

"""Types of the well known XMP properties, and coercion of values to them.

The XMP specification assigns every property a value type and, where the
property holds more than one value, an RDF container type. A property that
carries the wrong container is not merely untidy: other tools discard it. For
example ``dc:subject`` is an unordered ``rdf:Bag``, and an ``rdf:Seq`` in its
place is silently dropped by Ghostscript and rejected by PDF/A validators.

This module records the type of the properties pikepdf knows about, so values
can be checked and converted on assignment. Properties that are not listed
here keep pikepdf's older behavior of inferring the container from the Python
type of the value assigned.
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import date, datetime
from enum import Enum, auto
from typing import Any, NamedTuple
from warnings import warn

from pikepdf._exceptions import XmpTypeWarning
from pikepdf.models.metadata._constants import (
    XMP_NS_DC,
    XMP_NS_PDF,
    XMP_NS_PDFA_ID,
    XMP_NS_PDFUA_ID,
    XMP_NS_PDFX_ID,
    XMP_NS_PHOTOSHOP,
    XMP_NS_XMP,
    XMP_NS_XMP_MM,
    XMP_NS_XMP_RIGHTS,
    AltList,
    clean,
)
from pikepdf.models.metadata._converters import encode_xmp_date


class XmpContainerType(Enum):
    """The RDF container an XMP property is stored in, if any."""

    SIMPLE = auto()
    ALT = auto()
    BAG = auto()
    SEQ = auto()


class XmpValueType(Enum):
    """The type of the individual values of an XMP property."""

    TEXT = auto()
    DATE = auto()
    INTEGER = auto()
    REAL = auto()
    BOOLEAN = auto()


class XmpProperty(NamedTuple):
    """The XMP type of a property."""

    container: XmpContainerType
    value: XmpValueType


_RDF_TYPES: dict[XmpContainerType, str] = {
    XmpContainerType.ALT: 'Alt',
    XmpContainerType.BAG: 'Bag',
    XmpContainerType.SEQ: 'Seq',
}


def _properties(
    uri: str, container: XmpContainerType, value: XmpValueType, *names: str
) -> dict[str, XmpProperty]:
    prop = XmpProperty(container, value)
    return {f'{{{uri}}}{name}': prop for name in names}


def _build_schema() -> dict[str, XmpProperty]:
    simple, alt, bag, seq = (
        XmpContainerType.SIMPLE,
        XmpContainerType.ALT,
        XmpContainerType.BAG,
        XmpContainerType.SEQ,
    )
    text, date_, integer, real, boolean = (
        XmpValueType.TEXT,
        XmpValueType.DATE,
        XmpValueType.INTEGER,
        XmpValueType.REAL,
        XmpValueType.BOOLEAN,
    )
    schema: dict[str, XmpProperty] = {}
    # Dublin Core, as profiled by the XMP specification
    schema |= _properties(
        XMP_NS_DC, simple, text, 'coverage', 'format', 'identifier', 'source'
    )
    schema |= _properties(XMP_NS_DC, alt, text, 'description', 'rights', 'title')
    schema |= _properties(
        XMP_NS_DC,
        bag,
        text,
        'contributor',
        'language',
        'publisher',
        'relation',
        'subject',
        'type',
    )
    schema |= _properties(XMP_NS_DC, seq, text, 'creator')
    schema |= _properties(XMP_NS_DC, seq, date_, 'date')

    # XMP basic
    schema |= _properties(
        XMP_NS_XMP, simple, text, 'BaseURL', 'CreatorTool', 'Label', 'Nickname'
    )
    schema |= _properties(
        XMP_NS_XMP, simple, date_, 'CreateDate', 'MetadataDate', 'ModifyDate'
    )
    schema |= _properties(XMP_NS_XMP, simple, real, 'Rating')
    schema |= _properties(XMP_NS_XMP, bag, text, 'Identifier')

    # PDF
    schema |= _properties(
        XMP_NS_PDF, simple, text, 'Keywords', 'PDFVersion', 'Producer', 'Trapped'
    )

    # PDF/A and PDF/UA identification
    schema |= _properties(XMP_NS_PDFA_ID, simple, integer, 'part', 'rev')
    schema |= _properties(XMP_NS_PDFA_ID, simple, text, 'conformance', 'amd', 'corr')
    schema |= _properties(XMP_NS_PDFUA_ID, simple, integer, 'part', 'rev')
    schema |= _properties(XMP_NS_PDFUA_ID, simple, text, 'amd', 'corr')
    schema |= _properties(XMP_NS_PDFX_ID, simple, text, 'GTS_PDFXVersion')

    # XMP rights management
    schema |= _properties(
        XMP_NS_XMP_RIGHTS, simple, text, 'Certificate', 'WebStatement'
    )
    schema |= _properties(XMP_NS_XMP_RIGHTS, simple, boolean, 'Marked')
    schema |= _properties(XMP_NS_XMP_RIGHTS, bag, text, 'Owner')
    schema |= _properties(XMP_NS_XMP_RIGHTS, alt, text, 'UsageTerms')

    # XMP media management - structured properties are deliberately omitted,
    # since pikepdf cannot generate them anyway
    schema |= _properties(
        XMP_NS_XMP_MM,
        simple,
        text,
        'DocumentID',
        'InstanceID',
        'OriginalDocumentID',
        'RenditionClass',
        'RenditionParams',
        'VersionID',
    )

    # Photoshop
    schema |= _properties(
        XMP_NS_PHOTOSHOP,
        simple,
        text,
        'AuthorsPosition',
        'CaptionWriter',
        'Category',
        'City',
        'Country',
        'Credit',
        'Headline',
        'Instructions',
        'Source',
        'State',
        'TransmissionReference',
    )
    schema |= _properties(XMP_NS_PHOTOSHOP, simple, date_, 'DateCreated')
    schema |= _properties(XMP_NS_PHOTOSHOP, simple, integer, 'Urgency')
    schema |= _properties(XMP_NS_PHOTOSHOP, bag, text, 'SupplementalCategories')

    return schema


XMP_SCHEMA: dict[str, XmpProperty] = _build_schema()


def lookup(qname: str) -> XmpProperty | None:
    """Return the XMP type of a property, or None if it is not known."""
    return XMP_SCHEMA.get(qname)


def lang_alts() -> frozenset[str]:
    """Return the qualified names of all language alternative properties."""
    return frozenset(
        qname
        for qname, prop in XMP_SCHEMA.items()
        if prop.container == XmpContainerType.ALT
    )


def _coerce_scalar(value_type: XmpValueType, val: Any) -> Any:
    """Convert a Python scalar to its XMP text representation."""
    if val is None or isinstance(val, str):
        return val
    if value_type == XmpValueType.DATE and isinstance(val, (datetime, date)):
        return encode_xmp_date(val)
    if value_type == XmpValueType.BOOLEAN and isinstance(val, bool):
        return 'True' if val else 'False'
    if (
        value_type == XmpValueType.INTEGER
        and isinstance(val, int)
        and not isinstance(val, bool)
    ):
        return str(val)
    if (
        value_type == XmpValueType.REAL
        and isinstance(val, (int, float))
        and not isinstance(val, bool)
    ):
        return str(val)
    return val


def normalize_value(
    key: str, qname: str, val: Any, *, strict: bool = False, stacklevel: int = 4
) -> tuple[Any, str | None]:
    """Check and convert a value being assigned to an XMP property.

    Arguments:
        key: the property name as the caller wrote it, for error messages
        qname: the property name in qualified ``{uri}local`` form
        val: the value being assigned
        strict: raise :class:`TypeError` instead of warning when the value
            does not match the type of the property
        stacklevel: how far up the stack the caller's assignment is, for
            warnings

    Returns:
        The value to store, and the name of the RDF container to store it in,
        or None to infer the container from the Python type of the value.
    """
    prop = lookup(qname)
    if prop is None:
        return val, None  # Unknown property: legacy behavior

    if prop.container == XmpContainerType.SIMPLE:
        val = _coerce_scalar(prop.value, val)
        if not isinstance(val, str) and isinstance(val, Iterable):
            if strict:
                raise TypeError(
                    f"{key} is a simple XMP property that holds one value, "
                    f"but a {type(val).__name__} was assigned"
                )
            # A container here would be discarded by other software, so join
            # the values into one. clean() warns that it did so.
            val = clean(val)
        return val, None

    rdf_type = _RDF_TYPES[prop.container]
    if prop.container == XmpContainerType.ALT:
        # A language alternative always gets one x-default entry, so multiple
        # values are joined rather than becoming several alternatives.
        return AltList([clean(_coerce_scalar(prop.value, val))]), rdf_type

    if isinstance(val, str) or not isinstance(val, Iterable):
        ordering = 'ordered' if prop.container == XmpContainerType.SEQ else 'unordered'
        msg = (
            f"{key} holds an {ordering} array of values (rdf:{rdf_type}); assign "
            f"a list or set of strings, not a {type(val).__name__}"
        )
        if strict:
            raise TypeError(msg)
        warn(XmpTypeWarning(msg), stacklevel=stacklevel)
        val = [val]
    items = [_coerce_scalar(prop.value, item) for item in val]
    if isinstance(val, (set, frozenset)):
        # A set has no order, so give it a reproducible one rather than
        # whatever order iteration happened to produce in this process.
        items.sort(key=str)
    return items, rdf_type
