# SPDX-FileCopyrightText: 2026 James R. Barlow
# SPDX-License-Identifier: MPL-2.0

"""Colour space resolution and the device colour rules.

`resolve_colourspace` accepts the device families, ICCBased, Indexed,
CalGray, CalRGB and Lab. Separation, DeviceN and Pattern colour spaces are
reported as unsupported. Device colour spaces are checked against the PDF/A
OutputIntent, unless the resources of the content stream set a device
independent ``/DefaultGray``, ``/DefaultRGB`` or ``/DefaultCMYK``, which then
replaces the device colour space (as veraPDF does).
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any, NamedTuple

import pikepdf
from pikepdf.pdfa._context import ValidationContext
from pikepdf.pdfa._icc import IccHeader, check_input_profile
from pikepdf.pdfa._schemas import SchemaSet
from pikepdf.pdfa._shallow import shallow_json_of

DEVICE_COMPONENTS = {'/DeviceGray': 1, '/DeviceRGB': 3, '/DeviceCMYK': 4}
DEFAULT_SPACES = {
    '/DeviceGray': '/DefaultGray',
    '/DeviceRGB': '/DefaultRGB',
    '/DeviceCMYK': '/DefaultCMYK',
}
DEVICE_INDEPENDENT = frozenset({'/ICCBased', '/CalGray', '/CalRGB', '/Lab'})
UNSUPPORTED_FAMILIES = frozenset({'/Separation', '/DeviceN', '/Pattern'})
INLINE_ABBREVIATIONS = {
    '/G': '/DeviceGray',
    '/RGB': '/DeviceRGB',
    '/CMYK': '/DeviceCMYK',
    '/I': '/Indexed',
}
MAX_NESTING = 4
MAX_HIVAL = 255

# Keys permitted in the dictionaries of the CIE-based colour spaces
# (ISO 32000-1 Tables 63, 64 and 65)
CIE_KEYS = {
    '/CalGray': frozenset({'/WhitePoint', '/BlackPoint', '/Gamma'}),
    '/CalRGB': frozenset({'/WhitePoint', '/BlackPoint', '/Gamma', '/Matrix'}),
    '/Lab': frozenset({'/WhitePoint', '/BlackPoint', '/Range'}),
}
CIE_COMPONENTS = {'/CalGray': 1, '/CalRGB': 3, '/Lab': 3}
CIE_ARRAY_LENGTHS = {
    '/WhitePoint': 3,
    '/BlackPoint': 3,
    '/Matrix': 9,
    '/Range': 4,
}


class ColourSpaceInfo(NamedTuple):
    """What the content checks need to know about a colour space.

    Attributes:
        family: The colour space family, e.g. ``/DeviceRGB`` or ``/ICCBased``.
        components: Number of colour components (operands of ``sc``).
    """

    family: str
    components: int


def check_device_use(ctx: ValidationContext, name: str, where: str) -> bool:
    """Check that a device colour space may be used with the OutputIntent.

    DeviceGray needs any PDF/A OutputIntent, DeviceRGB an RGB one and
    DeviceCMYK a CMYK one. Any other name is reported as unsupported.

    Returns:
        True if the use is allowed.
    """
    intent = ctx.output_intent_cs
    if name == '/DeviceGray':
        if intent is None:
            ctx.deny(
                ctx.rule('6.2.3.3-3', '6.2.4.3-4'),
                where,
                "DeviceGray used without a PDF/A OutputIntent",
            )
            return False
    elif name == '/DeviceRGB':
        if intent != 'RGB ':
            ctx.deny(
                ctx.rule('6.2.3.3-1', '6.2.4.3-2'),
                where,
                f"DeviceRGB used with OutputIntent colour space {intent!r}",
            )
            return False
    elif name == '/DeviceCMYK':
        if intent != 'CMYK':
            ctx.deny(
                ctx.rule('6.2.3.3-2', '6.2.4.3-3'),
                where,
                f"DeviceCMYK used with OutputIntent colour space {intent!r}",
            )
            return False
    else:
        ctx.deny('pikepdf:colour-space', where, f"colour space {name}", 'unsupported')
        return False
    return True


def _name(obj: Any) -> str | None:
    if not isinstance(obj, pikepdf.Name):
        return None
    try:
        return str(obj)
    except UnicodeDecodeError:
        return None


def _is_number(obj: Any) -> bool:
    return isinstance(obj, int | Decimal | float) and not isinstance(obj, bool)


class _Resolver:
    """Resolve one colour space, reporting problems to the context."""

    def __init__(
        self,
        ctx: ValidationContext,
        colour_spaces: Any,
        where: str,
        *,
        check_device: bool,
        inline: bool,
    ):
        self.ctx = ctx
        self.colour_spaces = (
            colour_spaces if isinstance(colour_spaces, pikepdf.Dictionary) else None
        )
        self.where = where
        self.check_device = check_device
        self.inline = inline

    def deny(self, message: str, rule: str = 'pikepdf:schema-ColorSpace') -> None:
        self.ctx.deny(rule, self.where, message)

    def unsupported(self, message: str) -> None:
        self.ctx.deny('pikepdf:colour-space', self.where, message, 'unsupported')

    def resolve(
        self, value: Any, depth: int, allow_names: bool
    ) -> ColourSpaceInfo | None:
        if depth > MAX_NESTING:
            self.unsupported(f"colour spaces nested deeper than {MAX_NESTING}")
            return None
        if isinstance(value, pikepdf.Name):
            return self.resolve_name(value, depth, allow_names)
        if isinstance(value, pikepdf.Array):
            return self.resolve_array(value, depth)
        self.deny(f"colour space {value!r} is neither a name nor an array")
        return None

    def resolve_name(
        self, value: pikepdf.Name, depth: int, allow_names: bool
    ) -> ColourSpaceInfo | None:
        name = _name(value)
        if name is None:
            self.deny("colour space name is not valid UTF-8")
            return None
        if self.inline and INLINE_ABBREVIATIONS.get(name) in DEVICE_COMPONENTS:
            name = INLINE_ABBREVIATIONS[name]
        if name in DEVICE_COMPONENTS:
            return self.device(name, depth)
        if name == '/Pattern':
            self.unsupported("pattern colour is not supported")
            return None
        if name in DEVICE_INDEPENDENT or name in UNSUPPORTED_FAMILIES:
            self.deny(f"colour space family {name} requires parameters")
            return None
        if not allow_names:
            self.deny(f"{name} is not a colour space family")
            return None
        if self.colour_spaces is None or name not in self.colour_spaces:
            self.ctx.deny(
                self.ctx.rule(None, '6.2.2-2', 'resource-missing'),
                self.where,
                f"colour space {name} is not in the content stream's resources",
            )
            return None
        # A resource value is a colour space family or array, never another
        # resource name.
        return self.resolve(self.colour_spaces.get(name), depth + 1, False)

    def device(self, name: str, depth: int) -> ColourSpaceInfo | None:
        components = DEVICE_COMPONENTS[name]
        if not self.check_device:
            return ColourSpaceInfo(name, components)
        default_key = DEFAULT_SPACES[name]
        if self.colour_spaces is not None and default_key in self.colour_spaces:
            default = _Resolver(
                self.ctx,
                None,
                f'{self.where} {default_key}',
                check_device=False,
                inline=False,
            ).resolve(self.colour_spaces.get(default_key), depth + 1, False)
            if default is None:
                return None
            if default.family not in DEVICE_INDEPENDENT:
                self.unsupported(
                    f"{default_key} is {default.family}, not device independent"
                )
                return None
            if default.components != components:
                self.deny(
                    f"{default_key} has {default.components} components, "
                    f"not {components}"
                )
                return None
            return ColourSpaceInfo(name, components)
        if not check_device_use(self.ctx, name, self.where):
            return None
        return ColourSpaceInfo(name, components)

    def resolve_array(self, value: pikepdf.Array, depth: int) -> ColourSpaceInfo | None:
        if len(value) == 0:
            self.deny("empty colour space array")
            return None
        family = _name(value[0])
        if family is None:
            self.deny("colour space array does not start with a family name")
            return None
        if self.inline:
            family = INLINE_ABBREVIATIONS.get(family, family)
        if family == '/ICCBased':
            return self.icc_based(value, depth)
        if family == '/Indexed':
            return self.indexed(value, depth)
        if family in CIE_KEYS:
            return self.cie(family, value)
        if family in UNSUPPORTED_FAMILIES:
            self.unsupported(f"{family} colour spaces are not supported")
            return None
        if family in DEVICE_COMPONENTS and len(value) == 1:
            self.unsupported(f"colour space array [{family}]")
            return None
        self.deny(f"unknown colour space family {family}")
        return None

    def icc_based(self, value: pikepdf.Array, depth: int) -> ColourSpaceInfo | None:
        ctx = self.ctx
        if len(value) != 2 or not isinstance(value[1], pikepdf.Stream):
            self.deny("ICCBased colour space must be [/ICCBased stream]")
            return None
        stream = value[1]
        key = stream.objgen if stream.is_indirect else None
        if key is not None and key in ctx.icc_profiles:
            components = ctx.icc_profiles[key]
        else:
            components = self.check_icc_stream(stream, depth)
            if key is not None:
                ctx.icc_profiles[key] = components
        if components is None:
            return None
        return ColourSpaceInfo('/ICCBased', components)

    def check_icc_stream(self, stream: pikepdf.Stream, depth: int) -> int | None:
        ctx = self.ctx
        where = f'{self.where} ICCBased {ctx.describe(stream)}'
        schemas = SchemaSet.for_flavour(ctx.flavour)
        if not schemas.check('ICCBasedStream', shallow_json_of(stream), ctx, where):
            return None
        n = int(stream.N)
        try:
            data = stream.read_bytes()
        except pikepdf.PdfError as e:
            ctx.deny(
                'pikepdf:icc', where, f"cannot read ICC profile: {e}", 'unsupported'
            )
            return None
        try:
            header = IccHeader.parse(data)
        except ValueError as e:
            ctx.deny(ctx.rule('6.2.3.2-1', '6.2.4.2-1'), where, str(e))
            return None
        if not check_input_profile(header, n, ctx.flavour, ctx, where):
            return None
        alternate = stream.get('/Alternate')
        if alternate is not None:
            info = _Resolver(
                ctx, None, f'{where} /Alternate', check_device=False, inline=False
            ).resolve(alternate, depth + 1, False)
            if info is None:
                return None
            if info.family in ('/Indexed', '/Pattern'):
                ctx.deny(
                    'pikepdf:schema-ICCBasedStream',
                    where,
                    f"/Alternate is {info.family}",
                )
                return None
            if info.components != n:
                ctx.deny(
                    'pikepdf:schema-ICCBasedStream',
                    where,
                    f"/Alternate has {info.components} components, /N is {n}",
                )
                return None
        return n

    def indexed(self, value: pikepdf.Array, depth: int) -> ColourSpaceInfo | None:
        if len(value) != 4:
            self.deny("Indexed colour space must be [/Indexed base hival lookup]")
            return None
        _family, base, hival, lookup = list(value)
        base_info = self.resolve(base, depth + 1, False)
        if base_info is None:
            return None
        if base_info.family in ('/Indexed', '/Pattern'):
            self.deny(f"the base of an Indexed colour space is {base_info.family}")
            return None
        if (
            not isinstance(hival, int)
            or isinstance(hival, bool)
            or not 0 <= hival <= MAX_HIVAL
        ):
            self.deny(f"Indexed hival {hival!r} is not an integer 0-{MAX_HIVAL}")
            return None
        if isinstance(lookup, pikepdf.String):
            size = len(bytes(lookup))
        elif isinstance(lookup, pikepdf.Stream):
            try:
                size = len(lookup.read_bytes())
            except pikepdf.PdfError as e:
                self.unsupported(f"cannot read the Indexed lookup table: {e}")
                return None
        else:
            self.deny("the Indexed lookup table is not a string or stream")
            return None
        needed = (hival + 1) * base_info.components
        if size < needed:
            self.deny(f"Indexed lookup table has {size} bytes; needs {needed}")
            return None
        return ColourSpaceInfo('/Indexed', 1)

    def cie(self, family: str, value: pikepdf.Array) -> ColourSpaceInfo | None:
        if len(value) != 2 or not isinstance(value[1], pikepdf.Dictionary):
            self.deny(f"{family} colour space must be [{family} dictionary]")
            return None
        params = value[1]
        allowed = CIE_KEYS[family]
        for key in params.keys():
            if key not in allowed:
                self.deny(f"{family} dictionary key {key} is not permitted")
                return None
        if '/WhitePoint' not in params:
            self.deny(f"{family} dictionary has no /WhitePoint")
            return None
        for key, length in CIE_ARRAY_LENGTHS.items():
            if key not in params:
                continue
            item = params.get(key)
            if (
                not isinstance(item, pikepdf.Array)
                or len(item) != length
                or not all(_is_number(v) for v in item)
            ):
                self.deny(f"{family} {key} is not an array of {length} numbers")
                return None
        if '/Gamma' in params:
            gamma = params.get('/Gamma')
            ok = (
                _is_number(gamma)
                if family == '/CalGray'
                else isinstance(gamma, pikepdf.Array)
                and len(gamma) == 3
                and all(_is_number(v) for v in gamma)
            )
            if not ok:
                self.deny(f"{family} /Gamma is malformed")
                return None
        return ColourSpaceInfo(family, CIE_COMPONENTS[family])


def resolve_colourspace(
    value: Any,
    resources: Any,
    ctx: ValidationContext,
    where: str,
    *,
    allow_names: bool = True,
    check_device: bool = True,
    inline: bool = False,
) -> ColourSpaceInfo | None:
    """Resolve a colour space operand or entry and check its use.

    Args:
        value: A colour space name (device family or resource name) or array.
        resources: The /ColorSpace resource dictionary of the content stream,
            or None if the stream has none. It provides named colour spaces
            and the ``/Default*`` colour spaces.
        ctx: Validation context.
        where: Location used in findings.
        allow_names: Whether *value* may name a colour space resource (true
            for ``cs``/``CS`` operands and inline images, false for image
            dictionaries, transparency groups and nested colour spaces).
        check_device: Whether device colour spaces are being used, so that
            they must agree with the OutputIntent. False when checking
            resource dictionaries, where they are only declared.
        inline: Whether inline image abbreviations are accepted.

    Returns:
        The colour space, or None if it was denied.
    """
    return _Resolver(
        ctx, resources, where, check_device=check_device, inline=inline
    ).resolve(value, 0, allow_names)


def check_image_colour(
    image: pikepdf.Stream, resources: Any, ctx: ValidationContext, where: str
) -> None:
    """Check the colour space and colour-key mask of an image XObject.

    Args:
        image: The image XObject.
        resources: The /ColorSpace resource dictionary of the content stream
            that paints the image (for the ``/Default*`` colour spaces), or
            None.
        ctx: Validation context.
        where: Location used in findings.
    """
    if image.get('/ImageMask') is True:
        return
    colour_space = image.get('/ColorSpace')
    if colour_space is None:
        ctx.deny('pikepdf:schema-ImageXObject', where, "image has no /ColorSpace")
        return
    info = resolve_colourspace(colour_space, resources, ctx, where, allow_names=False)
    if info is None:
        return
    mask = image.get('/Mask')
    if isinstance(mask, pikepdf.Array) and (
        len(mask) != 2 * info.components
        or not all(isinstance(v, int) and not isinstance(v, bool) for v in mask)
    ):
        ctx.deny(
            'pikepdf:schema-ImageXObject',
            where,
            f"colour key /Mask must have {2 * info.components} integers",
        )
