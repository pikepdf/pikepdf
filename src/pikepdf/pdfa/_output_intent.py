# SPDX-FileCopyrightText: 2026 James R. Barlow
# SPDX-License-Identifier: MPL-2.0

"""PDF/A output intents."""

from __future__ import annotations

from dataclasses import dataclass

from pikepdf import Array, Dictionary, Name, Pdf, Stream, String
from pikepdf.pdfa._catalogue import data_file
from pikepdf.pdfa._flavour import Flavour
from pikepdf.pdfa._icc import (
    COMPONENTS,
    HEADER_SIZE,
    OUTPUT_COLOUR_SPACES,
    OUTPUT_DEVICE_CLASSES,
    IccHeader,
)

SRGB_ICC_PROFILE_NAME = 'sRGB.icc'

_ICC_MAGIC = b'acsp'
_TAG_ENTRY_SIZE = 12
_MAX_DESCRIPTION = 256


def load_srgb() -> bytes:
    """Load the sRGB ICC profile from package data."""
    return data_file(SRGB_ICC_PROFILE_NAME).read_bytes()


@dataclass(frozen=True)
class OutputIntentSpec:
    """A validated PDF/A output intent, ready to install.

    Attributes:
        icc: The destination ICC profile.
        n: The number of colour components of the profile.
        colour_space: ``'RGB'``, ``'CMYK'`` or ``'GRAY'``.
        identifier: The /OutputConditionIdentifier.
        info: The /Info text describing the output condition.
    """

    icc: bytes
    n: int
    colour_space: str
    identifier: str
    info: str


def _description(icc: bytes) -> str | None:
    """Return the text of an ICC profile's description tag, if easily read.

    Reads a version 2 ``desc`` (textDescriptionType, ASCII part) or a version
    4 ``mluc`` (first record) tag. Returns None for anything else.
    """
    try:
        count = int.from_bytes(icc[HEADER_SIZE : HEADER_SIZE + 4], 'big')
        for i in range(min(count, 1024)):
            entry = HEADER_SIZE + 4 + i * _TAG_ENTRY_SIZE
            if icc[entry : entry + 4] != b'desc':
                continue
            offset = int.from_bytes(icc[entry + 4 : entry + 8], 'big')
            size = int.from_bytes(icc[entry + 8 : entry + 12], 'big')
            tag = icc[offset : offset + size]
            kind = tag[0:4]
            if kind == b'desc':
                length = int.from_bytes(tag[8:12], 'big')
                raw = tag[12 : 12 + min(length, _MAX_DESCRIPTION)]
                text = raw.split(b'\0', 1)[0].decode('ascii')
            elif kind == b'mluc':
                if int.from_bytes(tag[8:12], 'big') < 1:
                    return None
                length = int.from_bytes(tag[20:24], 'big')
                start = int.from_bytes(tag[24:28], 'big')
                raw = tag[start : start + min(length, 2 * _MAX_DESCRIPTION)]
                text = raw.decode('utf-16-be')
            else:
                return None
            text = text.strip()
            if text and text.isprintable():
                return text
            return None
    except (UnicodeDecodeError, ValueError):
        return None
    return None


def _parse_icc(icc: bytes, flavour: Flavour) -> tuple[int, str, str | None]:
    """Check an ICC profile is usable as a PDF/A destination output profile.

    Applies the checks the validator makes of an OutputIntent's
    /DestOutputProfile (`pikepdf.pdfa._icc.check_output_profile`).

    Returns:
        The number of components, the colour space (without padding) and
        the profile description, if any.

    Raises:
        ValueError: If the profile is not acceptable.
    """
    header = IccHeader.parse(icc)
    if icc[36:40] != _ICC_MAGIC:
        raise ValueError("not an ICC profile: the 'acsp' signature is missing")
    if not HEADER_SIZE <= header.size <= len(icc):
        raise ValueError(
            f"ICC profile header declares {header.size} bytes, but "
            f"{len(icc)} bytes were given"
        )
    if header.device_class not in OUTPUT_DEVICE_CLASSES:
        raise ValueError(
            f"ICC profile device class {header.device_class!r} cannot be a "
            "PDF/A output intent; it must be an output (printer) or display "
            "profile"
        )
    if header.colour_space not in OUTPUT_COLOUR_SPACES:
        raise ValueError(
            f"ICC profile colour space {header.colour_space!r} cannot be a "
            "PDF/A output intent; it must be RGB, CMYK or GRAY"
        )
    max_major = 2 if flavour.part == 1 else 4
    if header.version_major > max_major:
        raise ValueError(
            f"ICC profile version {header.version_major} is not permitted in "
            f"PDF/A-{flavour.part}; the version must be {max_major} or earlier"
        )
    return (
        COMPONENTS[header.colour_space],
        header.colour_space.rstrip(),
        _description(icc),
    )


def srgb_output_intent() -> OutputIntentSpec:
    """Return the output intent for the sRGB profile shipped with pikepdf."""
    return OutputIntentSpec(
        icc=load_srgb(), n=3, colour_space='RGB', identifier='sRGB', info='sRGB'
    )


def parse_output_intent(
    value: bytes | str | None,
    flavour: Flavour | str,
    identifier: str | None = None,
) -> OutputIntentSpec | None:
    """Validate an output intent argument.

    Args:
        value: ``'sRGB'`` (in any case) for the sRGB profile shipped with
            pikepdf, the bytes of an ICC profile, or None to keep the
            document's output intents.
        flavour: The PDF/A flavour the intent is for; PDF/A-1 permits ICC
            profiles up to version 2, later parts up to version 4.
        identifier: The /OutputConditionIdentifier to use instead of the
            default: ``'sRGB'`` for the sRGB profile, else the profile's
            description, or ``'Custom'`` if it has none.

    Returns:
        The output intent, or None if *value* is None.

    Raises:
        ValueError: If the value is not usable as a PDF/A output intent.
        TypeError: If the value is of the wrong type.
    """
    pdfa_flavour = Flavour(flavour)
    if value is None:
        return None
    if isinstance(value, str):
        if value.lower() != 'srgb':
            raise ValueError(
                f"output_intent {value!r} is not recognized; use 'sRGB', the "
                "bytes of an ICC profile, or None"
            )
        spec = srgb_output_intent()
    elif isinstance(value, bytes | bytearray | memoryview):
        icc = bytes(value)
        try:
            n, colour_space, description = _parse_icc(icc, pdfa_flavour)
        except ValueError as e:
            raise ValueError(f"output_intent: {e}") from e
        spec = OutputIntentSpec(
            icc=icc,
            n=n,
            colour_space=colour_space,
            identifier=description or 'Custom',
            info=description or 'Custom',
        )
    else:
        raise TypeError(
            f"output_intent must be 'sRGB', bytes or None, not {type(value).__name__}"
        )
    if identifier is not None:
        spec = OutputIntentSpec(
            icc=spec.icc,
            n=spec.n,
            colour_space=spec.colour_space,
            identifier=identifier,
            info=spec.info,
        )
    return spec


def has_output_intent(pdf: Pdf, spec: OutputIntentSpec) -> bool:
    """Return True if *spec* is already the document's only output intent.

    That is, /OutputIntents holds exactly the dictionary
    `replace_output_intents` would install for *spec*, with the same profile
    bytes.
    """
    intents = pdf.Root.get(Name.OutputIntents)
    if not isinstance(intents, Array) or len(intents) != 1:
        return False
    intent = intents[0]
    if not isinstance(intent, Dictionary) or set(intent.keys()) != {
        '/Type',
        '/S',
        '/OutputConditionIdentifier',
        '/Info',
        '/DestOutputProfile',
    }:
        return False
    profile = intent.get(Name.DestOutputProfile)
    identifier = intent.get(Name.OutputConditionIdentifier)
    info = intent.get(Name.Info)
    return (
        intent.get(Name.Type) == Name.OutputIntent
        and intent.get(Name.S) == Name.GTS_PDFA1
        and isinstance(identifier, String)
        and str(identifier) == spec.identifier
        and isinstance(info, String)
        and str(info) == spec.info
        and isinstance(profile, Stream)
        and profile.is_indirect
        and profile.get(Name.N) == spec.n
        and profile.read_bytes() == spec.icc
    )


def add_srgb_output_intent(pdf: Pdf) -> None:
    """Make an sRGB PDF/A output intent the document's only output intent.

    Equivalent to `replace_output_intents` with the sRGB profile: existing
    output intents (such as a PDF/X intent with a CMYK profile) are
    discarded, since PDF/A requires every output intent to share one
    destination profile.

    Args:
        pdf: An open pikepdf.Pdf object
    """
    replace_output_intents(pdf)


def replace_output_intents(pdf: Pdf, spec: OutputIntentSpec | None = None) -> None:
    """Replace the catalog's /OutputIntents with a single PDF/A intent.

    The new intent is a GTS_PDFA1 OutputIntent whose destination profile is
    that of *spec*, by default the sRGB ICC profile shipped with pikepdf.
    An output intent of another kind or with another profile cannot be kept,
    because PDF/A requires all output intents to use the same profile.

    Args:
        pdf: An open pikepdf.Pdf object
        spec: The output intent to install, from `parse_output_intent`.
    """
    if spec is None:
        spec = srgb_output_intent()
    icc_stream = Stream(pdf, spec.icc)
    icc_stream[Name.N] = spec.n
    output_intent = Dictionary(
        {
            '/Type': Name.OutputIntent,
            '/S': Name('/GTS_PDFA1'),
            '/OutputConditionIdentifier': String(spec.identifier),
            '/Info': String(spec.info),
            '/DestOutputProfile': icc_stream,
        }
    )
    pdf.Root[Name.OutputIntents] = Array([pdf.make_indirect(output_intent)])
