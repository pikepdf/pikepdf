# SPDX-FileCopyrightText: 2026 James R. Barlow
# SPDX-License-Identifier: MPL-2.0

"""Shallow JSON encoding of PDF objects, following qpdf JSON v2 conventions.

Only direct objects are expanded; an indirect object is encoded as its
reference string ``"N G R"``. This keeps each role's schema check local to one
object, while the walker decides which references to follow.
"""

from __future__ import annotations

from decimal import Decimal
from typing import TYPE_CHECKING, Any

import pikepdf

if TYPE_CHECKING:
    from pikepdf.pdfa._writemodel import WriteModel

_BOM_UTF16 = b'\xfe\xff'


def _encode_name(obj: pikepdf.Object) -> str:
    try:
        return str(obj)
    except UnicodeDecodeError:
        # Names are byte strings; ones in legacy encodings (e.g. GBK font
        # names) are not valid UTF-8. The unparsed form is ASCII with #xx
        # escapes.
        return obj.unparse().decode('ascii', 'replace')


def _encode_string(obj: pikepdf.Object) -> str:
    raw = bytes(obj)
    if raw.startswith(_BOM_UTF16):
        try:
            return 'u:' + raw[2:].decode('utf-16-be')
        except UnicodeDecodeError:
            return 'b:' + raw.hex()
    try:
        return 'u:' + raw.decode('pdfdoc')
    except UnicodeDecodeError:
        return 'b:' + raw.hex()


def _ref(obj: pikepdf.Object) -> str:
    num, gen = obj.objgen
    return f'{num} {gen} R'


def _encode_dict_items(obj: pikepdf.Object) -> dict[str, Any]:
    # A dictionary entry whose value is null is equivalent to an absent entry.
    return {
        str(key): shallow_json(value)
        for key, value in obj.items()
        if not _is_null(value)
    }


def _is_null(value: Any) -> bool:
    if value is None:
        return True
    return (
        isinstance(value, pikepdf.Object)
        and value._type_code == pikepdf.ObjectType.null
    )


def _scalar_value(obj: pikepdf.Object) -> Any:
    if isinstance(obj, pikepdf.Name):
        return _encode_name(obj)
    if isinstance(obj, pikepdf.String):
        return _encode_string(obj)
    if isinstance(obj, pikepdf.Boolean):
        return bool(obj)
    if isinstance(obj, pikepdf.Integer):
        return int(obj)
    if isinstance(obj, pikepdf.Real):
        return float(obj)
    if obj._type_code == pikepdf.ObjectType.null:
        return None
    raise TypeError(f"cannot encode PDF object of type {obj._type_name}")


def shallow_json(obj: Any) -> Any:
    """Encode a PDF object as JSON-compatible data without following references.

    Args:
        obj: A pikepdf object, or a Python scalar as returned by pikepdf's
            implicit conversion of PDF integers, reals, booleans and null.

    Returns:
        ``"/Name"`` for names; ``"u:text"`` for strings that decode as
        UTF-16BE (with BOM) or PDFDocEncoding, else ``"b:<hex>"``; int,
        float, bool or None for scalars; ``"N G R"`` for indirect objects;
        lists and dicts for direct arrays and dictionaries; and
        ``{"stream": {"dict": {...}}}`` for a direct stream.
    """
    if obj is None or isinstance(obj, bool | int):
        return obj
    if isinstance(obj, Decimal | float):
        return float(obj)
    if not isinstance(obj, pikepdf.Object):
        raise TypeError(f"cannot encode {type(obj).__name__}")
    if obj.is_indirect:
        return _ref(obj)
    if isinstance(obj, pikepdf.Stream):
        return {'stream': {'dict': shallow_json_of_stream_dict(obj)}}
    if isinstance(obj, pikepdf.Dictionary):
        return _encode_dict_items(obj)
    if isinstance(obj, pikepdf.Array):
        return [shallow_json(item) for item in obj]
    return _scalar_value(obj)


def shallow_json_of_stream_dict(
    stream: pikepdf.Stream, model: WriteModel | None = None
) -> dict[str, Any]:
    """Encode a stream's dictionary (not its data), shallowly.

    If *model* predicts a written form, ``/Filter`` and ``/DecodeParms`` are
    the ones the model says will be written.
    """
    encoded = _encode_dict_items(stream.stream_dict)
    if model is None or model.is_identity:
        return encoded
    encoded.pop('/Filter', None)
    encoded.pop('/DecodeParms', None)
    filters, decode_parms = model.stream_filters(stream)
    if not _is_null(filters):
        encoded['/Filter'] = shallow_json(filters)
    if not _is_null(decode_parms):
        encoded['/DecodeParms'] = shallow_json(decode_parms)
    return encoded


def shallow_json_of(obj: Any, model: WriteModel | None = None) -> Any:
    """Encode an object expanding its own top level even if it is indirect.

    Streams are encoded as their stream dictionary, so a schema for a stream
    role describes the dictionary directly; *model*, if given, supplies the
    stream filters that will be written.
    """
    if isinstance(obj, pikepdf.Stream):
        return shallow_json_of_stream_dict(obj, model)
    if isinstance(obj, pikepdf.Dictionary):
        return _encode_dict_items(obj)
    if isinstance(obj, pikepdf.Array):
        return [shallow_json(item) for item in obj]
    if isinstance(obj, pikepdf.Object) and obj.is_indirect:
        return _scalar_value(obj)
    return shallow_json(obj)
