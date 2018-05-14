pikepdf Object Model
********************

This section covers the object model pikepdf uses in more detail.

A :class:`pikepdf.Object` is a Python wrapper around a C++ ``QPDFObjectHandle``
which, as the name suggests, is a handle (or pointer) to a data structure in
memory, or possibly a reference to data that exists in a file. Importantly, an
object can be a scalar quantity (like an integer) or a compound quatity (like a
list or dict, that contains other objects). The fact that the C++ class involved
here is an object handle is an implementation detail; it shouldn't matter for a
pikepdf user.

There is something of an impedance mismatch between Python's strict dynamic
typing and a C++ library that effectively has a dynamic variant type. Currently
this is managed by **not** subclassing ``pikepdf.Object``. Instead pikepdf
``pikepdf.Object`` implements all of the methods it could ever use.

For convenience, the ``repr()`` of a ``pikepdf.Object`` will display a
Python expression that replicates the existing object (when possible), so it
will say:

.. code-block:: python

    >>> three = pikepdf.Integer(3)
    pikepdf.Integer(3)

But in reality it's just a PDF object, with no subclassing:

.. code-block:: python

    >>> three.__class__.__name__
    pikepdf.Object

Making PDF objects
==================

You may construct a new object with one of the factory functions:

*   :class:`pikepdf.Integer`
*   :class:`pikepdf.Boolean`
*   :class:`pikepdf.Array`
*   :class:`pikepdf.Dictionary`
*   :class:`pikepdf.Real` - decimal numbers, similar to :class:`decimal.Decimal`
*   :class:`pikepdf.Name` - the type used for keys in PDF Dictionary objects
*   :class:`pikepdf.String` - a text string 
    (treated as ``bytes`` and ``str`` depending on context)
*   :class:`pikepdf.Null` - equivalent to ``None``

For example, a PDF :class:`Boolean` may be constructed as 

.. code-block:: python

    >>> pikepdf.Boolean(True)
    pikepdf.Boolean(True)

There are a few other factory functions for special PDF objects that don't
map to Python as neatly. We'll look at these later.

*   ``pikepdf.Operator`` - a special object involved in processing content
    streams
*   ``pikepdf.Stream`` - a special object similar to a ``Dictionary`` with
    compressed binary data attached
*   ``pikepdf.Inlineimage`` - an image that is embedded in content streams

The great news is that it's often unnecessary to construct ``pikepdf.Object``
objects when working with pikepdf. Python types are transparently *converted* to
the appropriate pikepdf object when passed to pikepdf APIs – when possible.
However, pikepdf sends ``pikepdf.Object`` types back to Python on return calls,
in most cases, because pikepdf needs to keep track of objects that came from
PDFs originally.

Because Python types are converted to pikepdf types, references will be lost.

