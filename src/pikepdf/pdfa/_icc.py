# SPDX-FileCopyrightText: 2026 James R. Barlow
# SPDX-License-Identifier: MPL-2.0

"""ICC profile header checks for OutputIntents and ICCBased colour spaces."""

from __future__ import annotations

from typing import NamedTuple

from pikepdf.pdfa._context import ValidationContext
from pikepdf.pdfa._flavour import Flavour

HEADER_SIZE = 128

OUTPUT_DEVICE_CLASSES = frozenset({'prtr', 'mntr'})
INPUT_DEVICE_CLASSES = frozenset({'prtr', 'mntr', 'scnr', 'spac'})
OUTPUT_COLOUR_SPACES = frozenset({'RGB ', 'CMYK', 'GRAY'})
COMPONENTS = {'GRAY': 1, 'RGB ': 3, 'Lab ': 3, 'CMYK': 4}


class IccHeader(NamedTuple):
    """The fields of an ICC profile header that PDF/A cares about."""

    size: int
    version_major: int
    device_class: str
    colour_space: str

    @classmethod
    def parse(cls, data: bytes) -> IccHeader:
        """Parse the first 128 bytes of an ICC profile.

        Raises:
            ValueError: If the data is too short to hold a header.
        """
        if len(data) < HEADER_SIZE:
            raise ValueError(f"ICC profile is {len(data)} bytes, too short")
        return cls(
            size=int.from_bytes(data[0:4], 'big'),
            version_major=data[8],
            device_class=data[12:16].decode('latin-1'),
            colour_space=data[16:20].decode('latin-1'),
        )


def _max_major(flavour: Flavour) -> int:
    return 2 if flavour.part == 1 else 4


def check_output_profile(
    header: IccHeader, flavour: Flavour, ctx: ValidationContext, where: str
) -> bool:
    """Check the DestOutputProfile of a PDF/A OutputIntent.

    Returns:
        True if the profile is acceptable.
    """
    rule = flavour.rule('6.2.2-1', '6.2.3-1')
    ok = True
    if header.device_class not in OUTPUT_DEVICE_CLASSES:
        ctx.deny(rule, where, f"output profile device class {header.device_class!r}")
        ok = False
    if header.colour_space not in OUTPUT_COLOUR_SPACES:
        ctx.deny(rule, where, f"output profile colour space {header.colour_space!r}")
        ok = False
    if header.version_major > _max_major(flavour):
        ctx.deny(rule, where, f"output profile version {header.version_major}")
        ok = False
    return ok


def check_input_profile(
    header: IccHeader, n: int, flavour: Flavour, ctx: ValidationContext, where: str
) -> bool:
    """Check the profile of an ICCBased colour space with ``/N n``.

    Returns:
        True if the profile is acceptable.
    """
    rule = flavour.rule('6.2.3.2-1', '6.2.4.2-1')
    ok = True
    if header.device_class not in INPUT_DEVICE_CLASSES:
        ctx.deny(rule, where, f"ICC profile device class {header.device_class!r}")
        ok = False
    if header.colour_space not in COMPONENTS:
        ctx.deny(rule, where, f"ICC profile colour space {header.colour_space!r}")
        ok = False
    elif COMPONENTS[header.colour_space] != n:
        ctx.deny(
            flavour.rule('6.2.3.2-2', None, 'icc-components'),
            where,
            f"/N {n} does not match ICC colour space {header.colour_space!r}",
            'violation' if flavour.part == 1 else 'unsupported',
        )
        ok = False
    if header.version_major > _max_major(flavour):
        ctx.deny(rule, where, f"ICC profile version {header.version_major}")
        ok = False
    return ok
