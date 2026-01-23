# SPDX-FileCopyrightText: 2022 James R. Barlow
# SPDX-License-Identifier: MPL-2.0

"""PdfMetadata - facade for XMP and DocumentInfo metadata."""

from __future__ import annotations

import logging
from collections.abc import Iterator, MutableMapping
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any
from warnings import warn

from pikepdf._version import __version__ as pikepdf_version
from pikepdf.models.metadata._constants import (
    XMP_NS_PDF,
    XMP_NS_PDFA_ID,
    XMP_NS_PDFX_ID,
    XMP_NS_XMP,
    clean,
)
from pikepdf.models.metadata._converters import DOCINFO_MAPPING, DocinfoMapping
from pikepdf.models.metadata._docinfo import DocinfoStore
from pikepdf.models.metadata._xmp import XmpDocument
from pikepdf.objects import Name, Stream

if TYPE_CHECKING:  # pragma: no cover
    from lxml.etree import QName

    from pikepdf import Pdf


log = logging.getLogger(__name__)


class PdfMetadata(MutableMapping):
    """Read and edit the metadata associated with a PDF.

    The PDF specification contain two types of metadata, the newer XMP
    (Extensible Metadata Platform, XML-based) and older DocumentInformation
    dictionary. The PDF 2.0 specification removes the DocumentInformation
    dictionary.

    This primarily works with XMP metadata, but includes methods to generate
    XMP from DocumentInformation and will also coordinate updates to
    DocumentInformation so that the two are kept consistent.

    XMP metadata fields may be accessed using the full XML namespace URI or
    the short name. For example ``metadata['dc:description']``
    and ``metadata['{http://purl.org/dc/elements/1.1/}description']``
    both refer to the same field. Several common XML namespaces are registered
    automatically.

    See the XMP specification for details of allowable fields.

    To update metadata, use a with block.

    Example:
        >>> with pdf.open_metadata() as records:
        ...     records['dc:title'] = 'New Title'

    See Also:
        :meth:`pikepdf.Pdf.open_metadata`
    """

    # Keep DOCINFO_MAPPING at class level for backward compatibility
    DOCINFO_MAPPING: list[DocinfoMapping] = DOCINFO_MAPPING

    # Delegate namespace dicts to XmpDocument for backward compatibility
    NS: dict[str, str] = XmpDocument.NS
    REVERSE_NS: dict[str, str] = XmpDocument.REVERSE_NS

    def __init__(
        self,
        pdf: Pdf,
        pikepdf_mark: bool = True,
        sync_docinfo: bool = True,
        overwrite_invalid_xml: bool = True,
    ):
        """Construct PdfMetadata. Use Pdf.open_metadata() instead."""
        self._pdf = pdf
        self.mark = pikepdf_mark
        self.sync_docinfo = sync_docinfo
        self._updating = False
        self._overwrite_invalid_xml = overwrite_invalid_xml

        # Initialize XmpDocument with PDF's XMP data
        self._xmp_doc = self._load_xmp()

        # Initialize DocinfoStore
        self._docinfo = DocinfoStore(pdf)

    def _load_xmp(self) -> XmpDocument:
        """Load XMP from PDF or create empty XmpDocument."""
        try:
            data = self._pdf.Root.Metadata.read_bytes()
        except AttributeError:
            data = b''

        return XmpDocument(
            data, overwrite_invalid_xml=self._overwrite_invalid_xml
        )

    def load_from_docinfo(
        self, docinfo, delete_missing: bool = False, raise_failure: bool = False
    ) -> None:
        """Populate the XMP metadata object with DocumentInfo.

        Arguments:
            docinfo: a DocumentInfo, e.g pdf.docinfo
            delete_missing: if the entry is not DocumentInfo, delete the equivalent
                from XMP
            raise_failure: if True, raise any failure to convert docinfo;
                otherwise warn and continue

        A few entries in the deprecated DocumentInfo dictionary are considered
        approximately equivalent to certain XMP records. This method copies
        those entries into the XMP metadata.
        """
        from lxml.etree import QName

        def warn_or_raise(msg, e=None):
            if raise_failure:
                raise ValueError(msg) from e
            warn(msg)

        for uri, shortkey, docinfo_name, converter in self.DOCINFO_MAPPING:
            qname = QName(uri, shortkey)
            # docinfo might be a dict or pikepdf.Dictionary, so lookup keys
            # by str(Name)
            val = docinfo.get(str(docinfo_name))
            if val is None:
                if delete_missing and qname in self:
                    del self[qname]
                continue
            try:
                val = str(val)
                if converter:
                    val = converter.xmp_from_docinfo(val)
                if not val:
                    continue
                self._setitem(qname, val, True)
            except (ValueError, AttributeError, NotImplementedError) as e:
                warn_or_raise(
                    f"The metadata field {docinfo_name} could not be copied to XMP", e
                )
        valid_docinfo_names = {
            str(docinfo_name) for _, _, docinfo_name, _ in self.DOCINFO_MAPPING
        }
        extra_docinfo_names = {str(k) for k in docinfo.keys()} - valid_docinfo_names
        for extra in extra_docinfo_names:
            warn_or_raise(
                f"The metadata field {extra} with value '{repr(docinfo.get(extra))}' "
                "has no XMP equivalent, so it was discarded",
            )

    def __enter__(self):
        """Open metadata for editing."""
        self._updating = True
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Close metadata and apply changes."""
        try:
            if exc_type is not None:
                return
            self._apply_changes()
        finally:
            self._updating = False

    def _update_docinfo(self):
        """Update the PDF's DocumentInfo dictionary to match XMP metadata.

        The standard mapping is described here:
            https://www.pdfa.org/pdfa-metadata-xmp-rdf-dublin-core/
        """
        from lxml.etree import QName

        # Touch object to ensure it exists
        self._pdf.docinfo  # pylint: disable=pointless-statement
        for uri, element, docinfo_name, converter in self.DOCINFO_MAPPING:
            qname = QName(uri, element)
            try:
                value = self[qname]
            except KeyError:
                if docinfo_name in self._pdf.docinfo:
                    del self._pdf.docinfo[docinfo_name]
                continue
            if converter:
                try:
                    value = converter.docinfo_from_xmp(value)
                except ValueError:
                    warn(
                        f"The DocumentInfo field {docinfo_name} could not be "
                        "updated from XMP"
                    )
                    value = None
                except Exception as e:
                    raise ValueError(
                        "An error occurred while updating DocumentInfo field "
                        f"{docinfo_name} from XMP {qname} with value {value}"
                    ) from e
            if value is None:
                if docinfo_name in self._pdf.docinfo:
                    del self._pdf.docinfo[docinfo_name]
                continue
            self._docinfo.set(docinfo_name, clean(value))

    def _apply_changes(self):
        """Serialize our changes back to the PDF in memory.

        Depending how we are initialized, leave our metadata mark and producer.
        """
        from lxml.etree import QName

        if self.mark:
            # We were asked to mark the file as being edited by pikepdf
            self._setitem(
                QName(XMP_NS_XMP, 'MetadataDate'),
                datetime.now(timezone.utc).isoformat(),
                applying_mark=True,
            )
            self._setitem(
                QName(XMP_NS_PDF, 'Producer'),
                'pikepdf ' + pikepdf_version,
                applying_mark=True,
            )
        xml = self._xmp_doc.to_bytes()
        self._pdf.Root.Metadata = Stream(self._pdf, xml)
        self._pdf.Root.Metadata[Name.Type] = Name.Metadata
        self._pdf.Root.Metadata[Name.Subtype] = Name.XML
        if self.sync_docinfo:
            self._update_docinfo()

    @classmethod
    def _qname(cls, name: QName | str) -> str:
        """Convert name to an XML QName.

        e.g. pdf:Producer -> {http://ns.adobe.com/pdf/1.3/}Producer
        """
        return XmpDocument.qname(name)

    @classmethod
    def register_xml_namespace(cls, uri: str, prefix: str) -> None:
        """Register a new XML/XMP namespace.

        Arguments:
            uri: The long form of the namespace.
            prefix: The alias to use when interpreting XMP.
        """
        XmpDocument.register_xml_namespace(uri, prefix)

    def _prefix_from_uri(self, uriname: str) -> str:
        """Given a fully qualified XML name, find a prefix.

        e.g. {http://ns.adobe.com/pdf/1.3/}Producer -> pdf:Producer
        """
        return self._xmp_doc.prefix_from_uri(uriname)

    def __contains__(self, key: object) -> bool:  # type: ignore[override]
        """Test if XMP key is in metadata."""
        from lxml.etree import QName

        if not isinstance(key, (str, QName)):
            raise TypeError(f"{key!r} must be str or QName")
        return key in self._xmp_doc

    def __getitem__(self, key: str | QName) -> Any:
        """Retrieve XMP metadata for key."""
        return self._xmp_doc[key]

    def __iter__(self) -> Iterator[str]:
        """Iterate through XMP metadata attributes and nodes."""
        return iter(self._xmp_doc)

    def __len__(self) -> int:
        """Return number of items in metadata."""
        return len(self._xmp_doc)

    def _setitem(
        self,
        key: str | QName,
        val: set[str] | list[str] | str,
        applying_mark: bool = False,
    ) -> None:
        if not self._updating:
            raise RuntimeError("Metadata not opened for editing, use with block")

        qkey = self._qname(key)
        self._setitem_check_args(key, val, applying_mark, qkey)
        self._xmp_doc.set_value(key, val)

    def _setitem_check_args(
        self, key: str | QName, val: Any, applying_mark: bool, qkey: str
    ) -> None:
        if (
            self.mark
            and not applying_mark
            and qkey
            in (
                self._qname('xmp:MetadataDate'),
                self._qname('pdf:Producer'),
            )
        ):
            # Complain if user writes self[pdf:Producer] = ... and because it will
            # be overwritten on save, unless self._updating_mark, in which case
            # the action was initiated internally
            log.warning(
                f"Update to {key} will be overwritten because metadata was opened "
                "with set_pikepdf_as_editor=True"
            )
        if isinstance(val, str) and qkey in (self._qname('dc:creator')):
            log.error(f"{key} should be set to a list of strings")

    def __setitem__(self, key: str | QName, val: set[str] | list[str] | str) -> None:
        """Set XMP metadata key to value."""
        return self._setitem(key, val, False)

    def __delitem__(self, key: str | QName) -> None:
        """Delete item from XMP metadata."""
        if not self._updating:
            raise RuntimeError("Metadata not opened for editing, use with block")
        del self._xmp_doc[key]

    @property
    def pdfa_status(self) -> str:
        """Return the PDF/A conformance level claimed by this PDF, or False.

        A PDF may claim to PDF/A compliant without this being true. Use an
        independent verifier such as veraPDF to test if a PDF is truly
        conformant.

        Returns:
            The conformance level of the PDF/A, or an empty string if the
            PDF does not claim PDF/A conformance. Possible valid values
            are: 1A, 1B, 2A, 2B, 2U, 3A, 3B, 3U. Note that ISO standard
            typically refers to PDF/A-1b for example, using lower case;
            this function returns the value as it appears in the PDF, which
            is uppercase.
        """
        from lxml.etree import QName

        key_part = QName(XMP_NS_PDFA_ID, 'part')
        key_conformance = QName(XMP_NS_PDFA_ID, 'conformance')
        try:
            return self[key_part] + self[key_conformance]
        except KeyError:
            return ''

    @property
    def pdfx_status(self) -> str:
        """Return the PDF/X conformance level claimed by this PDF, or False.

        A PDF may claim to PDF/X compliant without this being true. Use an
        independent verifier such as veraPDF to test if a PDF is truly
        conformant.

        Returns:
            The conformance level of the PDF/X, or an empty string if the
            PDF does not claim PDF/X conformance.
        """
        from lxml.etree import QName

        pdfx_version = QName(XMP_NS_PDFX_ID, 'GTS_PDFXVersion')
        try:
            return self[pdfx_version]
        except KeyError:
            return ''

    def __str__(self) -> str:
        """Convert XMP metadata to XML string."""
        return str(self._xmp_doc)

    # Backward compatibility methods for internal API access
    def _load(self) -> None:
        """No-op for backward compatibility.

        Previously this triggered lazy loading of XMP. Now XMP is loaded
        immediately in __init__.
        """
        pass

    def _get_rdf_root(self):
        """Get the rdf:RDF root element.

        Provided for backward compatibility with code that accesses
        internal XMP structure.
        """
        return self._xmp_doc._get_rdf_root()

    def _get_xml_bytes(self, xpacket: bool = True) -> bytes:
        """Serialize XMP to XML bytes.

        Provided for backward compatibility.
        """
        return self._xmp_doc.to_bytes(xpacket=xpacket)
