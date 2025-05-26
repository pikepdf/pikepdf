# Working with interactive forms

pikepdf provides two interfaces for working with interactive forms. There is a low-level
interface, {class}`pikepdf.AcroForm`, which is exposed as the
{attr}`pikepdf.Pdf.acroform` property. There is also a higher-level interface available
in the {mod}`pikepdf.form` module, which provides several abstractions to make usage
easier.

## Extracting Form Data

It is relatively easy to extract basic form data from a PDF.

```python
>>> from pikepdf.form import Form

>>> form = Form(pdf)

>>> data = {}

>>> for field_name, field in form.items():
...    if field.is_text or field.is_choice or field.is_radio_button:
...        data[field_name] = field.value
...    elif field.is_checkbox:
...        data[field_name] = field.checked
```

## Inspecting the Form

The form allows retrieving specific named fields via dict-like access. There are several
useful properties common to all fields. The most useful of these are:

- `alternate_name`, which is a human-readable label for the field.
- `fully_qualified_name`, which is the machine-readable key which identifies this field
- `is_required`
- `is_text`
- `is_checkbox`
- `is_radio_button`
- `is_pushbutton`
- `is_choice`

```python
>>> field = form['MyField']

>>> field.fully_qualified_name
"MyField"

>>> field.alternate_name
"Applicant's first given name"

>>> field.is_text
True

>>> field.is_required
False
```

## Filling Form Data

Before filling a form, you will need to determine how you will deal with appearance
streams. In addition to merely holding values, PDF form fields must explicitly declare
how the filled-in value should look. This is known as the appearance stream. There are
several options available.

First, you may choose not to generate appearance streams at all. Most full-fat PDF readers
are capable of generating these appearance streams themselves, so depending on your use
case it may be acceptable to leave appearance stream generation to the end-user
application. This is the default behavior of the {class}`pikepdf.form.Form` class.

If you do need or want to generate appearance streams, you must provide the class you wish
to use to accomplish this task. There are two possible implementations provided with
pikepdf: {class}`pikepdf.form.DefaultAppearanceStreamGenerator` and
{class}`pikepdf.form.ExtendedAppearanceStreamGenerator`. To use either of these, simply pass
the class as the second argument to the constructor:

```python
>>> from pikepdf.form import Form, DefaultAppearanceStreamGenerator

>>> form = Form(pdf, DefaultAppearanceStreamGenerator)
```

The differences between these two options is explained in the documentation for each class.

Lastly, you may implement your own class for generating appearance streams that better
fits your specific use case. It must implement the interface provided by
{class}`pikepdf.form.AppearanceStreamGenerator`.

After filling a form, you may also wish to flatten it. This converts the interactive form
fields into normal, un-editable text. This can be done as follows:

```python
pdf.flatten_annotations()
```

Generating appearance streams is required if you wish to flatten the form.

### Text Fields

Text fields can either resemble an HTML text input, or an HTML textarea, as well as a
password field, file upload, or rich text input. pikepdf supports only the first two
options, which can be distinguished from one another using the `is_multiline` property.

The underlying value of the text field is stored in the `value` property. The field
may also have a `default_value` which should be used when resetting the form.

```python
>>> text_field = form['MyTextField']

>>> text_field.is_multiline
False

>>> text_field.default_value
''

>>> text_field.value
''

>>> text_field.max_length
75

>>> text_field.value = "Hello World!"
```

### Checkbox Fields

Checkbox fields behave somewhat similarly to what you might be familiar with working with
HTML forms in JavaScript. There is a `checked` property which will tell you if the box
is checked or not. If access to the underlying value is needed, it can be fetched via the
`value` property.

Unlike HTML checkboxes, however, there is a value for both the on *and* off states, and
thus `value` will return different values depending on if the box is checked or not. The
value for an off state will be a `pikepdf.Name` with the value "/Off". The value for the
on state is variable, and can be retrieved from the `on_value` property.

```python
>>> checkbox_field = form['MyCheckbox']

>>> checkbox.checked
False

>>> checkbox.value
pikepdf.Name("/Off")

>>> checkbox.on_value
pikepdf.Name("/Yes")

>> checkbox.states
(pikepdf.Name("/Yes"), pikepdf.Name("/Off"))

>>> checkbox.checked = True

>>> checkbox.value
pikepdf.Name("/Yes")
```

### Radio Button Groups

A radio button group is constrained to a finite list of allowed values, which are all
`pikepdf.Name` objects. The list of allowed values can be obtained via the `states`
property.

```python
>>> radio_group = form['MyRadioButtonGroup']

>>> radio_group.states
(pikepdf.Name("/1"), pikepdf.Name("/2"), pikepdf.Name("/3"))

>>> radio_group.value
None

>>> radio_group.value = pikepdf.Name("/1")
```

Radio buttons are returned as a group rather than as individual buttons, though
representations of the individual buttons can be obtained by way of the `options`
property. You can set the selection option via the group's `selected` property, or via
the button's `select` method.

```python
>>> radio_group.options[0].checked
True

>>> radio_group.options[1].on_value
pikepdf.Name("/2")

>>> radio_group.options[1].states
(pikepdf.Name("/2"), pikepdf.Name("/Off"))

>>> radio_group.selected = radio_group.options[1]

>>> radio_group.value
pikepdf.Name("/2")

>>> radio_group.options[2].select()

>>> radio_group.value
pikepdf.Name("/3")
```

### Choice Fields

Choice fields may be either list boxes or comboboxes, as determined by the `is_combobox`
property. If the field is a combobox, it may optionally have an editable text box attached
to it, as shown by the `allows_edit` property. Editable choice fields may store
arbitrary values, but otherwise choice fields are limited to those options which are
returned via the `options` property.

```python
>>> field = form['MyChoiceField']

>>> field.is_combobox
True

>>> field.allows_edit
False

>>> field.options[0].display_name
"Pike"

>>> field.options[2].select()

>>> field.value
"Trout"

>>> field.value = "Pike"
```

### Signature Fields

pikepdf does not support signature fields, but does include a utility function to stamp an
image over the top of the field's bounding box. The stamped image must be a PDF.

```python
>>> form_pdf = Pdf.open(...)

>>> sig_pdf = Pdf.open(...)

>>> form = Form(form_pdf)

>>> form['MySigField'].stamp_overlay(sig_pdf.pages[0])
```

To stamp an image that is not already a PDF, you will need to use an image processing
library, such as [Pillow](https://pillow.readthedocs.io/en/stable/) to convert it:

```python
>>> from PIL import Image

>>> img = Image.open(img).convert('RGB')

>>> img_as_pdf = BytesIO()

>>> img.save(img_as_pdf, 'pdf')

>>> img_as_pdf.seek(0)

>>> sig_pdf = Pdf.open(img_as_pdf)
```
