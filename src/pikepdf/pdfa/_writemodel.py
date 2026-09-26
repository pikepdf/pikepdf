# SPDX-FileCopyrightText: 2026 James R. Barlow
# SPDX-License-Identifier: MPL-2.0

"""What the validator sees of a document once it is written.

qpdf's writer changes some things between the in-memory object graph and the
bytes it writes: stream filters, the trailer, the version, encryption, the
cross-reference format and which objects are written at all. The validator
asks a `WriteModel` for these instead of reading them from the open `Pdf`,
so it can evaluate the written form of a document without writing it.

`WriteModel.identity` answers with the in-memory values, which is correct
for a document opened from a file that is being validated as written.
`WriteModel.predict` answers with what `pikepdf.Pdf.save` will write, given
settings from `resolve_save_kwargs`.
"""

from __future__ import annotations

from collections.abc import Iterator, Mapping, Sequence
from decimal import Decimal

import pikepdf
from pikepdf._core import ObjectStreamMode
from pikepdf.pdfa._shallow import JsonValue, shallow_json_of

# Filters qpdf decodes at stream_decode_level=generalized, by the names qpdf
# accepts for them. Flate and LZW take predictor parameters; the others
# must have none.
_FLATE_LZW = frozenset({'/FlateDecode', '/Fl', '/LZWDecode', '/LZW'})
_LZW = frozenset({'/LZWDecode', '/LZW'})
_GENERALIZED = _FLATE_LZW | {'/ASCII85Decode', '/A85', '/ASCIIHexDecode', '/AHx'}
# Decoded only at stream_decode_level=all (specialized or lossy), which qpdf
# uses for the document metadata stream.
_SPECIALIZED = frozenset(
    {'/RunLengthDecode', '/RL', '/DCTDecode', '/DCT', '/JBIG2Decode'}
)

# Trailer keys qpdf replaces or drops when writing (QPDFWriter trimmed_trailer).
_TRIMMED_TRAILER_KEYS = frozenset(
    {
        '/ID',
        '/Encrypt',
        '/Prev',
        '/Index',
        '/W',
        '/Length',
        '/Filter',
        '/DecodeParms',
        '/Type',
        '/XRefStm',
    }
)
_PLACEHOLDER_ID = ['b:' + '00' * 16, 'b:' + '00' * 16]

# (/Filter, /DecodeParms) of a stream; None if absent
_Filters = tuple[pikepdf.Object | None, pikepdf.Object | None]


def _version_tuple(version: str) -> tuple[int, int]:
    major, _, minor = version.partition('.')
    try:
        return int(major), int(minor or 0)
    except ValueError:
        return (0, 0)


def _version_arg(value: object) -> str:
    """The version string of a min_version/force_version argument."""
    if isinstance(value, tuple):
        return str(value[0])
    return str(value or '')


def _is_null(value: object) -> bool:
    return value is None or (
        isinstance(value, pikepdf.Object)
        and value._type_code == pikepdf.ObjectType.null
    )


def _flate_lzw_parms_ok(parms: pikepdf.Object | None, lzw: bool) -> bool:
    """Whether qpdf's SF_FlateLzwDecode accepts these /DecodeParms."""
    if not isinstance(parms, pikepdf.Dictionary):
        return True  # qpdf treats a non-dictionary as having no keys
    predictor = 1
    columns = 1
    for key, value in parms.items():
        if key in ('/Predictor', '/Columns', '/Colors', '/BitsPerComponent') or (
            lzw and key == '/EarlyChange'
        ):
            number = pikepdf.as_int(value)
            if number is None:
                return False
            if key == '/Predictor':
                if not (number in (1, 2) or 10 <= number <= 15):
                    return False
                predictor = number
            elif key == '/Columns':
                columns = number
            elif key == '/EarlyChange' and number not in (0, 1):
                return False
    return not (predictor > 1 and columns == 0)


def _crypt_parms_ok(parms: pikepdf.Object | None) -> bool:
    if isinstance(parms, pikepdf.Dictionary):
        for key, value in parms.items():
            if key == '/Name':
                continue
            if key == '/Type' and (
                _is_null(value) or value == pikepdf.Name.CryptFilterDecodeParms
            ):
                continue
            if not _is_null(value):
                return False
        return True
    return _is_null(parms)


def _filter_ok(name: str, parms: pikepdf.Object | None, level_all: bool) -> bool:
    if name in _FLATE_LZW:
        return _flate_lzw_parms_ok(parms, name in _LZW)
    if name == '/Crypt':
        return _crypt_parms_ok(parms)
    if name in _GENERALIZED or (level_all and name in _SPECIALIZED):
        # JBIG2Decode accepts parameters; the others need none.
        return name == '/JBIG2Decode' or _is_null(parms)
    return False


def _decodable(stream_dict: pikepdf.Dictionary, level_all: bool) -> bool:
    """Whether qpdf can decode the stream (QPDF_Stream.cc ``filterable``)."""
    filter_obj = stream_dict.get('/Filter')
    if _is_null(filter_obj):
        return True
    names: list[pikepdf.Object]
    if isinstance(filter_obj, pikepdf.Name):
        names = [filter_obj]
    elif isinstance(filter_obj, pikepdf.Array):
        names = list(filter_obj)
        if not all(isinstance(name, pikepdf.Name) for name in names):
            return False
    else:
        return False
    parms_obj = stream_dict.get('/DecodeParms')
    parms: list[pikepdf.Object | None]
    if isinstance(parms_obj, pikepdf.Array) and len(parms_obj) > 0:
        if names and len(parms_obj) != len(names):
            return False
        parms = list(parms_obj)
    else:
        if isinstance(parms_obj, pikepdf.Array):
            parms_obj = None
        parms = [parms_obj] * len(names)
    return all(
        _filter_ok(str(name), parm, level_all)
        for name, parm in zip(names, parms, strict=True)
    )


def _unchanged_filters(stream_dict: pikepdf.Dictionary) -> _Filters:
    """The filters qpdf writes for a stream it copies without decoding."""
    filter_obj = stream_dict.get('/Filter')
    parms = stream_dict.get('/DecodeParms')
    if isinstance(parms, pikepdf.Array) and len(parms) == 0:
        parms = None
    if isinstance(filter_obj, pikepdf.Name) and filter_obj == pikepdf.Name.Crypt:
        return None, None
    if isinstance(filter_obj, pikepdf.Array):
        names = list(filter_obj)
        if pikepdf.Name.Crypt in names:
            idx = names.index(pikepdf.Name.Crypt)
            filter_obj = pikepdf.Array(names[:idx] + names[idx + 1 :])
            if isinstance(parms, pikepdf.Array) and idx < len(parms):
                items = list(parms)
                parms = pikepdf.Array(items[:idx] + items[idx + 1 :])
    return filter_obj, parms


class WriteModel:
    """Predicts the written form of a document for the validator.

    Construct instances with `WriteModel.identity` or `WriteModel.predict`.
    """

    __slots__ = ('_objects', '_root_metadata', '_save_kwargs')

    def __init__(self, save_kwargs: Mapping[str, object] | None = None) -> None:
        # None means identity: the written form is the in-memory form.
        self._save_kwargs = None if save_kwargs is None else dict(save_kwargs)
        self._root_metadata: tuple[int, int] | None = None
        self._objects: list[pikepdf.Object] | None = None

    @classmethod
    def identity(cls) -> WriteModel:
        """Return a model in which the written form is the in-memory form."""
        return cls()

    @classmethod
    def predict(cls, pdf: pikepdf.Pdf, save_kwargs: Mapping[str, object]) -> WriteModel:
        """Return a model of what ``pdf.save(..., **save_kwargs)`` writes.

        *save_kwargs* must come from `resolve_save_kwargs`: the model relies
        on its pinned settings (``stream_decode_level=generalized``, no
        encryption, no content normalization, no QDF). The model describes
        the document as it is when the model is used; it does not modify it.

        Stream data that qpdf fails to decode while writing is written
        unchanged, which the model cannot foresee without decoding it; such
        a difference is caught when the written file is validated.
        """
        model = cls(save_kwargs)
        metadata = pdf.Root.get('/Metadata')
        if isinstance(metadata, pikepdf.Stream) and metadata.is_indirect:
            md = metadata.stream_dict
            if md.get('/Type') == pikepdf.Name.Metadata and (
                md.get('/Subtype') == pikepdf.Name.XML
            ):
                model._root_metadata = metadata.objgen
        return model

    @property
    def is_identity(self) -> bool:
        """True if this model reports the in-memory values unchanged."""
        return self._save_kwargs is None

    def __repr__(self) -> str:
        if self.is_identity:
            return 'WriteModel.identity()'
        return f'WriteModel({self._save_kwargs!r})'

    def _setting(self, key: str, default: object = None) -> object:
        assert self._save_kwargs is not None
        return self._save_kwargs.get(key, default)

    def stream_filters(self, stream: pikepdf.Stream) -> _Filters:
        """Return the stream's ``(/Filter, /DecodeParms)`` once written.

        Each is the value of the stream dictionary entry, or None if absent.
        """
        if self._save_kwargs is None:
            return stream.get('/Filter'), stream.get('/DecodeParms')
        return self._predict_filters(stream)

    def _predict_filters(self, stream: pikepdf.Stream) -> _Filters:
        # Mirrors QPDFWriter::will_filter_stream and QPDF_Stream's
        # pipeStreamData at stream_decode_level=generalized.
        stream_dict = stream.stream_dict
        compress = bool(self._setting('compress_streams', True))
        recompress = bool(self._setting('recompress_flate', False))
        length = pikepdf.as_int(stream_dict.get('/Length'))
        if length is not None:
            empty = length == 0
        else:
            # In-memory streams have no /Length when their data is empty.
            empty = len(stream.read_raw_bytes()) == 0
        filter_obj = stream_dict.get('/Filter')

        filter_ = True
        level_all = False
        encode = False
        if (
            compress
            and not recompress
            and isinstance(filter_obj, pikepdf.Name)
            and filter_obj in (pikepdf.Name.FlateDecode, pikepdf.Name('/Fl'))
        ):
            filter_ = False
        if stream.is_indirect and stream.objgen == self._root_metadata:
            filter_ = True
            level_all = True
        elif filter_ and compress:
            encode = True
        if length == 0:
            filter_ = True
            encode = False

        attempt = filter_ or empty
        if attempt and _decodable(stream_dict, level_all and filter_):
            if filter_ and encode:
                return pikepdf.Name.FlateDecode, None
            return None, None
        return _unchanged_filters(stream_dict)

    def trailer_json(self, trailer: pikepdf.Dictionary) -> dict[str, JsonValue]:
        """Return the shallow JSON encoding of the trailer once written."""
        shallow = shallow_json_of(trailer)
        if self._save_kwargs is None:
            return shallow
        written = {k: v for k, v in shallow.items() if k not in _TRIMMED_TRAILER_KEYS}
        written['/ID'] = list(_PLACEHOLDER_ID)
        return written

    def version(self, pdf: pikepdf.Pdf) -> str:
        """Return the PDF version in the header once written, e.g. ``'1.7'``."""
        if self._save_kwargs is None:
            return pdf.pdf_version
        forced = _version_arg(self._setting('force_version'))
        if forced:
            return forced
        candidates = [pdf.pdf_version, _version_arg(self._setting('min_version'))]
        if self._object_streams(pdf):
            candidates.append('1.5')
        return max((v for v in candidates if v), key=_version_tuple)

    def _object_streams(self, pdf: pikepdf.Pdf) -> bool:
        forced = _version_arg(self._setting('force_version'))
        if forced and _version_tuple(forced) < (1, 5):
            return False
        mode = self._setting('object_stream_mode', ObjectStreamMode.preserve)
        if mode == ObjectStreamMode.generate:
            return True
        if mode == ObjectStreamMode.preserve:
            return pdf.trailer.get('/Type') == pikepdf.Name.XRef
        return False

    def encrypted(self, pdf: pikepdf.Pdf) -> bool:
        """Return True if the written file is encrypted."""
        if self._save_kwargs is None:
            return pdf.is_encrypted
        return False

    def xref_stream(self, pdf: pikepdf.Pdf) -> bool:
        """Return True if the written file uses a cross-reference stream."""
        if self._save_kwargs is None:
            return pdf.trailer.get('/Type') == pikepdf.Name.XRef
        return self._object_streams(pdf)

    def objects(
        self, pdf: pikepdf.Pdf
    ) -> Sequence[pikepdf.Object | int | bool | Decimal]:
        """Return the indirect objects written to the file.

        An indirect integer, real or boolean is given as its Python value
        (by the identity model) or left out (by a predicting model), since
        the validator checks such a value where it is used.
        """
        if self._save_kwargs is None:
            return [pikepdf.unbox(obj) for obj in pdf.objects]
        if self._objects is None:
            self._objects = list(_reachable(pdf))
        return self._objects


def _reachable(pdf: pikepdf.Pdf) -> Iterator[pikepdf.Object]:
    """Yield each indirect object reachable from the written trailer, once.

    qpdf writes only these (it drops the old /Encrypt dictionary and any
    orphaned object). Iterative, so deep graphs do not exhaust the stack.
    """
    seen: set[tuple[int, int]] = set()
    stack: list[pikepdf.Object] = [
        value for key, value in pdf.trailer.items() if key not in _TRIMMED_TRAILER_KEYS
    ]
    stack.reverse()
    while stack:
        value = pikepdf.unbox(stack.pop())
        if not isinstance(value, pikepdf.Object):
            # A PDF integer, real or boolean, unboxed
            continue
        if value.is_indirect:
            key = value.objgen
            if key in seen:
                continue
            seen.add(key)
            yield value
        if isinstance(value, pikepdf.Stream):
            children = [v for _k, v in value.stream_dict.items()]
        elif isinstance(value, pikepdf.Dictionary):
            children = [v for _k, v in value.items()]
        elif isinstance(value, pikepdf.Array):
            children = list(value)
        else:
            continue
        children.reverse()
        stack.extend(children)
