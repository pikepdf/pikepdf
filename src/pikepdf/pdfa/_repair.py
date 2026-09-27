# SPDX-FileCopyrightText: 2026 James R. Barlow
# SPDX-License-Identifier: MPL-2.0

"""Repairs that make a document acceptable to PDF/A without changing content."""

from __future__ import annotations

import logging
from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass, field
from functools import cache
from typing import cast

import pikepdf
from pikepdf import Array, Dictionary, Name, Object, Pdf, Stream
from pikepdf.pdfa._embedded import associated_file_objgens
from pikepdf.pdfa._encodings import (
    MAX_CODE,
    STANDARD,
    WIN_ANSI,
    DifferencesError,
    encoding_table,
    parse_differences,
)
from pikepdf.pdfa._fontuse import font_codes

log = logging.getLogger(__name__)


def _get_dict(obj: Object, key: str | Name) -> Dictionary:
    """Look up a key expected to hold a dictionary, else return an empty one.

    A malformed file may store an array, a name, a stream or nothing at all
    where a dictionary belongs; scanning code treats those as empty.
    """
    value = obj.get(key)
    if isinstance(value, Object) and value.as_dict(None) is not None:
        return cast(Dictionary, value)
    return Dictionary()


def strip_image_interpolation(pdf: Pdf) -> int:
    """Remove /Interpolate from every image XObject.

    PDF/A forbids image interpolation. The entry is only a rendering hint, so
    removing it does not change the content. Inline images that request
    interpolation (``/I true``) are not repaired, because that would mean
    rewriting content streams; the validator denies them.

    Args:
        pdf: An open pikepdf.Pdf object

    Returns:
        The number of images changed.
    """
    count = 0
    for obj in pdf.objects:
        if (
            isinstance(obj, Stream)
            and obj.get(Name.Subtype) == Name.Image
            and Name.Interpolate in obj
        ):
            del obj[Name.Interpolate]
            count += 1
    return count


# Annotation flags (ISO 32000-1 Table 165)
_ANNOT_INVISIBLE = 1
_ANNOT_HIDDEN = 2
_ANNOT_PRINT = 4
_ANNOT_NOVIEW = 32
_ANNOT_TOGGLE_NOVIEW = 256
_ANNOT_NOT_VIEWABLE = (
    _ANNOT_INVISIBLE | _ANNOT_HIDDEN | _ANNOT_NOVIEW | _ANNOT_TOGGLE_NOVIEW
)
_MAX_PAGES_LISTED = 5


@dataclass
class AnnotationRepairResult:
    """What :func:`pikepdf.pdfa.repair_annotation_flags` changed.

    An empty result (no removals and no Print flags set) means the annotation
    flags of every page were already acceptable to PDF/A.
    """

    removed: Counter[str] = field(default_factory=Counter)
    """The number of annotations removed, keyed by subtype without the leading
    slash (for example ``'Link'`` or ``'Popup'``); ``'unknown'`` counts
    annotations that have no valid ``/Subtype``."""

    removed_pages: set[int] = field(default_factory=set)
    """The page numbers (1-based) from which annotations were removed."""

    print_flags_set: int = 0
    """The number of annotations that were kept and given the Print flag,
    because they had no ``/F`` entry or had one without the Print bit."""


def _annotation_flags(annot: Dictionary) -> int:
    return annot.get_int(Name.F, 0)


def _subtype_label(annot: Dictionary) -> str:
    subtype = annot.get(Name.Subtype)
    if not isinstance(subtype, Name):
        return 'unknown'
    try:
        return str(subtype)[1:]
    except UnicodeDecodeError:
        return subtype.unparse().decode('ascii', 'replace')[1:]


def _is_doomed(annot: Dictionary, doomed: set[tuple[int, int]]) -> bool:
    return bool(_annotation_flags(annot) & _ANNOT_NOT_VIEWABLE) or (
        annot.is_indirect and annot.objgen in doomed
    )


def describe_removed_annotations(
    removed: Counter[str], removed_pages: Iterable[int]
) -> str:
    """Describe removed annotations in a sentence.

    Args:
        removed: The number of annotations removed, by subtype.
        removed_pages: The page numbers (1-based) they were removed from;
            listed only if there are few of them.
    """
    pages_set = set(removed_pages)
    total = sum(removed.values())
    by_subtype = ', '.join(
        f'{count} {subtype}'
        for subtype, count in sorted(
            removed.items(), key=lambda item: (-item[1], item[0])
        )
    )
    pages = ''
    if pages_set and len(pages_set) <= _MAX_PAGES_LISTED:
        numbers = ', '.join(str(n) for n in sorted(pages_set))
        pages = f" on page{'s' if len(pages_set) > 1 else ''} {numbers}"
    return (
        f"Removed {total} annotation{'s' if total > 1 else ''} ({by_subtype})"
        f"{pages} that {'are' if total > 1 else 'is'} hidden or not viewable, "
        "which PDF/A does not permit"
    )


def repair_annotation_flags(pdf: Pdf) -> AnnotationRepairResult:
    """Make the annotation flags of every page acceptable to PDF/A.

    PDF/A requires every annotation to set the Print flag and to clear the
    Hidden, Invisible and NoView flags; PDF/A-2 and PDF/A-3 also require
    ToggleNoView to be clear. An annotation with any of those four flags set
    is removed, as Ghostscript does, rather than made visible. This function
    does not take a PDF/A part, so it removes annotations with ToggleNoView
    for every part, including PDF/A-1, whose rule predates that flag and does
    not mention it; the flags that remain are acceptable to every part.
    Along with a removed annotation goes its ``/Popup`` annotation, and a
    ``/Popup`` entry that refers to a removed annotation is deleted. The
    remaining annotations are given the Print flag if they lack it, leaving
    their other flags alone. Only annotations listed in a page's ``/Annots``
    are considered. The repair is idempotent.

    :func:`pikepdf.pdfa.prepare` calls this function, but it may also be used
    on its own, for example to preserve hyperlinks before handing a file to
    another PDF/A converter: Ghostscript's PDF/A mode silently deletes any
    annotation without the Print flag, which includes a ``/Link`` annotation
    written with no ``/F`` entry. It needs nothing beyond importing
    :mod:`pikepdf.pdfa`, and it neither validates the document nor changes
    anything other than page annotations.

    Logs up to two debug messages to a ``pikepdf.pdfa`` logger: one if any
    annotation was removed, and one if any annotation was given the Print
    flag.

    Args:
        pdf: An open pikepdf.Pdf object, modified in place.

    Returns:
        What was changed.
    """
    result = AnnotationRepairResult()
    # Indirect annotations to remove, and the popups that belong to them
    doomed: set[tuple[int, int]] = set()
    for page in pdf.pages:
        annots = page.obj.get(Name.Annots)
        if not isinstance(annots, Array):
            continue
        for annot in annots:
            if (
                isinstance(annot, Dictionary)
                and _annotation_flags(annot) & _ANNOT_NOT_VIEWABLE
            ):
                if annot.is_indirect:
                    doomed.add(annot.objgen)
                popup = annot.get(Name.Popup)
                if isinstance(popup, Dictionary) and popup.is_indirect:
                    doomed.add(popup.objgen)

    for pageno, page in enumerate(pdf.pages, start=1):
        annots = page.obj.get(Name.Annots)
        if not isinstance(annots, Array):
            continue
        kept = []
        for annot in annots:
            if not isinstance(annot, Dictionary):
                kept.append(annot)
                continue
            if _is_doomed(annot, doomed):
                result.removed[_subtype_label(annot)] += 1
                result.removed_pages.add(pageno)
                continue
            popup = annot.get(Name.Popup)
            if isinstance(popup, Dictionary) and _is_doomed(popup, doomed):
                del annot[Name.Popup]
            flags = _annotation_flags(annot)
            if Name.F not in annot or not flags & _ANNOT_PRINT:
                annot[Name.F] = flags | _ANNOT_PRINT
                result.print_flags_set += 1
            kept.append(annot)
        if len(kept) != len(annots):
            page.obj[Name.Annots] = Array(kept)

    if result.removed:
        log.debug(
            "%s", describe_removed_annotations(result.removed, result.removed_pages)
        )
    if result.print_flags_set:
        log.debug(
            "Setting the Print flag on %d annotation(s), as PDF/A requires",
            result.print_flags_set,
        )
    return result


def _cidset_bytes(cids: set[int]) -> bytes:
    """Encode CIDs as a /CIDSet bitmap (the high bit of byte 0 is CID 0)."""
    data = bytearray(max(cids) // 8 + 1 if cids else 1)
    for cid in cids:
        data[cid // 8] |= 0x80 >> (cid % 8)
    return bytes(data)


def _cidfont_program_cids(cidfont: Dictionary) -> set[int] | None:
    """Return the CIDs for which a CIDFont's embedded program has a glyph.

    Returns None if the font program is of a kind not handled here or cannot
    be read, in which case no /CIDSet should be added.
    """
    from pikepdf.pdfa._fontprogram import (
        CFFProgram,
        FontProgramError,
        TrueTypeProgram,
    )

    descriptor = _get_dict(cidfont, Name.FontDescriptor)
    subtype = cidfont.get(Name.Subtype)
    font_file2 = descriptor.get(Name.FontFile2)
    font_file3 = descriptor.get(Name.FontFile3)
    try:
        if subtype == Name.CIDFontType2 and isinstance(font_file2, Stream):
            num_glyphs = TrueTypeProgram(font_file2.read_bytes()).num_glyphs
            cid_to_gid = cidfont.get(Name.CIDToGIDMap, Name.Identity)
            if cid_to_gid == Name.Identity:
                return set(range(num_glyphs))
            if not isinstance(cid_to_gid, Stream):
                return None
            data = cid_to_gid.read_bytes()
            return {0} | {
                i // 2
                for i in range(0, len(data) - 1, 2)
                if 0 < int.from_bytes(data[i : i + 2], 'big') < num_glyphs
            }
        if (
            subtype == Name.CIDFontType0
            and isinstance(font_file3, Stream)
            and font_file3.get(Name.Subtype) == Name.CIDFontType0C
        ):
            return CFFProgram(font_file3.read_bytes()).cids()
    except (FontProgramError, pikepdf.PdfError) as e:
        log.debug("Cannot determine the CIDs of a CIDFont program: %s", e)
    return None


def _has_subset_prefix(basefont: Object | None) -> bool:
    """Return True if a font name starts with a subset tag such as ``ABCDEF+``."""
    if not isinstance(basefont, Name):
        return False
    raw = basefont.unparse()[1:]
    tag, plus, _rest = raw.partition(b'+')
    return bool(plus) and len(tag) == 6 and tag.isalpha() and tag.isupper()


def add_cidsets_for_subset_cidfonts(pdf: Pdf) -> int:
    """Add a /CIDSet to each subset CIDFont that lacks one.

    PDF/A-1 requires the font descriptor of a subset CIDFont to identify the
    CIDs present in the embedded program. For a CIDFontType2 (TrueType) font
    these are the CIDs whose CIDToGIDMap entry names a glyph of the program
    (with an /Identity map, every CID below the glyph count); for a
    CIDFontType0 font with a bare CFF program they are the CIDs in the CFF
    charset. Existing /CIDSet streams are left alone. Later parts of PDF/A
    do not require /CIDSet.

    Args:
        pdf: An open pikepdf.Pdf object

    Returns:
        The number of CIDSets added.
    """
    count = 0
    for obj in pdf.objects:
        if not isinstance(obj, Dictionary) or obj.get(Name.Subtype) not in (
            Name.CIDFontType0,
            Name.CIDFontType2,
        ):
            continue
        descriptor = obj.get(Name.FontDescriptor)
        if not isinstance(descriptor, Dictionary) or Name.CIDSet in descriptor:
            continue
        if not _has_subset_prefix(obj.get(Name.BaseFont)):
            continue
        cids = _cidfont_program_cids(obj)
        if cids is None:
            continue
        descriptor[Name.CIDSet] = pdf.make_stream(_cidset_bytes(cids))
        count += 1
    return count


# Font descriptor flags (ISO 32000-1 Table 123)
_FONT_SYMBOLIC = 4
_FONT_NONSYMBOLIC = 32


def _needs_base_encoding(obj: Object) -> bool:
    """True for a non-symbolic TrueType font with /Differences but no base."""
    if not isinstance(obj, Dictionary) or obj.get(Name.Subtype) != Name.TrueType:
        return False
    descriptor = obj.get(Name.FontDescriptor)
    if not isinstance(descriptor, Dictionary):
        return False
    flags = descriptor.get_int(Name.Flags, 0)
    if not flags & _FONT_NONSYMBOLIC or flags & _FONT_SYMBOLIC:
        return False
    encoding = obj.get(Name.Encoding)
    return (
        isinstance(encoding, Dictionary)
        and not isinstance(encoding, Stream)
        and Name.Differences in encoding
        and Name.BaseEncoding not in encoding
    )


@cache
def _standard_codes_kept_by_win_ansi() -> frozenset[int]:
    """Codes with the same glyph name in StandardEncoding and WinAnsiEncoding.

    Codes that neither encoding defines are included: they select .notdef
    either way.
    """
    standard = encoding_table(STANDARD)
    win_ansi = encoding_table(WIN_ANSI)
    return frozenset(
        code for code in range(MAX_CODE + 1) if standard.get(code) == win_ansi.get(code)
    )


def add_truetype_base_encodings(pdf: Pdf) -> int:
    """Give /BaseEncoding /WinAnsiEncoding to TrueType encodings that lack one.

    PDF/A-2 and PDF/A-3 require the encoding of a non-symbolic TrueType font
    to be based on WinAnsiEncoding or MacRomanEncoding. An encoding
    dictionary with /Differences and no /BaseEncoding is based on
    StandardEncoding. A font is changed only if every code shown in it, in
    the content the document can draw, is either assigned by /Differences or
    has the same glyph name in both encodings, so no glyph drawn changes. If
    the content cannot be scanned completely, no font is changed.

    The font's encoding dictionary is replaced, not modified, since other
    fonts may share it.

    Args:
        pdf: An open pikepdf.Pdf object

    Returns:
        The number of fonts changed.
    """
    candidates = [obj for obj in pdf.objects if _needs_base_encoding(obj)]
    if not candidates:
        return 0
    used = font_codes(pdf)
    if used is None:
        log.debug("Content could not be scanned; TrueType encodings left alone")
        return 0
    kept = _standard_codes_kept_by_win_ansi()
    count = 0
    for font in candidates:
        encoding = font.get(Name.Encoding)
        assert isinstance(encoding, Dictionary)
        try:
            differences = parse_differences(encoding.get(Name.Differences))
        except DifferencesError:
            continue
        codes = used.get(font.objgen, set())
        if not all(code in differences or code in kept for code in codes):
            continue
        replacement = Dictionary({str(key): value for key, value in encoding.items()})
        replacement[Name.BaseEncoding] = Name.WinAnsiEncoding
        font[Name.Encoding] = replacement
        count += 1
    return count


def remove_name_tree(pdf: Pdf, key: Name) -> bool:
    """Remove an entry of the document's name dictionary.

    Args:
        pdf: An open pikepdf.Pdf object
        key: The entry, such as ``Name.JavaScript``.

    Returns:
        True if the entry was present and removed.
    """
    names = pdf.Root.get(Name.Names)
    if not isinstance(names, Dictionary) or key not in names:
        return False
    del names[key]
    return True


_OCTET_STREAM = Name('/application/octet-stream')


@dataclass
class EmbeddedFileRepairResult:
    """What :func:`repair_embedded_files` changed.

    Attributes:
        subtypes_set: The number of embedded file streams given the MIME
            type application/octet-stream.
        relationships_set: The number of file specifications given
            /AFRelationship /Unspecified.
        associated_added: The number of file specifications added to the
            catalog's /AF array.
    """

    subtypes_set: int = 0
    relationships_set: int = 0
    associated_added: int = 0


def _embedded_file_specs(pdf: Pdf) -> list[Dictionary]:
    """Return the file specifications of the embedded files name tree.

    Only indirect dictionaries with /EF are returned, each once, in tree
    order. A malformed tree is read as far as it can be.
    """
    names = _get_dict(pdf.Root, Name.Names)
    root = names.get(Name.EmbeddedFiles)
    found: list[Dictionary] = []
    seen: set[tuple[int, int]] = set()
    pending: list[Object] = [root] if isinstance(root, Dictionary) else []
    while pending:
        node = pending.pop()
        if not isinstance(node, Dictionary):
            continue
        if node.is_indirect:
            if node.objgen in seen:
                continue
            seen.add(node.objgen)
        kids = node.get(Name.Kids)
        if isinstance(kids, Array):
            pending.extend(reversed(list(kids)))
        items = node.get(Name.Names)
        if not isinstance(items, Array):
            continue
        for value in list(items)[1::2]:
            if (
                isinstance(value, Dictionary)
                and value.is_indirect
                and value.objgen not in seen
                and Name.EF in value
            ):
                seen.add(value.objgen)
                found.append(value)
    return found


def repair_embedded_files(pdf: Pdf) -> EmbeddedFileRepairResult:
    """Supply what PDF/A-3 requires of embedded files, where it is missing.

    PDF/A-3 requires each embedded file stream to state its MIME type, each
    file specification to state its relationship to the document, and each
    embedded file to be an associated file. For the embedded files of the
    name tree and of the catalog's /AF array, an embedded file stream
    without /Subtype is given application/octet-stream, which ISO 19005-3
    prescribes when the type is not known; a file specification without
    /AFRelationship is given /Unspecified; and a file specification of the
    name tree that no /AF array lists is appended to the catalog's /AF
    array. A catalog /AF that is not an array is left alone. Values that are
    present but wrong are not changed.

    Args:
        pdf: An open pikepdf.Pdf object

    Returns:
        What was changed.
    """
    result = EmbeddedFileRepairResult()
    in_tree = _embedded_file_specs(pdf)
    af = pdf.Root.get(Name.AF)
    filespecs = list(in_tree)
    if isinstance(af, Array):
        filespecs += [
            item
            for item in af
            if isinstance(item, Dictionary) and item.is_indirect and Name.EF in item
        ]

    done: set[tuple[int, int]] = set()
    streams_done: set[tuple[int, int]] = set()
    for filespec in filespecs:
        if filespec.objgen in done:
            continue
        done.add(filespec.objgen)
        if Name.AFRelationship not in filespec:
            filespec[Name.AFRelationship] = Name.Unspecified
            result.relationships_set += 1
        for _key, stream in _get_dict(filespec, Name.EF).items():
            if not isinstance(stream, Stream) or stream.objgen in streams_done:
                continue
            streams_done.add(stream.objgen)
            if Name.Subtype not in stream:
                stream[Name.Subtype] = _OCTET_STREAM
                result.subtypes_set += 1

    associated = associated_file_objgens(pdf.objects)
    missing = [fs for fs in in_tree if fs.objgen not in associated]
    if missing:
        if af is None:
            pdf.Root[Name.AF] = Array(missing)
            result.associated_added = len(missing)
        elif isinstance(af, Array):
            for filespec in missing:
                af.append(filespec)
            result.associated_added = len(missing)
    return result
