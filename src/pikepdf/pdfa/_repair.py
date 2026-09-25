# SPDX-FileCopyrightText: 2026 James R. Barlow
# SPDX-License-Identifier: MPL-2.0

"""Repairs that make a document acceptable to PDF/A without changing content."""

from __future__ import annotations

import logging
from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import cast

import pikepdf
from pikepdf import Array, Dictionary, Name, Object, Pdf, Stream

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
    """What :func:`repair_annotation_flags` changed.

    Attributes:
        removed: The number of annotations removed, by subtype (without the
            leading slash).
        removed_pages: The page numbers (1-based) annotations were removed from.
        print_flags_set: The number of annotations given the Print flag.
    """

    removed: Counter[str] = field(default_factory=Counter)
    removed_pages: set[int] = field(default_factory=set)
    print_flags_set: int = 0


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
    Hidden, Invisible and NoView flags (and ToggleNoView, for PDF/A-2 and
    later). An annotation with any of those flags set is not shown to the
    reader, so it is removed, as Ghostscript does, rather than made visible:
    along with it goes its /Popup annotation, and a /Popup entry that
    refers to a removed annotation is deleted. The remaining annotations are
    given the Print flag if they lack it, leaving their other flags alone.

    Logs one debug message if any annotation was removed.

    Args:
        pdf: An open pikepdf.Pdf object

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
