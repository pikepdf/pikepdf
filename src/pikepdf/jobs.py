# SPDX-FileCopyrightText: 2026 James R. Barlow
# SPDX-License-Identifier: MPL-2.0

"""A Pythonic builder for qpdf jobs.

qpdf exposes a large amount of functionality through its "job" interface: the
same operations the ``qpdf`` command line tool performs (encrypt, decrypt,
merge/split pages, linearize, compress, manage attachments, overlay/underlay,
and so on). pikepdf binds this as :class:`pikepdf.Job`, which accepts a job
specified as a JSON string, a Python ``dict``, or command line arguments.

Writing that JSON by hand is awkward: the keys are camelCase, the encryption
block has ``40bit``/``128bit``/``256bit`` variants with their own restriction
vocabulary, and permission flags are expressed as restrictions rather than
grants. :class:`JobBuilder` provides a fluent, snake_case, Pythonic API that
assembles a valid job specification and hands it to :class:`pikepdf.Job`.

qpdf's JSON job format is a complete representation of any job configuration --
``initializeFromJson``, ``initializeFromArgv`` and qpdf's own fluent C++
``config()`` builder all funnel through the same handlers -- so nothing is lost
by building the specification in Python.

Example:
    >>> from pikepdf import JobBuilder, Permissions
    >>> (
    ...     JobBuilder()
    ...     .input('in.pdf')
    ...     .output('out.pdf')
    ...     .encrypt(owner_password='secret', allow=Permissions(extract=False))
    ...     .run()
    ... )  # doctest: +SKIP
"""

from __future__ import annotations

import os
from copy import deepcopy
from typing import TYPE_CHECKING, Any, Literal

from pikepdf._core import Job
from pikepdf.models.encryption import DEFAULT_PERMISSIONS, Encryption, Permissions

if TYPE_CHECKING:
    from pikepdf._core import Pdf

__all__ = ['JobBuilder']

# Map snake_case Python names to qpdf's camelCase job-JSON keys for the
# scalar, top-level options reachable through .set(). Structured blocks
# (encrypt, pages, attachments, overlay/underlay, global) have dedicated
# methods and are intentionally excluded here. This map is also used by the
# schema-drift guard test, which asserts every value still exists in the
# libqpdf job schema.
_KEY_MAP: dict[str, str] = {
    'input_file': 'inputFile',
    'password': 'password',
    'password_file': 'passwordFile',
    'empty': 'empty',
    'json_input': 'jsonInput',
    'output_file': 'outputFile',
    'replace_input': 'replaceInput',
    'qdf': 'qdf',
    'preserve_unreferenced': 'preserveUnreferenced',
    'newline_before_endstream': 'newlineBeforeEndstream',
    'normalize_content': 'normalizeContent',
    'stream_data': 'streamData',
    'compress_streams': 'compressStreams',
    'recompress_flate': 'recompressFlate',
    'decode_level': 'decodeLevel',
    'decrypt': 'decrypt',
    'deterministic_id': 'deterministicId',
    'static_aes_iv': 'staticAesIv',
    'static_id': 'staticId',
    'no_original_object_ids': 'noOriginalObjectIds',
    'copy_encryption': 'copyEncryption',
    'encryption_file_password': 'encryptionFilePassword',
    'linearize': 'linearize',
    'linearize_pass1': 'linearizePass1',
    'object_streams': 'objectStreams',
    'min_version': 'minVersion',
    'force_version': 'forceVersion',
    'progress': 'progress',
    'split_pages': 'splitPages',
    'json_output': 'jsonOutput',
    'remove_restrictions': 'removeRestrictions',
    'check': 'check',
    'check_linearization': 'checkLinearization',
    'filtered_stream_data': 'filteredStreamData',
    'raw_stream_data': 'rawStreamData',
    'show_encryption': 'showEncryption',
    'show_encryption_key': 'showEncryptionKey',
    'show_linearization': 'showLinearization',
    'show_npages': 'showNpages',
    'show_object': 'showObject',
    'show_pages': 'showPages',
    'show_xref': 'showXref',
    'with_images': 'withImages',
    'list_attachments': 'listAttachments',
    'show_attachment': 'showAttachment',
    'json': 'json',
    'json_stream_data': 'jsonStreamData',
    'json_stream_prefix': 'jsonStreamPrefix',
    'update_from_json': 'updateFromJson',
    'allow_weak_crypto': 'allowWeakCrypto',
    'keep_files_open': 'keepFilesOpen',
    'keep_files_open_threshold': 'keepFilesOpenThreshold',
    'no_warn': 'noWarn',
    'verbose': 'verbose',
    'test_json_schema': 'testJsonSchema',
    'ignore_xref_streams': 'ignoreXrefStreams',
    'password_is_hex_key': 'passwordIsHexKey',
    'password_mode': 'passwordMode',
    'suppress_password_recovery': 'suppressPasswordRecovery',
    'suppress_recovery': 'suppressRecovery',
    'coalesce_contents': 'coalesceContents',
    'compression_level': 'compressionLevel',
    'jpeg_quality': 'jpegQuality',
    'externalize_inline_images': 'externalizeInlineImages',
    'ii_min_bytes': 'iiMinBytes',
    'remove_unreferenced_resources': 'removeUnreferencedResources',
    'collate': 'collate',
    'flatten_annotations': 'flattenAnnotations',
    'flatten_rotation': 'flattenRotation',
    'generate_appearances': 'generateAppearances',
    'keep_inline_images': 'keepInlineImages',
    'oi_min_area': 'oiMinArea',
    'oi_min_height': 'oiMinHeight',
    'oi_min_width': 'oiMinWidth',
    'optimize_images': 'optimizeImages',
    'remove_acroform': 'removeAcroform',
    'remove_info': 'removeInfo',
    'remove_metadata': 'removeMetadata',
    'remove_page_labels': 'removePageLabels',
    'remove_structure': 'removeStructure',
    'report_memory_usage': 'reportMemoryUsage',
    'warning_exit0': 'warningExit0',
    'preserve_unreferenced_resources': 'preserveUnreferencedResources',
    'requires_password': 'requiresPassword',
    'is_encrypted': 'isEncrypted',
}

# Keys for the structured blocks, kept here so the schema-drift guard test can
# verify them against the libqpdf job schema alongside _KEY_MAP.
_ENCRYPT_KEYS = frozenset(
    {
        'encrypt',
        'userPassword',
        'ownerPassword',
        '40bit',
        '128bit',
        '256bit',
        'accessibility',
        'annotate',
        'assemble',
        'cleartextMetadata',
        'extract',
        'form',
        'modifyOther',
        'modify',
        'print',
        'forceV4',
        'useAes',
        'allowInsecure',
        'forceR5',
    }
)
_BLOCK_KEYS = frozenset(
    {
        'pages',
        'overlay',
        'underlay',
        'addAttachment',
        'copyAttachmentsFrom',
        'removeAttachment',
        'rotate',
        'global',
        'file',
        'range',
        'from',
        'to',
        'repeat',
        'prefix',
        'key',
        'filename',
        'mimetype',
        'description',
        'creationdate',
        'moddate',
        'replace',
        'noDefaultLimits',
        'parserMaxContainerSize',
        'parserMaxContainerSizeDamaged',
        'parserMaxErrors',
        'parserMaxNesting',
        'maxStreamFilters',
    }
)

#: Every qpdf job-JSON key this module may emit. Used by the schema-drift test.
ALL_JSON_KEYS = frozenset(_KEY_MAP.values()) | _ENCRYPT_KEYS | _BLOCK_KEYS

# qpdf's flag-style options take an empty string to enable them.
_ENABLE = ''


def _path(p: Any) -> str:
    """Coerce a path-like to the str form qpdf job JSON expects."""
    if isinstance(p, os.PathLike):
        p = os.fspath(p)
    if isinstance(p, bytes):
        return os.fsdecode(p)
    return str(p)


def _yn(allowed: bool) -> Literal['y', 'n']:
    return 'y' if allowed else 'n'


def _bits_for_R(R: int) -> int:
    """Map an :class:`Encryption` security-handler revision to a key length."""
    if R >= 5:
        return 256
    if R == 4:
        return 128
    if R == 3:
        return 128
    return 40


class JobBuilder:
    """Fluently assemble a qpdf job and run it.

    Each method records part of the job specification and returns ``self`` so
    calls can be chained. List-valued sections (pages, attachments,
    overlay/underlay) use repeatable ``add_*`` methods. Terminal methods
    :meth:`build`, :meth:`run` and :meth:`create_pdf` hand the assembled
    specification to :class:`pikepdf.Job`.

    The builder performs minimal local validation; qpdf is the source of truth
    and will raise :class:`pikepdf.JobUsageError` (or ``RuntimeError`` for
    malformed JSON) for invalid configurations when the job is built.
    """

    _spec: dict[str, Any]

    def __init__(self) -> None:
        """Create an empty job specification."""
        self._spec = {}

    # -- Input / output -----------------------------------------------------

    def input(self, file: Any, *, password: str | None = None) -> JobBuilder:
        """Set the input file, optionally with a password.

        Args:
            file: Path to the input PDF.
            password: Password for an encrypted input file.
        """
        if 'empty' in self._spec:
            raise ValueError("Cannot set an input file after empty()")
        self._spec['inputFile'] = _path(file)
        if password is not None:
            self._spec['password'] = password
        return self

    def empty(self) -> JobBuilder:
        """Use an empty PDF as input instead of an input file."""
        if 'inputFile' in self._spec:
            raise ValueError("Cannot use empty() when an input file is set")
        self._spec['empty'] = _ENABLE
        return self

    def output(self, file: Any) -> JobBuilder:
        """Set the output file.

        Args:
            file: Path to write. For :meth:`split_pages`, include a ``%d``
                placeholder for the page group number.
        """
        self._spec['outputFile'] = _path(file)
        return self

    def replace_input(self) -> JobBuilder:
        """Overwrite the input file with the output (in place)."""
        self._spec['replaceInput'] = _ENABLE
        return self

    # -- Encryption ---------------------------------------------------------

    def encrypt(
        self,
        encryption: Encryption | None = None,
        *,
        owner_password: str | None = None,
        user_password: str | None = None,
        bits: Literal[40, 128, 256] = 256,
        allow: Permissions | None = None,
        metadata: bool = True,
        aes: bool | None = None,
        force_v4: bool = False,
        allow_insecure: bool = False,
        force_r5: bool = False,
    ) -> JobBuilder:
        """Encrypt the output.

        Either pass a :class:`pikepdf.Encryption` object positionally, or use
        the keyword arguments. The two forms are mutually exclusive.

        Args:
            encryption: A :class:`pikepdf.Encryption` describing passwords,
                permissions and algorithm. If given, the keyword arguments
                must not be used.
            owner_password: Owner password (full access).
            user_password: User password (restricted access).
            bits: Key length: 40, 128 or 256 (default). 40 and 128-bit RC4
                are weak and require :meth:`allow_weak_crypto`.
            allow: A :class:`pikepdf.Permissions` describing what the user
                password is permitted to do. Permissions default to
                :data:`pikepdf.models.encryption.DEFAULT_PERMISSIONS`.
            metadata: If False, document metadata is left unencrypted
                (128/256-bit only).
            aes: For 128-bit, request AES rather than RC4.
            force_v4: For 128-bit, force ``V=4`` in the encryption dictionary.
            allow_insecure: For 256-bit, allow an insecure empty owner password.
            force_r5: For 256-bit, use the deprecated ``R=5`` algorithm.
        """
        if encryption is not None:
            if any(v is not None for v in (owner_password, user_password, allow)):
                raise ValueError(
                    "Pass either an Encryption object or keyword arguments, not both"
                )
            owner_password = encryption.owner
            user_password = encryption.user
            allow = encryption.allow
            metadata = encryption.metadata
            aes = encryption.aes
            bits = _bits_for_R(encryption.R)  # type: ignore[assignment]

        if bits not in (40, 128, 256):
            raise ValueError("bits must be 40, 128 or 256")
        if allow is None:
            allow = DEFAULT_PERMISSIONS

        variant = f'{bits}bit'
        self._spec['encrypt'] = {
            'userPassword': user_password or '',
            'ownerPassword': owner_password or '',
            variant: _encrypt_flags(
                bits,
                allow,
                metadata=metadata,
                aes=aes,
                force_v4=force_v4,
                allow_insecure=allow_insecure,
                force_r5=force_r5,
            ),
        }
        return self

    def decrypt(self) -> JobBuilder:
        """Remove encryption from the input file."""
        self._spec['decrypt'] = _ENABLE
        return self

    def remove_restrictions(self) -> JobBuilder:
        """Remove security restrictions, recovering the encryption key if needed."""
        self._spec['removeRestrictions'] = _ENABLE
        return self

    def allow_weak_crypto(self) -> JobBuilder:
        """Permit writing files with weak (RC4) cryptography."""
        self._spec['allowWeakCrypto'] = _ENABLE
        return self

    # -- Pages --------------------------------------------------------------

    def add_pages(
        self, file: Any, page_range: str | None = None, *, password: str | None = None
    ) -> JobBuilder:
        """Append pages from a file to the page-selection (merge/split) operation.

        Args:
            file: Source PDF. Use ``'.'`` to refer to the primary input file.
            page_range: qpdf page range, e.g. ``'1-5'`` or ``'z-1'`` (reversed).
                Omit to use all pages.
            password: Password for an encrypted source file.
        """
        entry: dict[str, str] = {'file': _path(file)}
        if page_range is not None:
            entry['range'] = page_range
        if password is not None:
            entry['password'] = password
        self._spec.setdefault('pages', []).append(entry)
        return self

    def split_pages(self, group: int | None = None) -> JobBuilder:
        """Write pages to separate files.

        Args:
            group: Number of pages per output file. The output filename should
                contain a ``%d`` placeholder.
        """
        self._spec['splitPages'] = '' if group is None else str(group)
        return self

    def collate(self, n: int | None = None) -> JobBuilder:
        """Collate rather than concatenate the page selection.

        Args:
            n: Number of pages to take from each file per round.
        """
        self._spec['collate'] = '' if n is None else str(n)
        return self

    def rotate(self, angle: int | str, page_range: str | None = None) -> JobBuilder:
        """Rotate pages.

        Args:
            angle: Rotation in degrees: ``90``, ``180``, ``270``; prefix with
                ``+`` or ``-`` to rotate relative to the current rotation.
            page_range: Page range to rotate. Omit to rotate all pages.
        """
        spec = str(angle) if page_range is None else f'{angle}:{page_range}'
        self._spec.setdefault('rotate', []).append(spec)
        return self

    # -- Output transforms --------------------------------------------------

    def linearize(self) -> JobBuilder:
        """Linearize (web-optimize) the output."""
        self._spec['linearize'] = _ENABLE
        return self

    def qdf(self) -> JobBuilder:
        """Produce QDF output suitable for inspection in a text editor."""
        self._spec['qdf'] = _ENABLE
        return self

    def compress(
        self,
        *,
        compress_streams: bool | None = None,
        object_streams: Literal['generate', 'preserve', 'disable'] | None = None,
        recompress_flate: bool = False,
        compression_level: int | None = None,
        decode_level: Literal['none', 'generalized', 'specialized', 'all']
        | None = None,
        stream_data: Literal['compress', 'preserve', 'uncompress'] | None = None,
    ) -> JobBuilder:
        """Configure stream and object-stream compression.

        Args:
            compress_streams: Compress uncompressed streams.
            object_streams: Control use of object streams.
            recompress_flate: Uncompress and recompress flate streams.
            compression_level: Flate compression level (1-9).
            decode_level: Which streams to uncompress before recompressing.
            stream_data: Legacy combined stream compression control.
        """
        if compress_streams is not None:
            self._spec['compressStreams'] = _yn(compress_streams)
        if object_streams is not None:
            self._spec['objectStreams'] = object_streams
        if recompress_flate:
            self._spec['recompressFlate'] = _ENABLE
        if compression_level is not None:
            self._spec['compressionLevel'] = str(compression_level)
        if decode_level is not None:
            self._spec['decodeLevel'] = decode_level
        if stream_data is not None:
            self._spec['streamData'] = stream_data
        return self

    def optimize_images(self) -> JobBuilder:
        """Recompress images using more efficient compression where possible."""
        self._spec['optimizeImages'] = _ENABLE
        return self

    # -- Attachments --------------------------------------------------------

    def add_attachment(
        self,
        file: Any,
        *,
        key: str | None = None,
        filename: str | None = None,
        mimetype: str | None = None,
        description: str | None = None,
        creationdate: str | None = None,
        moddate: str | None = None,
        replace: bool = False,
    ) -> JobBuilder:
        """Attach (embed) a file in the output.

        Args:
            file: Path to the file to attach.
            key: Attachment key; defaults to the filename.
            filename: Displayed filename of the attachment.
            mimetype: MIME type, e.g. ``'application/pdf'``.
            description: Human-readable description.
            creationdate: Creation date (PDF date string).
            moddate: Modification date (PDF date string).
            replace: Replace an existing attachment with the same key.
        """
        entry: dict[str, str] = {'file': _path(file)}
        if key is not None:
            entry['key'] = key
        if filename is not None:
            entry['filename'] = filename
        if mimetype is not None:
            entry['mimetype'] = mimetype
        if description is not None:
            entry['description'] = description
        if creationdate is not None:
            entry['creationdate'] = creationdate
        if moddate is not None:
            entry['moddate'] = moddate
        if replace:
            entry['replace'] = _ENABLE
        self._spec.setdefault('addAttachment', []).append(entry)
        return self

    def copy_attachments_from(
        self, file: Any, *, prefix: str | None = None, password: str | None = None
    ) -> JobBuilder:
        """Copy all attachments from another PDF.

        Args:
            file: Source PDF to copy attachments from.
            prefix: Prefix to disambiguate keys that collide with existing ones.
            password: Password for an encrypted source file.
        """
        entry: dict[str, str] = {'file': _path(file)}
        if prefix is not None:
            entry['prefix'] = prefix
        if password is not None:
            entry['password'] = password
        self._spec.setdefault('copyAttachmentsFrom', []).append(entry)
        return self

    def remove_attachment(self, key: str) -> JobBuilder:
        """Remove an embedded file by key.

        Args:
            key: Attachment key to remove.
        """
        self._spec.setdefault('removeAttachment', []).append(key)
        return self

    # -- Overlay / underlay -------------------------------------------------

    def add_overlay(
        self,
        file: Any,
        *,
        to: str | None = None,
        from_: str | None = None,
        repeat: str | None = None,
        password: str | None = None,
    ) -> JobBuilder:
        """Overlay pages from another file on top of the output pages.

        Args:
            file: Source PDF for the overlay.
            to: Destination page range in the output.
            from_: Source page range in ``file``.
            repeat: Source pages to repeat across remaining destination pages.
            password: Password for an encrypted source file.
        """
        self._spec.setdefault('overlay', []).append(
            _underlay_overlay_entry(file, to, from_, repeat, password)
        )
        return self

    def add_underlay(
        self,
        file: Any,
        *,
        to: str | None = None,
        from_: str | None = None,
        repeat: str | None = None,
        password: str | None = None,
    ) -> JobBuilder:
        """Underlay pages from another file beneath the output pages.

        See :meth:`add_overlay` for argument descriptions.
        """
        self._spec.setdefault('underlay', []).append(
            _underlay_overlay_entry(file, to, from_, repeat, password)
        )
        return self

    # -- Global parser limits ----------------------------------------------

    def limits(
        self,
        *,
        no_default_limits: bool | None = None,
        parser_max_container_size: int | None = None,
        parser_max_container_size_damaged: int | None = None,
        parser_max_errors: int | None = None,
        parser_max_nesting: int | None = None,
        max_stream_filters: int | None = None,
    ) -> JobBuilder:
        """Set global parser limits (useful for hardening against malicious PDFs).

        Args:
            no_default_limits: Disable qpdf's optional default limits.
            parser_max_container_size: Maximum container size while parsing.
            parser_max_container_size_damaged: Maximum container size while
                parsing damaged files.
            parser_max_errors: Maximum number of errors before giving up.
            parser_max_nesting: Maximum object nesting depth.
            max_stream_filters: Maximum number of filters when filtering a stream.
        """
        g: dict[str, str] = self._spec.setdefault('global', {})
        if no_default_limits:
            g['noDefaultLimits'] = _ENABLE
        if parser_max_container_size is not None:
            g['parserMaxContainerSize'] = str(parser_max_container_size)
        if parser_max_container_size_damaged is not None:
            g['parserMaxContainerSizeDamaged'] = str(parser_max_container_size_damaged)
        if parser_max_errors is not None:
            g['parserMaxErrors'] = str(parser_max_errors)
        if parser_max_nesting is not None:
            g['parserMaxNesting'] = str(parser_max_nesting)
        if max_stream_filters is not None:
            g['maxStreamFilters'] = str(max_stream_filters)
        return self

    # -- Escape hatch -------------------------------------------------------

    def set(self, **kwargs: Any) -> JobBuilder:
        """Set arbitrary scalar top-level options not covered by other methods.

        Keyword names are snake_case Python aliases for qpdf's camelCase job
        keys (e.g. ``no_warn`` -> ``noWarn``). A boolean ``True`` enables a
        flag (emitted as an empty string); other values are stringified.

        Args:
            **kwargs: Option names and values.

        Raises:
            ValueError: If a keyword does not correspond to a known option.
        """
        for name, value in kwargs.items():
            try:
                json_key = _KEY_MAP[name]
            except KeyError:
                raise ValueError(f"Unknown job option: {name!r}") from None
            if value is True:
                self._spec[json_key] = _ENABLE
            elif value is False:
                continue
            else:
                self._spec[json_key] = value
        return self

    # -- Serialization / terminals -----------------------------------------

    def to_json(self) -> dict[str, Any]:
        """Return a deep copy of the assembled job specification as a dict."""
        return deepcopy(self._spec)

    def to_json_str(self) -> str:
        """Return the assembled job specification as a JSON string."""
        import json

        return json.dumps(self._spec)

    def build(self) -> Job:
        """Construct a :class:`pikepdf.Job` from the specification.

        The job is validated by qpdf during construction but not executed.

        Raises:
            pikepdf.JobUsageError: If the configuration is semantically invalid.
            RuntimeError: If the JSON is malformed or contains unknown keys.
        """
        return Job(self._spec)

    def run(self, *, validate: bool = True) -> Job:
        """Build and run the job.

        Args:
            validate: If True (default), call ``check_configuration()`` before
                running to fail fast on invalid configurations.

        Returns:
            The :class:`pikepdf.Job` after running, so callers can inspect
            ``exit_code``, ``has_warnings`` and ``encryption_status``.
        """
        job = self.build()
        if validate:
            job.check_configuration()
        job.run()
        return job

    def create_pdf(self) -> Pdf:
        """Build the job and run only its first stage, returning a :class:`pikepdf.Pdf`.

        This is the staged workflow: the returned PDF can be modified before
        calling :meth:`pikepdf.Job.write_pdf` on the same job. Use :meth:`build`
        to retain a reference to the job for the write stage.
        """
        return self.build().create_pdf()

    def __repr__(self) -> str:
        return f'<pikepdf.JobBuilder {self._spec!r}>'


def _underlay_overlay_entry(
    file: Any,
    to: str | None,
    from_: str | None,
    repeat: str | None,
    password: str | None,
) -> dict[str, str]:
    entry: dict[str, str] = {'file': _path(file)}
    if to is not None:
        entry['to'] = to
    if from_ is not None:
        entry['from'] = from_
    if repeat is not None:
        entry['repeat'] = repeat
    if password is not None:
        entry['password'] = password
    return entry


def _encrypt_flags(
    bits: int,
    allow: Permissions,
    *,
    metadata: bool,
    aes: bool | None,
    force_v4: bool,
    allow_insecure: bool,
    force_r5: bool,
) -> dict[str, str]:
    """Translate a :class:`Permissions` grant into qpdf restriction flags.

    pikepdf's :class:`Permissions` is allow-oriented; qpdf's flags are
    restrictions. Every flag is emitted explicitly so the result is fully
    determined by ``allow`` rather than qpdf's defaults.
    """
    flags: dict[str, str] = {}

    # Printing: qpdf takes a single resolution level.
    if not allow.print_lowres:
        flags['print'] = 'none'
    elif not allow.print_highres:
        flags['print'] = 'low'
    else:
        flags['print'] = 'full'

    if bits == 40:
        # The 40-bit (R2) handler only has coarse permission bits.
        flags['extract'] = _yn(allow.extract)
        flags['annotate'] = _yn(allow.modify_annotation)
        if allow.modify_other:
            flags['modify'] = 'all'
        elif allow.modify_form:
            flags['modify'] = 'form'
        elif allow.modify_annotation:
            flags['modify'] = 'annotate'
        elif allow.modify_assembly:
            flags['modify'] = 'assembly'
        else:
            flags['modify'] = 'none'
        return flags

    # 128-bit and 256-bit support granular permissions.
    flags['accessibility'] = _yn(allow.accessibility)
    flags['extract'] = _yn(allow.extract)
    flags['annotate'] = _yn(allow.modify_annotation)
    flags['assemble'] = _yn(allow.modify_assembly)
    flags['form'] = _yn(allow.modify_form)
    flags['modifyOther'] = _yn(allow.modify_other)
    if not metadata:
        flags['cleartextMetadata'] = _ENABLE
    if bits == 128:
        if aes:
            flags['useAes'] = 'y'
        if force_v4:
            flags['forceV4'] = _ENABLE
    elif bits == 256:
        if allow_insecure:
            flags['allowInsecure'] = _ENABLE
        if force_r5:
            flags['forceR5'] = _ENABLE
    return flags
