# SPDX-FileCopyrightText: 2026 James R. Barlow
# SPDX-License-Identifier: MPL-2.0

"""Helpers for removing potentially unwanted content from a PDF.

What is "safe" to remove from a PDF depends entirely on your use case and
threat model. The functions in this module each perform one narrowly scoped,
low-risk operation: they remove active or auxiliary content (scripts, embedded
files, actions that reach the network or filesystem, thumbnails, search
indexes) while leaving the standard page content, page geometry, and document
metadata in place.

These operations are *not* guaranteed to leave a document's appearance
unchanged. PDF JavaScript, for example, can alter how a document renders, so
removing it may change the result — although in practice most PDFs are designed
to display correctly without it, since many viewers do not run PDF JavaScript.

They deliberately do **not** strip XFA, AcroForm, annotations, the document
``/ID``, or metadata wholesale, because those operations frequently destroy
legitimate document content. See the :doc:`Sanitizing PDFs </topics/sanitize>`
topic for a discussion of the tradeoffs and the limits of what programmatic
sanitization can accomplish.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from pikepdf.objects import Array, Dictionary, Name, Stream

if TYPE_CHECKING:
    from collections.abc import Callable

    from pikepdf import Object, Pdf

__all__ = [
    'Sanitizer',
    'remove_attachments',
    'remove_external_access',
    'remove_javascript',
    'remove_search_index',
    'remove_thumbnails',
]

# Action subtypes (the value of an action dictionary's /S key).
_JS_SUBTYPES = frozenset({Name.JavaScript})
_EXTERNAL_SUBTYPES = frozenset(
    {Name.URI, Name.Launch, Name.GoToR, Name.SubmitForm, Name.ImportData}
)

# Guard against pathological /Next chains built from inline (direct) action
# dictionaries, which cannot be deduplicated by object id.
_MAX_CHAIN_DEPTH = 50


def _is_action_dict(obj: Object | None) -> bool:
    """Return True if *obj* looks like a PDF action dictionary.

    Action dictionaries carry an ``/S`` (subtype) key whose value is a Name.
    Streams are permitted because an action's dictionary part may, rarely, be
    attached to a stream object.
    """
    if not isinstance(obj, (Dictionary, Stream)):
        return False
    return isinstance(obj.get(Name.S), Name)


def _is_targeted_action(obj: Object, targets: frozenset[Name]) -> bool:
    """Return True if *obj* is an action dict whose subtype is in *targets*."""
    if not _is_action_dict(obj):
        return False
    subtype = obj.get(Name.S)
    return isinstance(subtype, Name) and subtype in targets


def _cycle_hit(obj: Object, seen: set[tuple[int, int]]) -> bool:
    """Track visited indirect objects to break cyclic /Next chains.

    Direct (inline) objects all report objgen ``(0, 0)`` and cannot be
    deduplicated this way; the recursion depth cap handles those.
    """
    if obj.is_indirect:
        objgen = obj.objgen
        if objgen in seen:
            return True
        seen.add(objgen)
    return False


def _as_actions(next_obj: Object) -> list[Object]:
    """Normalize a /Next value (single action dict or Array) to a list."""
    if isinstance(next_obj, Array):
        return list(next_obj)
    return [next_obj]


def _neutralize_next_chain(
    action: Object,
    targets: frozenset[Name],
    seen: set[tuple[int, int]],
    depth: int = 0,
) -> None:
    """Prune targeted actions from *action*'s /Next chain, in place.

    A pruned node's own (already-cleaned) /Next survivors are grafted upward so
    that legitimate downstream actions are preserved.
    """
    next_obj = action.get(Name.Next)
    if depth >= _MAX_CHAIN_DEPTH or next_obj is None:
        return

    survivors: list[Object] = []
    for child in _as_actions(next_obj):
        if _cycle_hit(child, seen):
            continue
        # Clean the child's own chain first, so grafted survivors are clean.
        _neutralize_next_chain(child, targets, seen, depth + 1)
        if _is_targeted_action(child, targets):
            # Drop this child, but keep anything still hanging off its /Next.
            grafted = child.get(Name.Next)
            if grafted is not None:
                survivors.extend(_as_actions(grafted))
        else:
            survivors.append(child)

    if not survivors:
        del action[Name.Next]
    elif len(survivors) == 1:
        action[Name.Next] = survivors[0]
    else:
        action[Name.Next] = Array(survivors)


def _neutralize_slot(
    holder: Object,
    key: Name,
    targets: frozenset[Name],
    seen: set[tuple[int, int]],
) -> None:
    """Neutralize a single-action slot, e.g. an annotation's /A.

    If the action's subtype is targeted, the slot is deleted entirely;
    otherwise the action's /Next chain is pruned.
    """
    action = holder.get(key)
    if action is None or not _is_action_dict(action):
        return  # e.g. /OpenAction holding a destination array
    if _cycle_hit(action, seen):
        return
    if _is_targeted_action(action, targets):
        del holder[key]
        return
    _neutralize_next_chain(action, targets, seen)


def _neutralize_additional_actions(holder: Object, targets: frozenset[Name]) -> None:
    """Neutralize every event in *holder*'s /AA additional-actions dictionary.

    The /AA dictionary is dropped if it becomes empty.
    """
    aa = holder.get(Name.AA)
    if not isinstance(aa, Dictionary):
        return
    for event_key in list(aa.keys()):
        _neutralize_slot(aa, Name(event_key), targets, set())
    if len(aa.keys()) == 0:
        del holder[Name.AA]


def _sanitize_actions(pdf: Pdf, targets: frozenset[Name]) -> None:
    """Walk all known action-holder slots and neutralize targeted actions."""
    root = pdf.Root

    # Document catalog.
    _neutralize_slot(root, Name.OpenAction, targets, set())
    _neutralize_additional_actions(root, targets)

    # Pages and their annotations.
    for page in pdf.pages:
        pobj = page.obj
        _neutralize_additional_actions(pobj, targets)
        annots = pobj.get(Name.Annots)
        if isinstance(annots, Array):
            for annot in annots:
                if not isinstance(annot, Dictionary):
                    continue
                _neutralize_slot(annot, Name.A, targets, set())
                _neutralize_additional_actions(annot, targets)

    # Interactive form fields.
    if pdf.acroform.exists:
        for field in pdf.acroform.fields:
            _neutralize_additional_actions(field.obj, targets)


def remove_javascript(pdf: Pdf) -> None:
    """Remove all JavaScript from a PDF, in place.

    Purges document-level named JavaScript (the ``/Root/Names/JavaScript``
    name tree) and every ``/JavaScript`` action reachable from document, page,
    annotation, and form-field action slots, including actions chained via
    ``/Next``.

    Page content, annotations (minus their scripts), form fields, and metadata
    are left in place. Note that PDF JavaScript can alter how a document
    renders, so removing it may change the result; in practice most documents
    are designed to display correctly without it.

    The main legitimate use of PDF JavaScript is interactive form validation;
    removing it may break that. Most PDF viewers other than Acrobat do not
    fully execute PDF JavaScript and warn about or disable it.

    This operation is idempotent and safe to call on a PDF that contains no
    JavaScript.

    Args:
        pdf: The PDF to modify in place.

    Note:
        To scrub document metadata, use
        :meth:`pikepdf.Pdf.open_metadata` with ``set_pikepdf_as_editor=False``
        instead; this function does not touch metadata.
    """
    _sanitize_actions(pdf, _JS_SUBTYPES)
    _drop_named_javascript(pdf)


def _drop_named_javascript(pdf: Pdf) -> None:
    """Drop the document-level ``/Root/Names/JavaScript`` name tree."""
    names = pdf.Root.get(Name.Names)
    if isinstance(names, Dictionary) and Name.JavaScript in names:
        del names[Name.JavaScript]


def remove_attachments(pdf: Pdf) -> None:
    """Remove all embedded files (attachments) from a PDF, in place.

    Clears the ``/Root/Names/EmbeddedFiles`` name tree (the
    :attr:`pikepdf.Pdf.attachments` mapping) and removes ``/AF`` (associated
    files) references at the catalog, page, and annotation level. FileAttachment
    annotations are defanged by removing their embedded ``/FS`` file
    specification; the annotation itself is retained so page geometry is
    unchanged.

    Embedded files can be integral to a document, especially in digital-signing
    workflows, so remove them deliberately.

    This operation is idempotent and safe to call on a PDF that has no
    attachments.

    Args:
        pdf: The PDF to modify in place.
    """
    pdf.attachments.clear()

    # Belt and suspenders: drop the name tree key itself, in case an
    # associated-files-only embed isn't enumerated by the mapping above.
    names = pdf.Root.get(Name.Names)
    if isinstance(names, Dictionary) and Name.EmbeddedFiles in names:
        del names[Name.EmbeddedFiles]

    _remove_associated_files(pdf.Root)
    for page in pdf.pages:
        pobj = page.obj
        _remove_associated_files(pobj)
        annots = pobj.get(Name.Annots)
        if isinstance(annots, Array):
            for annot in annots:
                if not isinstance(annot, Dictionary):
                    continue
                _remove_associated_files(annot)
                if annot.get(Name.Subtype) == Name.FileAttachment and Name.FS in annot:
                    del annot[Name.FS]


def _remove_associated_files(holder: Object) -> None:
    """Remove an /AF (associated files) reference if present."""
    if Name.AF in holder:
        del holder[Name.AF]


def remove_external_access(pdf: Pdf) -> None:
    """Neutralize actions that reach the network or filesystem, in place.

    Removes ``/URI``, ``/Launch``, ``/GoToR`` (remote go-to), ``/SubmitForm``,
    and ``/ImportData`` actions wherever they are reachable from document,
    page, annotation, and form-field action slots, including actions chained
    via ``/Next``.

    Link annotations are retained (so any visible underline or box is
    preserved) but their triggering action is removed, rendering them inert.
    Visible content and metadata are left intact.

    URI actions are usually benign hyperlinks; this function is a separate
    opt-in so callers can decide whether to sever external access.

    This operation is idempotent and safe to call on a PDF that contains no
    such actions.

    Args:
        pdf: The PDF to modify in place.

    Note:
        To scrub document metadata, use
        :meth:`pikepdf.Pdf.open_metadata` with ``set_pikepdf_as_editor=False``
        instead; this function does not touch metadata.
    """
    _sanitize_actions(pdf, _EXTERNAL_SUBTYPES)


def remove_thumbnails(pdf: Pdf) -> None:
    """Remove embedded page thumbnails from a PDF, in place.

    Deletes the ``/Thumb`` thumbnail image stream from every page. Thumbnails
    are an optional convenience that viewers can regenerate on the fly, so
    removing them is safe; doing so reduces file size and avoids stale
    thumbnails that some editors fail to keep in sync with edited pages. A stale
    thumbnail can also leak the prior appearance of a page you intended to edit
    or redact.

    This operation is idempotent and safe to call on a PDF that has no
    thumbnails.

    Args:
        pdf: The PDF to modify in place.
    """
    for page in pdf.pages:
        if Name.Thumb in page.obj:
            del page.obj[Name.Thumb]


def remove_search_index(pdf: Pdf) -> None:
    """Remove an embedded full-text search index from a PDF, in place.

    Adobe Acrobat can embed a full-text search index in a document to speed up
    searching. It is stored as a ``/SearchIndex`` entry in the catalog's
    ``/PieceInfo`` dictionary. This function removes that entry (and the
    ``/PieceInfo`` dictionary itself if it becomes empty); the index's data
    streams become unreferenced and are dropped when the PDF is saved.

    Removing the index reduces file size, re-enables Fast Web View (which an
    embedded index precludes), and avoids a stale index leaking content you
    intended to edit or redact. Non-Acrobat viewers do not use it.

    This operation is idempotent and safe to call on a PDF that has no embedded
    search index.

    Args:
        pdf: The PDF to modify in place.
    """
    piece_info = pdf.Root.get(Name.PieceInfo)
    if not isinstance(piece_info, Dictionary):
        return
    if Name.SearchIndex in piece_info:
        del piece_info[Name.SearchIndex]
    if len(piece_info.keys()) == 0:
        del pdf.Root[Name.PieceInfo]


class Sanitizer:
    """A fluent builder that accumulates sanitization operations.

    Each ``remove_*`` method records an operation and returns ``self`` so calls
    can be chained. Nothing happens until :meth:`apply` is called with a PDF;
    this lets a single :class:`Sanitizer` be configured once and reused across
    many documents. The action-based removals (JavaScript, external access) are
    coalesced into a single traversal of the document when applied.

    The methods correspond to the module-level functions of the same name and
    have the same scope and caveats. Like those functions, the operations are
    deliberately limited to the curated, low-risk set; there is no "remove
    everything" option, because blanket removal of forms, annotations, or XFA
    usually destroys legitimate content.

    Example:
        Configure once, apply to many files::

            scrubber = (
                pikepdf.sanitize.Sanitizer()
                .remove_javascript()
                .remove_external_access()
                .remove_attachments()
            )
            for path in untrusted_paths:
                with pikepdf.open(path) as pdf:
                    scrubber.apply(pdf).save(out_dir / path.name)
    """

    def __init__(self) -> None:
        """Create an empty sanitizer with no operations recorded."""
        self._action_subtypes: set[Name] = set()
        self._drop_named_js = False
        self._structural: list[Callable[[Pdf], None]] = []

    def remove_javascript(self) -> Sanitizer:
        """Record removal of all JavaScript. See :func:`remove_javascript`."""
        self._action_subtypes |= _JS_SUBTYPES
        self._drop_named_js = True
        return self

    def remove_external_access(self) -> Sanitizer:
        """Record removal of external-access actions.

        See :func:`remove_external_access`.
        """
        self._action_subtypes |= _EXTERNAL_SUBTYPES
        return self

    def remove_attachments(self) -> Sanitizer:
        """Record removal of embedded files. See :func:`remove_attachments`."""
        self._structural.append(remove_attachments)
        return self

    def remove_thumbnails(self) -> Sanitizer:
        """Record removal of page thumbnails. See :func:`remove_thumbnails`."""
        self._structural.append(remove_thumbnails)
        return self

    def remove_search_index(self) -> Sanitizer:
        """Record removal of an embedded search index.

        See :func:`remove_search_index`.
        """
        self._structural.append(remove_search_index)
        return self

    def apply(self, pdf: Pdf) -> Pdf:
        """Apply the recorded operations to *pdf*, in place.

        The action-based removals run as a single combined traversal, followed
        by the structural removals in the order they were recorded.

        Args:
            pdf: The PDF to modify in place.

        Returns:
            The same ``pdf``, to allow further chaining, e.g.
            ``.apply(pdf).save(...)``.
        """
        if self._action_subtypes:
            _sanitize_actions(pdf, frozenset(self._action_subtypes))
        if self._drop_named_js:
            _drop_named_javascript(pdf)
        for operation in self._structural:
            operation(pdf)
        return pdf
