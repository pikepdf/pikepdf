Form
****

The ``pikepdf.form`` module provides a high-level API for working with interactive forms, built on top of the lower-level `pikepdf.AcroForm` interface.

.. autoapiclass:: pikepdf.form.Form
    :members:

Form Fields
===========

.. autoapiclass:: pikepdf.form._FieldWrapper
    :members:

.. autoapiclass:: pikepdf.form.TextField
    :members:

.. autoapiclass:: pikepdf.form.CheckboxField
    :members:

.. autoapiclass:: pikepdf.form.RadioButtonGroup
    :members:

.. autoapiclass:: pikepdf.form.RadioButtonOption
    :members:

.. autoapiclass:: pikepdf.form.PushbuttonField
    :members:

.. autoapiclass:: pikepdf.form.ChoiceField
    :members:

.. autoapiclass:: pikepdf.form.ChoiceFieldOption
    :members:

.. autoapiclass:: pikepdf.form.SignatureField
    :members:

Generating Appearance Streams
=============================

Merely setting the values of form fields is not sufficient. It is also necessary to 
generate appearance streams for fields. These appearance streams define how the filled-out 
field should actually look when viewed in a PDF reader.

Generating appearance streams can be very complex. Both of the classes below have limited 
capacities, but should work for many use cases, and can be extended to meet your needs.

.. autoapiclass:: pikepdf.form.AppearanceStreamGenerator
    :members:

.. autoapiclass:: pikepdf.form.DefaultAppearanceStreamGenerator
    :members:

.. autoapiclass:: pikepdf.form.ExtendedAppearanceStreamGenerator
    :members:



