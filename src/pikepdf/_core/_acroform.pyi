# SPDX-FileCopyrightText: 2022 James R. Barlow
# SPDX-License-Identifier: MPL-2.0

# Type stubs for the bindings in src/core/acroform.cpp.
# See pikepdf/_core/__init__.pyi for how this stub package is laid out.

# pylint: disable=no-method-argument,unused-argument,no-self-use,too-many-public-methods
# ruff: noqa: D418
# mypy: disable-error-code="misc"

from __future__ import annotations

from collections.abc import Sequence
from enum import IntFlag

from pikepdf._core._annotation import Annotation
from pikepdf._core._matrix import Matrix
from pikepdf._core._object import Object, ObjectHelper
from pikepdf._core._object_construct import Dictionary, Name
from pikepdf._core._page import Page
from pikepdf._core._qpdf import Pdf

class FormFieldFlag(IntFlag):
    """Flag values for `pikepdf.AcroFormField.flags`."""

    read_only: ...
    """The field is read-only. Users should not be allowed to change the value of this
    field."""
    required: ...
    """The field is required. Users should be required to submit a value for this field.
    """
    no_export: ...
    """No value should be exported from this field when the user submits the form."""
    btn_no_toggle_off: ...
    """For radio buttons only. Indicates users should no be able to deselect a value,
    and values should only be deselected by selecting another value in the same group.
    (This is the normal, familiar behavior of radio buttons.)"""
    btn_radio: ...
    """Indicates that the button is a radio button."""
    btn_pushbutton: ...
    """Indicates that the button is a pushbutton."""
    btn_radios_in_unison: ...
    """If two radio buttons in this group share the same on-state value, both buttons
    should toggle on or off together."""
    tx_multiline: ...
    """Indicates this is a multiline text field."""
    tx_password: ...
    """Indicates this is a password field."""
    tx_file_select: ...
    """Indicates this is a file upload field."""
    tx_do_not_spell_check: ...
    """Disables spell checking for this text field."""
    tx_do_not_scroll: ...
    """Prevent the text in this field from being scrolled (horizontally or vertically).

    Once the field is full, the field should not accept additional text."""
    tx_comb: ...
    """Divide characters into evenly-spaced "combs", depending on the value of
    ``MaxLen`` in the field dictionary.
    """
    tx_rich_text: ...
    """Indicates this field contains rich text.

    Rich text is entered in an XML-based markup language known as XFA.
    """
    ch_combo: ...
    """Indicates this field is a combo-box. Otherwise, it will be a list box."""
    ch_edit: ...
    """Also allow entry of free-text values into this choice field.

    The ``ch_combo`` flag must also be set.
    """
    ch_sort: ...
    """Request that options be sorted alphabetically.

    You should check this flag when inserting new options into this choice field. It
    does not effect how the form displays to the user.
    """
    ch_multi_select: ...
    """Allow multiple selections."""
    ch_do_not_spell_check: ...
    """Disables spell checking for free-text values in this choice field.

    The ``edit`` flag must be set for this to have any effect.
    """
    ch_commit_on_sel_change: ...
    """Indicates that the new value should be committed immediately upon selection. If
    this is not set, the value will not be committed until the user moves on to the next
    field."""

class AcroFormField(ObjectHelper):
    """An AcroForm field. Wrapper around a PDF dictionary."""
    @property
    def is_null(self) -> bool:
        """True if the field is null."""
    @property
    def parent(self) -> AcroFormField:
        """This field's parent.

        If there is no parent, a AcroFormField where ``field.is_null is True`` is
        returned.
        """
    @property
    def top_level_field(self) -> AcroFormField:
        """The top-level field for this field.

        This will be the field itself, or one of its ancestors (often the
        immediate parent).

        Note that the top-level field may not itself be a "real" field. Fields
        may be nested underneath one another at any arbitrary level, with the
        outer fields forming groups or sets of fields. This property references
        the highest field in this field's hierarchy.
        """
    def get_inheritable_field_value(self, name: str):
        """Get field value, possibly inheriting the value from ancestor node."""
    def get_inheritable_field_value_as_string(self, name: str) -> str:
        """Get an inherited field value as a string.

        If the value is not a string, this property will hold an empty string.
        """
    def get_inheritable_field_value_as_name(self, name: str) -> Name:
        """Get an inherited field value as a Name object.

        If the value is not a name, this property will hold an empty name.
        """
    @property
    def field_type(self) -> str:
        """The raw value of /FT if present, otherwise an empty string."""
    @property
    def fully_qualified_name(self) -> str:
        """The field's fully qualified name.

        This is defined as being the /T (partial_name) value of this and all
        ancestors, concatenated together with dots.
        """
    @property
    def partial_name(self) -> str:
        """The field's partial name (/T)."""
    @property
    def alternate_name(self) -> str:
        """The alternative field name (/TU), the field name presented to users.

        If a value is not present in the underlying field, this property falls
        back to the fully qualified name.
        """
    @property
    def mapping_name(self) -> str:
        """Return the mapping field name (/TM).

        If a value is not present in the underlying field, this property falls
        back to the fully qualified name.
        """
    @property
    def value(self):
        """The current value of the form field."""
    @property
    def value_as_string(self) -> str:
        """The field's value as a string.

        If the value is not a string, this property will hold an empty string.
        """
    @property
    def default_value(self):
        """The default value of the form field."""
    @property
    def default_value_as_string(self) -> str:
        """The field's default value as a string.

        If the value is not a string, this property will hold an empty string.
        """
    @property
    def default_appearance(self) -> bytes:
        """Default appearance string, inheriting from ancestor fields if needed.

        This property will contain and empty string if the default appearance
        string is not available (because it's erroneously absent or because
        this is not a variable text field). If not found in the field
        hierarchy, look in /AcroForm.
        """
    @property
    def default_resources(self) -> Dictionary:
        """The default resource dictionary for the field.

        This comes not from the field but from the document-level /AcroForm
        dictionary. While several PDF generates put a /DR key in the form
        field's dictionary, experimentation suggests that many popular
        readers, including Adobe Acrobat and Acrobat Reader, ignore any /DR
        item on the field.
        """
    @property
    def quadding(self) -> int:
        """The quadding value, inheriting from ancestor fields if needed.

        This will be 0 if the quadding is not specified. Look in /AcroForm if
        not found in the field hierarchy.
        """
    @property
    def flags(self) -> int:
        """Field flags from /Ff."""
    @property
    def is_text(self) -> bool:
        """True if field is of type /Tx."""
    @property
    def is_checkbox(self) -> bool:
        """True if field is type /Btn and flags do not indicate other type of button."""
    @property
    def is_checked(self) -> bool:
        """True if field is a checkbox and is checked."""
    @property
    def is_radio_button(self) -> bool:
        """True if field is of type /Btn and flags indicate that a radio button."""
    @property
    def is_pushbutton(self) -> bool:
        """True if field is of type /Btn and flags indicate that a pushbutton."""
    @property
    def is_choice(self) -> bool:
        """True if fields if of type /Ch."""
    @property
    def choices(self) -> Sequence[str]:
        """Available choices for this field, if this is a choice field.

        This does not contain choices for radio buttons. For radio buttons,
        traverse the /Kids of the top-level field and inspect the individual
        buttons.

        This also only works for choice fields where the options are
        represented as an array of strings. However, some PDFs represent
        choices as an array of ``[export_value, display_value]`` pairs. This
        is a limitation of the underlying QPDF library.
        See `QPDF Issue 1433 <https://github.com/qpdf/qpdf/issues/1433>`_.
        To get options for such fields, use `field.obj.Opt` instead.
        """
    def set_value(self, value, need_appearance: bool = True):
        """Set the ``value`` property.

        If ``need_appearance`` is true, and this is a text or choice field, the
        ``pikepdf.AcroForm.needs_appearances`` will also be set.
        """
    def generate_appearance(self, annot: Annotation):
        """Generate an appearance stream for this field."""

class AcroForm:
    """A helper for working with PDF interactive forms."""
    @property
    def exists(self) -> bool:
        """True if the current document has an interactive form."""
    def add_field(self, field: AcroFormField):
        """Add a form field.

        Initializes the document's AcroForm dictionary if needed, and
        updates the cache if necessary.

        Note that you are adding fields that are copies of other fields, this
        method may result in multiple fields existing with the same qualified
        name, which can have unexpected side effects. In that case, you should
        use ``add_and_rename_fields()`` instead.
        """
    def add_and_rename_fields(self, fields: Sequence[AcroFormField]):
        """Add a collection of form fields.

        Ensures that their fully qualified names don't conflict with
        already present form fields.

        Fields within the collection of new fields that have the same name as
        each other will continue to do so.
        """
    def remove_fields(self, fields: Sequence[AcroFormField]):
        """Remove fields from the ``fields`` list."""
    def set_field_name(self, field: AcroFormField, name: str):
        """Set partial name of a field, updating internal records of field names."""
    @property
    def fields(self) -> Sequence[AcroFormField]:
        """A list of all terminal fields in this interactive form.

        Terminal fields are fields that have no children that are also fields.
        Terminal fields should have children that are annotations, or be
        annotations themselves. Only terminal fields are displayed as actual
        widgets in the PDF document; non-terminal fields exist only for
        grouping.

        Intermediate nodes in the fields tree are not included in this list,
        but you can still reach them through the `pikepdf.AcroFormField.parent`
        and `pikepdf.AcroFormField.top_level_field`` properties.
        """
    def get_fields_with_qualified_name(self, name: str) -> Sequence[AcroFormField]:
        """Get a list of all fields with the given qualified name.

        Generally, this list will contain only one member, as having multiple
        fields with the same name is discouraged (but not impossible).

        This will only return elements that have an explicit name (/T) in the
        field dictionary. In practice, this means that it should return the
        highest-level matching field, but not any children. (For example, this
        method will return a radio group rather than individual radio buttons.)
        """
    def get_annotations_for_field(self, field: AcroFormField) -> Sequence[Annotation]:
        """Given a form field, return the associated annotation(s).

        Typically, interactive forms store field information and annotation
        information in the same dictionary, meaning this method will often
        return a single `pikepdf.Annotation` which refers to the same
        underlying `pikepdf.Dictionary`. However, this is not necessarily always
        the case and should not be relied on. A field may store annotation data
        in its own dictionary, and may even have multiple annotations.
        """
    def get_widget_annotations_for_page(self, page: Page) -> Sequence[Annotation]:
        """Find all the interactive form widgets on a page.

        In many PDFs, you may find that this returns a list that perfectly
        corresponds to that returned by ``get_form_fields_for_page``. However,
        you should not rely on this behavior. This will not always be the case.
        Use this method to get the annotations, then use the
        ``get_field_for_annotation`` method for each to get the corresponding
        field.
        """
    def get_form_fields_for_page(self, page: Page) -> Sequence[AcroFormField]:
        """Find all the interactive form fields on a page.

        In many PDFs, you may find that this returns a list that perfectly
        corresponds to that returned by ``get_widget_annotations_for_page``.
        However, you should not rely on this behavior. This will not always be
        the case. Use this method to get all the fields, then use the
        ``get_annotations_for_field`` method for each to get the corresponding
        annotations.
        """
    def get_field_for_annotation(self, annotation: Annotation) -> AcroFormField:
        """Given an annotation for a widget, return the associated form field.

        Typically, interactive forms store field information and annotation
        information in the same dictionary, meaning this method will often
        return a `pikepdf.AcroFormField` which refers to the same underlying
        `pikepdf.Dictionary`. However, this is not necessarily always
        the case and should not be relied on. A field may store annotation data
        in its own dictionary.
        """
    @property
    def needs_appearances(self) -> bool:
        """Indicates whether appearance streams must be regenerated.

        This should be set to True if you modify any field values in the
        interactive form, unless you also generate the appearance streams for
        the modified fields.
        """
    def generate_appearances_if_needed(self) -> None:
        """Generate appearance streams for all form fields that need them.

        For checkbox and radio button fields, this method ensures that
        appearance state is consistent with the field's value and uses any
        pre-existing appearance streams.

        If ``needs_appearances`` is False, this method does nothing.

        This method uses the underlying QPDF implementation, which has several
        limitations:

         * Only supports ASCII characters in text fields
         * Does not support multi-line text
         * Ignores quadding (alignment)
        """
    def disable_digital_signatures(self) -> None:
        """Disables digital signature fields.

        This method removes all digital signature fields from the document,
        leaving any annotation showing the content of the field intact.
        """
    def fix_copied_annotations(
        self,
        to_page: Page,
        from_page: Page,
        from_acroform: AcroForm,
    ) -> Sequence[AcroFormField]:
        """Copy form fields and annotations from one page to another.

        This would typically be called after copying a new page in order to add
        field/annotation awareness. When just copying the page by itself,
        annotations end up being shared, and fields end up being omitted
        because there is no reference to the field from the page. This method
        ensures that each separate copy of a page has private annotations and
        that fields and annotations are properly updated to resolve conflicts
        that may occur from common resource and field names across documents.

        Args:
            to_page: The page to copy to.
            from_page: The page to copy from. May be in a different PDF or in
                the same PDF.
            from_acroform: The acroform object for the source PDF.

        Returns a list of newly created fields.
        """
    def validate(self, repair: bool = ...) -> None:
        """Re-validate the AcroForm structure.

        Useful if you have modified the structure of the AcroForm dictionary in
        a way that would invalidate the internal cache.

        Args:
            repair: If True (default), the document will be repaired if possible
                when validation encounters errors.

        .. versionadded:: 10.9
        """
    def invalidate_cache(self) -> None:
        """Mark the internal field/annotation/page cache invalid.

        This class lazily caches the mapping among form fields, annotations, and
        pages. If you modify pages' annotation dictionaries, the /AcroForm
        dictionary, or form fields manually in a way that alters these
        associations, call this to force the cache to be regenerated.

        .. versionadded:: 10.9
        """
    def transform_annotations(
        self,
        old_annots: Object,
        matrix: Matrix = ...,
        from_qpdf: Pdf | None = ...,
        from_acroform: AcroForm | None = ...,
    ) -> tuple[list[Object], list[Object], list[tuple[int, int]]]:
        """Transform a set of annotations by a matrix, copying form fields.

        This is the low-level primitive underlying
        :meth:`pikepdf.Page.copy_annotations`.
        For each annotation in ``old_annots``, a new annotation is created with
        the matrix applied to its rectangle. If an annotation is associated with
        a form field, a new form field pointing at the new annotation is created.
        The new annotations and fields are *not* added to any page or to the
        document; the caller must do that.

        Args:
            old_annots: An array of annotations to transform. May belong to a
                different ``Pdf``, in which case pass ``from_qpdf``.
            matrix: The transformation matrix. Defaults to the identity matrix.
            from_qpdf: The source ``Pdf`` if ``old_annots`` is foreign.
            from_acroform: An optional source AcroForm, for efficiency when
                copying many annotations from the same source document.

        Returns:
            A tuple ``(new_annots, new_fields, old_fields)`` where ``new_annots``
            and ``new_fields`` are lists of newly created objects, and
            ``old_fields`` is a list of ``(object_number, generation)`` for the
            source fields that were transformed.

        .. versionadded:: 10.9
        """
