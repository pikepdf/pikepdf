# SPDX-FileCopyrightText: 2025 Dominick Johnson
# SPDX-License-Identifier: MPL-2.0

"""Support for working with interactive forms."""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from collections.abc import Generator, Mapping, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from decimal import Decimal

from pikepdf import (
    AcroForm,
    AcroFormField,
    Array,
    Dictionary,
    FormFieldFlag,
    Matrix,
    Name,
    Object,
    Operator,
    Page,
    Pdf,
    Rectangle,
    String,
    parse_content_stream,
)
from pikepdf.canvas import ContentStreamBuilder, SimpleFont

log = logging.getLogger(__name__)


class Form:
    """Utility class to make it easier to work with interactive forms.

    This is easier to use than the core {class}`pikepdf.AcroForm` implementation, but is
    higher-level, and abstracts over details in ways which do impose some limitations,
    such as failing for PDFs which have multiple fields with the same name.

    A non-exhaustive list of limitations:

    * No support for signatures
    * No support for password fields
    * No support for rich text fields
    * Multiselect choice fields are treated as single-select
    * Generating appearance streams imposes additional limitations (see
      {class}`pikepdf.form.DefaultAppearanceStreamGenerator` and
      {class}`pikepdf.form.ExtendedAppearanceStreamGenerator` for details.)
    """

    generate_appearances: AppearanceStreamGenerator | None = None
    """If provided, this object will be used to generate appearance streams for fields
    as the form is filled. If not, the `needs_appearances` flag will be set on the form.
    """
    ignore_max_length: bool
    """If True, we will ignore the MaxLen property of any text fields in this form. This
    produces a PDF that would typically not be possible to create in an interactive PDF
    reader, but this may be desirable or useful if the PDF is intended to be read by
    another automated system rather than a human.
    """
    _pdf: Pdf
    _acroform: AcroForm
    _cache: Mapping[str, _FieldWrapper]

    def __init__(
        self,
        pdf: Pdf,
        generate_appearances: type[AppearanceStreamGenerator] | None = None,
        *,
        ignore_max_length=False,
    ):
        """Initialize the form."""
        self._pdf = pdf
        self._acroform = pdf.acroform
        self._cache = {}
        if generate_appearances is not None:
            self.generate_appearances = generate_appearances(self._pdf, self._acroform)
        self.ignore_max_length = ignore_max_length

    def __getattr__(self, name):
        return getattr(self._acroform, name)

    def __getitem__(self, name: str):
        if name in self._cache:
            return self._cache[name]
        fields = self._acroform.get_fields_with_qualified_name(name)
        if not fields:
            raise KeyError(name)
        if len(fields) > 1:
            raise RuntimeError(f'Multiple fields with same name: {name}')
        return self._wrap(fields[0], name)

    def __contains__(self, name: str):
        try:
            self.__getitem__(name)
            return True
        except KeyError:
            return False

    def items(self) -> Generator[tuple[str, _FieldWrapper]]:
        """Yield (name, field) pairs for all fields in this form."""
        seen = set()
        for field in self._acroform.fields:
            name = field.fully_qualified_name
            if name in self._cache and name not in seen:
                seen.add(name)
                yield name, self._cache[name]
            elif (
                name in self._cache
                and field.is_radio_button
                and field.parent == self._cache[name]._field
            ):
                # We already returned the parent of this radio button
                continue
            elif name in self._cache:
                raise RuntimeError(f'Multiple fields with same name: {name}')
            elif field.is_radio_button:
                # QPDF does something here which is perhaps not entirely correct by the
                # spec, and which causes issues. By the spec, a radio button group is a
                # single field with multiple widget annotations in the Kids array. (See
                # 12.7.5.2.4 of the 2.0 spec) However, QPDF here treats is as a group
                # containing separate terminal fields for each button, each inheriting
                # the same name. Fortunately, the implementation of
                # `get_fields_with_qualified_name` seems to be correct, so we'll fall
                # back to using that.
                fields = self._acroform.get_fields_with_qualified_name(name)
                if len(fields) > 1:
                    raise RuntimeError(f'Multiple fields with same name: {name}')
                seen.add(name)
                yield name, self._wrap(fields[0], name)
            else:
                seen.add(name)
                yield name, self._wrap(field, name)

    def __iter__(self):
        for name, item in self.items():
            yield item

    def _wrap(self, field: AcroFormField, name: str):
        if field.is_text:
            wrapped = TextField(self, field)
        elif field.is_checkbox:
            wrapped = CheckboxField(self, field)
        elif field.is_radio_button:
            wrapped = RadioButtonGroup(self, field)
        elif field.is_pushbutton:
            wrapped = PushbuttonField(self, field)
        elif field.is_choice:
            wrapped = ChoiceField(self, field)
        elif field.field_type == Name.Sig:
            wrapped = SignatureField(self, field)
        else:
            raise RuntimeError('Unknown field type')
        self._cache[name] = wrapped
        return wrapped


class _FieldWrapper:
    """Base class for other field types.

    In addition to the methods and properties documented here, all fields expose the
    same properties and methods defined on `pikepdf.AcroFormField`. These are forwarded
    to the underlying field object.
    """

    def __init__(self, form: Form, field: AcroFormField):
        self._form = form
        self._field = field

    def __getattr__(self, name):
        return getattr(self._field, name)

    @property
    def is_required(self) -> bool:
        """Is this a required field?"""
        return bool(self._field.flags & FormFieldFlag.required)

    @property
    def is_read_only(self) -> bool:
        """Is this a read-only field?"""
        return bool(self._field.flags & FormFieldFlag.read_only)

    @property
    def export_enabled(self) -> bool:
        """Should this field's value be included when exporting data from the PDF?"""
        return not self._field.flags & FormFieldFlag.no_export


class TextField(_FieldWrapper):
    """Represents an editable text field."""

    @property
    def is_multiline(self) -> bool:
        """Is this a multiline text field?

        If True, text will be wrapped and newlines will be allowed. If False, text will
        not be wrapped and newlines are stripped.
        """
        return bool(self._field.flags & FormFieldFlag.tx_multiline)

    @property
    def is_combed(self) -> bool:
        """Is this a combed text field?

        If True, the field will be split into equal-length segments, based on
        ``max_length``, containing one character each.
        """
        return bool(self._field.flags & FormFieldFlag.tx_comb)

    @property
    def is_rich_text(self) -> bool:
        """Is this a rich text field?

        Rich text functionality is not currently implemented, but this flag is presented
        for your information.
        """
        return bool(self._field.flags & FormFieldFlag.tx_rich_text)

    @property
    def is_password(self) -> bool:
        """Is this a password field?

        Password fields are not currently implemented, but this flag is presented for
        your information.
        """
        return bool(self._field.flags & FormFieldFlag.tx_password)

    @property
    def is_file_select(self) -> bool:
        """Is this a file select field?

        File select fields are not currently implemented, but this flag is presented for
        your information.
        """
        return bool(self._field.flags & FormFieldFlag.tx_file_select)

    @property
    def spell_check_enabled(self) -> bool:
        """Should spell-checking be enabled in this field?"""
        return not self._field.flags & FormFieldFlag.tx_do_not_spell_check

    @property
    def scrolling_enabled(self) -> bool:
        """Should scrolling (horizontal or vertical) be allowed in this field?"""
        return not self._field.flags & FormFieldFlag.tx_do_not_scroll

    @property
    def max_length(self) -> int | None:
        """The maximum length of the text in this field."""
        return self._field.get_inheritable_field_value("/MaxLen")

    @property
    def default_value(self) -> str:
        """The default (placeholder) value of the text field."""
        return self._field.default_value_as_string

    @property
    def value(self) -> str:
        """The value of the text field."""
        return self._field.value_as_string

    @value.setter
    def value(self, value: str):
        # Coerce the value into something acceptable if it isn't
        if not self.is_multiline:
            value = value.replace('\n', '')
        max_length = self.max_length
        if (
            not self._form.ignore_max_length
            and max_length is not None
            and len(value) > max_length
        ):
            value = value[:max_length]
            log.warning('Value is too long for text field and is being truncated')
        # Set the value
        self._field.set_value(value, self._form.generate_appearances is None)
        # Generate appearance streams if requested.
        if self._form.generate_appearances is not None:
            self._form.generate_appearances.generate_text(self._field)


class CheckboxField(_FieldWrapper):
    """Represents a checkbox field."""

    @property
    def states(self) -> Sequence[Name]:
        """List the possible states for this checkbox.

        Typically this will be /Off plus one additional arbitrary value representing the
        on state.
        """
        return tuple(Name(key) for key in self._field.obj.AP.N.keys())

    @property
    def on_value(self) -> Name:
        """The underlying value associated with this checkbox's "on" state."""
        for name in self._field.obj.AP.N.keys():
            if name != Name.Off:
                return Name(name)

    @property
    def value(self) -> Name | None:
        """The actual current stored value of this checkbox."""
        return self._field.value

    @property
    def checked(self) -> bool:
        """Is this checkbox checked?"""
        return self._field.is_checked

    @checked.setter
    def checked(self, checked: bool):
        if checked:
            states = set(self._field.obj.AP.N.keys())
            states.discard(Name.Off)
            self._field.set_value(Name(states.pop()))
        else:
            self._field.set_value(Name.Off)
        # Appearance stream generation not needed for checkboxes, and QDPF already sets
        # /AS when it sets /V, so no further action needed


class RadioButtonGroup(_FieldWrapper):
    """Represents a radio button group."""

    @property
    def can_toggle_off(self):
        """If radio buttons in this group are allowed to be togged off."""
        return not self._field.flags & FormFieldFlag.btn_no_toggle_off

    @property
    def states(self) -> Sequence[Name]:
        """List the possible on states of all component radio buttons in this group."""
        if Name.Kids not in self._field.obj:
            return ()
        states = set()
        for kid in self._field.obj.Kids:
            states.update(kid.AP.N.keys())
        states.discard(Name.Off)
        return tuple(Name(state) for state in states)

    @property
    def options(self) -> Sequence[RadioButtonOption]:
        """A list of all available options."""
        if Name.Kids not in self._field.obj:
            return ()
        return tuple(
            RadioButtonOption(self, kid, index)
            for index, kid in enumerate(self._field.obj.Kids)
        )

    @property
    def value(self) -> Name | None:
        """The value of the currently selected option."""
        return self._field.value

    @value.setter
    def value(self, value: Name):
        if value == Name.Off and not self.can_toggle_off:
            raise ValueError('To uncheck a radio button, check another.')
        if self._field.parent is None:
            self._field.set_value(value)
            # Appearance stream generation not needed for radio buttons, and QDPF
            # already sets /AS for all children when it sets /V for the parent, so no
            # further action needed.
        else:
            # This is a workaround for https://github.com/qpdf/qpdf/issues/1449 and can
            # be removed once a fix for that issue is broadly available in QPDF. We
            # should be able to already assume we are a terminal field, because of how
            # the Form class above works, so all the checks QPDF does should be
            # unneeded.
            self._field.obj.V = value
            for kid in self._field.obj.Kids:
                # Set appearance streams for children (individual radio buttons)
                states = set(kid.AP.N.keys())
                if value in states:
                    kid.AS = value
                elif '/AS' in kid:
                    kid.AS = Name.Off

    @property
    def selected(self) -> RadioButtonOption | None:
        """The currently selected option."""
        value = self._field.value
        if value is None or value == Name.Off:
            return None
        if Name.Kids not in self._field.obj:
            return None
        for index, kid in enumerate(self._field.obj.Kids):
            if value in kid.AP.N:
                return RadioButtonOption(self, kid, index)
        log.warning('Radio button group value does not match any radio buttons')
        return None

    @selected.setter
    def selected(self, option: RadioButtonOption):
        if option._group is not self:
            raise ValueError('Option does not belong to this group')
        self.value = option.on_value


class RadioButtonOption:
    """Represents a single radio button in a radio button group."""

    _group: RadioButtonGroup
    _annot_dict: Dictionary

    def __init__(self, group: RadioButtonGroup, annot_dict: Dictionary, index: int):
        """Create a new option for a radio button group."""
        self._group = group
        self._annot_dict = annot_dict
        self._index = index

    @property
    def states(self) -> Sequence[Name]:
        """List the possible states for this radio button.

        Typically this will be /Off plus one additional arbitrary value representing the
        on state.
        """
        return (Name(key) for key in self._field.obj.AP.N.keys())

    @property
    def on_value(self) -> Name:
        """The underlying value associated with this button's "on" state."""
        for name in self._annot_dict.AP.N.keys():
            if name != Name.Off:
                return Name(name)

    def select(self):
        """Mark this as the selected option."""
        self._group.value = self.on_value

    @property
    def checked(self) -> bool:
        """Is this is the currently selected option?"""
        return self.on_value == self._group.value

    @checked.setter
    def checked(self, value: bool):
        if value:
            self._group.value = self.on_value
        else:
            self._group.value = Name.Off


class PushbuttonField(_FieldWrapper):
    """Represents a pushbutton field.

    Pushbuttons retain no permanent state, so this class is merely a placeholder. It
    exposes no functionality.
    """


class ChoiceField(_FieldWrapper):
    """Represents a choice field.

    Multiselect is not currently supported; multiselect fields will still only allow
    selecting a single value.
    """

    @property
    def is_multiselect(self) -> bool:
        """Is this a multiselect field?

        Multiselect fields are currently treated as single-selection fields. True
        multiselect is not yet supported, but this flag is presented for your
        information.
        """
        # True multiselect could be enabled by setting /V to an array. However, I'm not
        # sure how to generate an appropriate appearance stream for a multiselect, and
        # QPDF doesn't seem to account for multiselect fields in it's appearance stream
        # generation algorithm either. This would require more research.
        return bool(self._field.flags & FormFieldFlag.ch_multi_select)

    @property
    def is_combobox(self) -> bool:
        """Is this a combobox field? If false, this is instead a list box."""
        return bool(self._field.flags & FormFieldFlag.ch_combo)

    @property
    def allow_edit(self) -> bool:
        """Does this field include an editable text box in addition to the dropdown?

        The field must be a comboxbox; this option is not valid for list boxes.
        """
        return bool(self._field.flags & FormFieldFlag.ch_edit)

    @property
    def spell_check_enabled(self) -> bool:
        """Should spell-checking be enabled in this field?

        This is only valid for fields that allow editing.
        """
        return not self._field.flags & FormFieldFlag.ch_do_not_spell_check

    @property
    def options(self) -> Sequence[ChoiceFieldOption]:
        """A list of all available options."""
        # The implementation in QPDF is not correct, as it only includes options which
        # are strings (see https://github.com/qpdf/qpdf/issues/1433). We opt for our own
        # implementation here.
        if Name.Opt not in self._field.obj:
            # It is perfectly valid for the choice field to have no options
            return ()
        return tuple(
            ChoiceFieldOption(self, opt, index)
            for index, opt in enumerate(self._field.obj.Opt.as_list())
        )

    @property
    def selected(self) -> ChoiceFieldOption | None:
        """The currently selected option, or None if no option is selected."""
        if Name.Opt in self._field.obj:
            for index, opt in enumerate(self._field.obj.Opt.as_list()):
                opt = ChoiceFieldOption(self, opt, index)
                if opt.export_value == self.value:
                    return opt
        return ChoiceFieldOption(self, self.value, None)

    @selected.setter
    def selected(self, option: ChoiceFieldOption):
        if option._field is not self:
            raise ValueError('Option does not belong to this field')
        # The PDF spec uses some language which makes me believe that it may still be
        # expected to use the display value as the value of V rather than the export
        # value. It isn't entirely clear to me either way. So, this may be incorrect.
        # If so, it should be as simple a matter to fix as changing `export_value` to
        # `display_value` in both the getter and the setter.
        self._field.set_value(
            option.export_value, self._form.generate_appearances is None
        )
        # Generate appearance streams if requested.
        if self._form.generate_appearances is not None:
            self._form.generate_appearances.generate_choice(self._field)
        # I'm ignoring the /I array for now, as it only is required for multiselect.

    @property
    def value(self) -> str | None:
        """The value of the currently selected option."""
        if self._field.value is not None:
            return self._field.value_as_string
        return None

    @value.setter
    def value(self, value: str | None):
        if not self.allow_edit:
            # Prevent setting a value not in the option list, unless the field is
            # editable
            okay = False
            for index, opt in enumerate(self._field.obj.Opt):
                opt = ChoiceFieldOption(self, opt, index)
                if opt.export_value == value:
                    okay = True
                    break
            if not okay:
                raise ValueError("Not a valid option for this choice field:", value)
        self._field.set_value(value, self._form.generate_appearances is None)
        # Generate appearance streams if requested.
        if self._form.generate_appearances is not None:
            self._form.generate_appearances.generate_choice(self._field)


class ChoiceFieldOption:
    """Represents a single option for a choice field."""

    def __init__(self, field: ChoiceField, opt: String | Array, index: int | None):
        """Create a new option for a choice field."""
        self._field = field
        self._opt = opt
        self._index = index

    @property
    def display_value(self):
        """The value that will be displayed on-screen to the user in a PDF reader."""
        if isinstance(self._opt, Array):
            return self._opt[1]
        else:
            return self._opt

    @property
    def export_value(self):
        """The value that will be used when exporting data from this form."""
        if isinstance(self._opt, Array):
            return self._opt[0]
        else:
            return self._opt

    @property
    def is_hidden(self) -> bool:
        """Is this option hidden?

        Hidden options are still settable via code, but are not shown to users in PDF
        reader applications.
        """
        return self._index is not None and self._index < self._field._field.obj.get(
            Name.TI, 0
        )

    @property
    def is_preset(self) -> bool:
        """Is this option one of the field's preset options?

        If false, this is a manually entered value typed by the user in an editable
        choice field.
        """
        return self._index is not None

    def select(self):
        """Set this option as the selected option."""
        self._field.selected = self

    @property
    def selected(self) -> bool:
        """Is this the currently selected option?"""
        return self._field.value == self.export_value


class SignatureField(_FieldWrapper):
    """Represents a signature field.

    Signatures are not truly supported.
    """

    def stamp_overlay(
        self,
        overlay: Object | Page,
        *,
        expand_rect: int
        | float
        | Decimal
        | Sequence[int | float | Decimal]
        | None = None,
    ) -> Name:
        """Stamp an image over the top of a signature field.

        This is *not* true support for PDF signatures. Rather, it is merely a utility
        for adding an image to the PDF at the location of a signature field.

        This uses `pikepdf.Page.add_overlay` under the hood, see that method for
        additional usage information.

        If the bounding box of the signature field is smaller than the "visual"
        signature area in the PDF, you may use the ``expand_rect`` parameter to increase
        the dimensions of the rectangle when stamping. This may be any of the
        following types:

        * A number, which will be added equally to all sides of the box
        * A sequence of two numbers, which will be added on the X and Y axis,
          respectively
        * A sequence of four numbers, which will be added to the left, bottom, right,
          and top sides respectively

        Positive numbers will increase the size of the box, and negative numbers will
        decease it.
        """
        # There is allowed to be only one annot per sig field, see 12.7.5.5
        field_annot = self._form._acroform.get_annotations_for_field(self._field)[0]
        if Name.P in field_annot.obj:
            # The annot keeps a reference to the page (not always the case)
            Page(field_annot.obj.P).add_overlay(
                overlay, self._expand_rect(field_annot.rect, expand_rect)
            )
        for page in self._form._pdf.pages:
            # Fall back to looping through all possible pages.
            for annot in self._form._acroform.get_widget_annotations_for_page(page):
                if annot == field_annot:
                    return page.add_overlay(
                        overlay, self._expand_rect(annot.rect, expand_rect)
                    )
        raise ValueError("Could not find annotation for signature field")

    def _expand_rect(self, rect: Rectangle, expand_by: int | float | Decimal | None):
        if expand_by is None:
            return rect
        if isinstance(expand_by, (int, float, Decimal)):
            expand_by = (expand_by, expand_by, expand_by, expand_by)
        if len(expand_by) == 2:
            expand_by = (*expand_by, *expand_by)
        return Rectangle(
            rect.llx - float(expand_by[0]),
            rect.lly - float(expand_by[1]),
            rect.urx + float(expand_by[2]),
            rect.ury + float(expand_by[3]),
        )


class AppearanceStreamGenerator(ABC):
    """Appearance stream generators are used to render forms.

    They are used by the `pikepdf.form.Form` class to optionally generate appearance
    streams as forms are filled.
    """

    pdf: Pdf
    form: AcroForm

    def __init__(self, pdf: Pdf, form: AcroForm):
        """Initialize the appearance stream generator."""
        self.pdf = pdf
        self.form = form

    @abstractmethod
    def generate_text(self, field: AcroFormField):
        """Generate the appearance stream for a text field."""

    @abstractmethod
    def generate_choice(self, field: AcroFormField):
        """Generate the appearance stream for a choice field."""


class DefaultAppearanceStreamGenerator(AppearanceStreamGenerator):
    """Basic appearance stream generator using QPDF's default algorithm.

    It is thus subject to all the same
    `limitations <https://qpdf.readthedocs.io/en/stable/cli.html#option-generate-appearances>`_.

    Briefly summarized, these limitations are:

    * Cannot generate appearance streams using encodings other than ASCII, WinAnsi, or
      MacRoman
    * No support for multiline text
    * No support for auto-sized text
    * Does not respect quadding

    Using this class will produce the same results as the following code:

    .. code-block:: python

        form = Form(pdf, generate_appearances = None)
        ...
        pdf.generate_appearances()

    However, unlike the above, appearances will be generated on the fly as the form is
    filled out, rather than all at once at the end.

    You may extend this class to customize appearance streams or add support for
    features you need.
    """

    def generate_text(self, field: AcroFormField):
        """Generate the appearance stream for a text field."""
        for annot in self.form.get_annotations_for_field(field):
            field.generate_appearance(annot)

    def generate_choice(self, field: AcroFormField):
        """Generate the appearance stream for a choice field."""
        for annot in self.form.get_annotations_for_field(field):
            field.generate_appearance(annot)


class ExtendedAppearanceStreamGenerator(DefaultAppearanceStreamGenerator):
    """Alternate appearance stream generator to address limitations of the default one.

    Improved features include:
      * Supports multiline text fields, with caveats:

      * Word wrap does not take scaling factors (other than font size) into account

      * Spacing operators not taken into consideration either

      * Quadding is still ignored

      * Due to limitations in Firefox's PDF viewer, the font and the line breaks will be
        incorrect when viewed in Firefox. PDFs filled by full-fat PDF readers, including
        Adobe Acrobat Reader, exhibit the same behavior when viewed in Firefox.

      * Supports combed text fields, with most of the same caveats as above

    Otherwise, this implementation has most of the same limitations as the default
    implementation. Unlike the default implementation, this is implemented in Python
    rather than C++, so will also be less performant.
    """

    def generate_text(self, field: AcroFormField):
        """Generate the appearance stream for a text field."""
        if field.flags & FormFieldFlag.tx_multiline:
            _text_appearance_multiline(self.pdf, self.form, field)
        elif field.flags & FormFieldFlag.tx_comb:
            _text_appearance_combed(self.pdf, self.form, field)
        else:
            # Fall back to the default implementation if we don't have a better one
            super().generate_text(field)


# The following functions are used to generate appearance streams for text inputs. With
# some additional refinement, some of this functionality could be moved to the canvas
# submodule and exposed as part of a public API. Right now, however, it's probably too
# specialized; it couldn't be used to create an arbitrary text box separate from a form
# field.
#
# Generating appearance streams for text fields is not trivial. Section 12.7.4.3 of the
# PDF 2.0 spec (Variable text) lays out how this is to be done. Also refer to the
# following similar implementations for references:
#
# * https://github.com/py-pdf/pypdf/blob/5c3550f66c5da530eb8853da91afe0f942afcbef/pypdf/_writer.py#L857
# * https://github.com/mozilla/pdf.js/blob/2c87c4854a486d5cd0731b947dd622f8abe5e1b5/src/core/annotation.js#L2138
# * https://github.com/fwenzel/pdftk/blob/a3db40d1a43207eaad558aa9591ef81403b51616/java/pdftk/com/lowagie/text/pdf/AcroFields.java#L407
# * https://github.com/qpdf/qpdf/blob/81823f4032caefd1050bccb207d315839c1c48db/libqpdf/QPDFFormFieldObjectHelper.cc#L746


def _text_appearance_multiline(pdf: Pdf, form: AcroForm, field: AcroFormField):
    da_info = _DaInfo.decode_for_field(field)
    for annot in form.get_annotations_for_field(field):
        # There is likely only one annot, but we have to allow for multiple
        bbox = annot.rect.to_bbox()
        with _text_stream_builder(da_info.da) as cs:
            if da_info.text_matrix is None:
                # If there is no existing matrix, create located at the upper-right of
                # the bbox (with allowance for the height of the text).
                top_offset = da_info.font.ascent
                if top_offset is None:
                    # Fallback to full line height
                    top_offset = da_info.line_spacing
                else:
                    # Scale to text-space
                    top_offset = da_info.font.convert_width(
                        top_offset, da_info.font_size
                    )
                cs.set_text_matrix(
                    Matrix.identity().translated(
                        bbox.llx, Decimal(bbox.ury) - top_offset
                    )
                )
            _layout_multiline_text(cs, field.value_as_string, da_info, bbox)
        _apply_appearance_stream(pdf, annot, cs, bbox, da_info)


def _text_appearance_combed(pdf: Pdf, form: AcroForm, field: AcroFormField):
    da_info = _DaInfo.decode_for_field(field)
    for annot in form.get_annotations_for_field(field):
        # There is likely only one annot, but we have to allow for multiple
        bbox = annot.rect.to_bbox()
        with _text_stream_builder(da_info.da) as cs:
            if da_info.text_matrix is None:
                # If there is no existing matrix, create located at the lower-right of
                # the bbox (with allowance for the descent of the text).
                # Fallback to zero
                bottom_offset = da_info.font.descent or 0
                # Scale to text-space
                bottom_offset = da_info.font.convert_width(
                    bottom_offset, da_info.font_size
                )
                cs.set_text_matrix(
                    Matrix.identity().translated(
                        bbox.llx, Decimal(bbox.lly) - bottom_offset
                    )
                )
            _layout_combed_text(
                cs,
                field.value_as_string,
                da_info,
                bbox,
                field.get_inheritable_field_value("/MaxLen"),
            )
        _apply_appearance_stream(pdf, annot, cs, bbox, da_info)


def _apply_appearance_stream(pdf, annot, cs, bbox, da_info):
    """Convert content stream to a Form XObject and save in annotation.

    The appearance stream is saved in the annotation dictionary (AP) under the normal
    (N) key.
    """
    fonts_dict = Dictionary()
    fonts_dict[da_info.font_name] = da_info.font.register(pdf)
    resources = Dictionary(Font=fonts_dict)
    xobj = _create_form_xobject(pdf, bbox, cs, resources)
    if Name.AP in annot.obj:
        annot.obj.AP.N = xobj
    else:
        annot.obj.AP = Dictionary(N=xobj)


@dataclass
class _DaInfo:
    da: bytes
    font: SimpleFont
    font_name: Name
    font_size: Decimal
    char_spacing: Decimal | None = None
    word_spacing: Decimal | None = None
    line_spacing: Decimal | None = None
    text_matrix: Matrix | None = None

    @classmethod
    def decode_for_field(cls, field: AcroFormField) -> _DaInfo:
        """Parse the default appearance, returning it and the font styling information.

        The default appearance is a value that is used to initialize the content stream
        for text fields. It must at minimum contain a `Tf` operator, which indicates the
        font family and size.
        """
        da = field.default_appearance
        tmp_pdf = Pdf.new()
        tmp_stream = tmp_pdf.make_stream(da)
        instructions = parse_content_stream(tmp_stream)
        # Locate the last Tf operator and use its operands (In theory there should only
        # be one, but you never know...). Also locate the optional Tm operator.
        tf_op = Operator('Tf')
        tm_op = Operator('Tm')
        tf_inst = None
        tm_inst = None
        for inst in instructions:
            if inst.operator == tf_op:
                tf_inst = inst
            if inst.operator == tm_op:
                tm_inst = inst
        if tf_inst is None:
            # This state is not valid according to the spec, but for robustness we could
            # consider adding a fallback.
            raise RuntimeError(
                "No Tf operator found in default appearance stream for "
                f"{field.fully_qualified_name}"
            )
        # Load styling information from the DA
        font_family, font_size = tf_inst.operands
        if font_size == 0:
            # It is allowed for the font_size to be zero, which is supposed to indicate
            # an auto-sized font (See 12.7.4.3). This means we should evaluate the size
            # of the actual text and scale it to fit in the bounding box. I feel like
            # supporting this is out of scope for now, but it could be supported in the
            # future. For now, we'll pretend it was 11pt.
            da = da.replace(b'0 Tf', b'11 Tf')
            font_size = 11
        font = SimpleFont.load(font_family, field.default_resources)
        matrix = tm_inst.operands[0] if tm_inst is not None else None
        # Make up a value for line spacing.
        #
        # The PDF spec gives no information about what forms should use for line spacing
        # if not defined in the DA (which is usually isn't). I've chosen to use the
        # font's default leading value if available, then fall back to using the font
        # size. Using the font size as the line spacing appears to be what Evince
        # Document Viewer is doing, so it seems like a reasonable fallback.
        #
        # We could parse the DA and see if by chance we can extract custom values
        # that may be set for spacing. (I haven't seen examples of this, but it would
        # probably be more correct.)
        line_spacing = font.leading or font_size
        return cls(da, font, font_family, font_size, None, None, line_spacing, matrix)


@contextmanager
def _text_stream_builder(da: bytes):
    """Utility to build text content streams for variable text fields.

    Example:

    .. code-block:: python

        with _text_stream_builder(da) as cs:
            # Make calls against cs, e.g.:
            cs.show_text(b'some text')
            ...

        # Now cs is complete. (Make sure you are outside the context manager; additional
        # operations are added once the context manager closes.)
    """
    content_builder = ContentStreamBuilder()
    content_builder.begin_marked_content(Name.Tx)
    content_builder.push()
    # Adobe includes a re, E, and n operation here (Creating a clip rectangle). Many
    # other PDF viewers do similarly. This is probably a good idea for the future, but
    # for now, while the layout algorithm is still imperfect, there is probably value in
    # not clipping and just showing what was entered.
    content_builder.begin_text()
    content_builder.extend(da)
    yield content_builder
    content_builder.end_text()
    content_builder.pop()
    content_builder.end_marked_content()


def _layout_multiline_text(
    content: ContentStreamBuilder, text: str, da_info: _DaInfo, bbox: Rectangle
):
    r"""Lay out the given text, wrapping at the edges of the bounding box.

    This layout algorithm is incomplete and somewhat rudimentary, but should produce
    acceptable results for most common use cases.

    Known issues:

    * Does not respect field-defined alignment (quadding) and spacing.
    * The text may overflow out the bottom of the box. We don't try to prevent this
      currently, though a correct implementation would do so if scrolling was
      disabled.
    * Words which are longer than the box width may overflow out the right side.
    * Does not allow line breaks other than at ' ' or '\n' characters.
    * Only ASCII, WinAnsi, and MacRoman encodings are supported.
    """
    font = da_info.font
    font_size = da_info.font_size
    # Word spacing in the PDF specification is something that is added *in addition* to
    # the width of the space, but we also want to take the width of the space itself
    # into account for what we're doing.
    word_spacing = font.text_width(' ', font_size) + (da_info.word_spacing or 0)
    # Fallback to font size if line spacing not provided
    content.set_text_leading(da_info.line_spacing or font_size)
    width = bbox.width
    try:
        text = font.encode(text)
    except NotImplementedError:
        # If the font uses an unsupported encoding, we will assume it is at least an
        # ASCII-compatible encoding and go for it.
        text = text.encode('ascii', errors='replace')
    for lineno, line in enumerate(text.splitlines()):
        if lineno != 0:
            # Manual newlines
            content.move_cursor_new_line()
        line_width = Decimal(0)
        line_words = []
        for word in line.split():
            word_len = font.text_width(word, font_size)
            if line_width + word_spacing + word_len > width:
                # Wrap if too long
                content.show_text(b' '.join(line_words))
                content.move_cursor_new_line()
                line_width = word_len
                line_words = [word]
            else:
                # Append to end of current line
                line_words.append(word)
                line_width += word_spacing + word_len
        if line_words:
            # Show last line
            content.show_text(b' '.join(line_words))


def _layout_combed_text(
    content: ContentStreamBuilder,
    text: str,
    da_info: _DaInfo,
    bbox: Rectangle,
    max_length: int | Decimal,
):
    """Lay out text, spacing characters evenly according to comb size.

    This layout algorithm is incomplete and somewhat rudimentary, but should produce
    acceptable results for most common use cases.

    Known issues:

    * Does not respect field-defined alignment (quadding).
    * Only ASCII, WinAnsi, and MacRoman encodings are supported.
    """
    font = da_info.font
    font_size = da_info.font_size
    width = bbox.width
    comb_size = Decimal(width) / max_length
    comb_size_gs = font.convert_width_reverse(comb_size, font_size)
    parts = []
    last_width = 0
    for char in text:
        try:
            char = font.encode(char)
        except NotImplementedError:
            # If the font uses an unsupported encoding, we will assume it is at least an
            # ASCII-compatible encoding and go for it.
            char = char.encode('ascii', errors='replace')
        space_needed = (font.unscaled_char_width(char) - comb_size_gs) / 2
        parts.append(last_width + space_needed)
        parts.append(char)
        last_width = space_needed
    content.show_text_with_kerning(*parts)


def _create_form_xobject(
    pdf: Pdf, bbox: Rectangle, content: ContentStreamBuilder, resources: Dictionary
):
    """Convert a content stream into a Form XObject."""
    return pdf.make_stream(
        content.build(),
        Type='XObject',
        Subtype='Form',
        FormType=1,
        BBox=bbox,
        Resources=resources,
    )
