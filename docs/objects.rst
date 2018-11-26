pikepdf Object Model
********************

This section covers the object model pikepdf uses in more detail.

A :class:`pikepdf.Object` is a Python wrapper around a C++ ``QPDFObjectHandle``
which, as the name suggests, is a handle (or pointer) to a data structure in
memory, or possibly a reference to data that exists in a file. Importantly, an
object can be a scalar quantity (like a string) or a compound quantity (like a
list or dict, that contains other objects). The fact that the C++ class involved
here is an object *handle* is an implementation detail; it shouldn't matter for
a pikepdf user.

The simplest types in PDFs are directly represented as Python types: ``int``,
``bool``, and ``None`` stand for PDF integers, booleans and the "null".
:class:`~decimal.Decimal` is used for floating point numbers in PDFs. If a
value in a PDF is assigned to a Python ``float``, pikepdf will convert it to
``Decimal``.

Types that are not directly convertible to Python are represented as
:class:`pikepdf.Object`, a compound object that offers a superset of methods,
some work only if the underlying type is suitable. You can use the EAFP
idiom or ``isinstance`` to determine the type more precisely. This partly
reflects the fact that the PDF specification allows many data fields to be
one of several types.

For convenience, the ``repr()`` of a ``pikepdf.Object`` will display a
Python expression that replicates the existing object (when possible), so it
will say:

.. code-block:: python

    >>> catalog_name = pdf.root.Type
    pikepdf.Name("/Catalog")
    >>> isinstance(catalog_name, pikepdf.Name)
    True
    >>> isinstance(catalog_name, pikepdf.Object)
    True


Making PDF objects
==================

You may construct a new object with one of the classes:

*   :class:`pikepdf.Array`
*   :class:`pikepdf.Dictionary`
*   :class:`pikepdf.Name` - the type used for keys in PDF Dictionary objects
*   :class:`pikepdf.String` - a text string
    (treated as ``bytes`` and ``str`` depending on context)

These may be thought of as subclasses of ``pikepdf.Object``. (Internally they
**are** ``pikepdf.Object``.)

There are a few other classes for special PDF objects that don't
map to Python as neatly.

*   ``pikepdf.Operator`` - a special object involved in processing content
    streams
*   ``pikepdf.Stream`` - a special object similar to a ``Dictionary`` with
    binary data attached
*   ``pikepdf.InlineImage`` - an image that is embedded in content streams

The great news is that it's often unnecessary to construct ``pikepdf.Object``
objects when working with pikepdf. Python types are transparently *converted* to
the appropriate pikepdf object when passed to pikepdf APIs – when possible.
However, pikepdf sends ``pikepdf.Object`` types back to Python on return calls,
in most cases, because pikepdf needs to keep track of objects that came from
PDFs originally.
