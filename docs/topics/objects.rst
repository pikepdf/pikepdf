Object model
************

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
value in a PDF is assigned a Python ``float``, pikepdf will convert it to
``Decimal``.

Types that are not directly convertible to Python are represented as
:class:`pikepdf.Object`, a compound object that offers a superset of possible
methods, some of which only if the underlying type is suitable. Use the
:abbr:`EAFP (easier to ask forgiveness than permission)` idiom, or
``isinstance`` to determine the type more precisely. This partly reflects the
fact that the PDF specification allows many data fields to be one of several
types.

For convenience, the ``repr()`` of a ``pikepdf.Object`` will display a
Python expression that replicates the existing object (when possible), so it
will say:

.. code-block:: python

    >>> catalog_name = pdf.Root.Type
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

Object lifecycle and memory management
======================================

As mentioned above, a :class:`pikepdf.Object` may reference data that is lazily
loaded from its source :class:`pikepdf.Pdf`. Closing the `Pdf` with
:meth:`pikepdf.Pdf.close` will invalidate some objects, depending on whether
or not the data was loaded, and other implementation details that may change.
Generally speaking, a :class:`pikepdf.Pdf` should be held open until it is no
longer needed, and objects that were derived from it may or may not be usable
after it is closed.

Simple objects (booleans, integers, decimals, ``None``) are copied directly
to Python as pure Python objects.

For PDF stream objects, use :meth:`pikepdf.Object.read_bytes()` to obtain a
copy of the object as pure bytes data, if this information is required after
closing a PDF.

When objects are copied from one :class:`pikepdf.Pdf` to another, the
underlying data is copied immediately into the target. As such it is possible
to merge hundreds of `Pdf` into one, keeping only a single source at a time and the
target file open.

Indirect objects
================

PDF has two ways to represented a PDF dictionary that contains another dictionary:
it can contain the inner dictionary, or provide a reference to another object.
In the PDF file itself, most objects have an object number that is for referencing.

pikepdf hides the details about whether an object is directly or indirectly
referenced, since in many situations it does not matter and manually testing each
object to see if it needs to be dereferenced before accessing it is tedious.
However, you may need to create indirect references. Sometimes, the |pdfrm|
specifically requires that a value be an indirect object.

You can use :attr:`pikepdf.Object.is_indirect` to check if an object is actually
an indirect reference. If you require an indirect object, use
:meth:`pikepdf.Pdf.make_indirect` to attach the dictionary to a `Pdf` and return
an indirect copy of it. Direct objects are not attached to any particular `Pdf`
and can be copied from one to another, just like scalars. Indirect objects
must be attached.

Stream objects are always indirect objects, and must always be attached to a
PDF.

Object helpers
==============

pikepdf also provides :class:`pikepdf.ObjectHelper` and various subclasses of
this class. Usually these are wrappers around a :class:`pikepdf.Dictionary` with
special rules applicable to that type of dictionary. :class:`pikepdf.Page` is
an example of an object helper. The underlying object can be accessed with
:attr:`pikepdf.ObjectHelper.obj`.