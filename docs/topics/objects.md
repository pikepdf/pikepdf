# Object model

This section covers the object model pikepdf uses in more detail.

A {class}`pikepdf.Object` is a Python wrapper around a C++ `QPDFObjectHandle`
which, as the name suggests, is a handle (or pointer) to a data structure in
memory, or possibly a reference to data that exists in a file. Importantly, an
object can be a scalar quantity (like a string) or a compound quantity (like a
list or dict, that contains other objects). The fact that the C++ class involved
here is an object *handle* is an implementation detail; it shouldn't matter for
a pikepdf user.

The simplest types in PDFs are directly represented as Python types: `int`,
`bool`, and `None` stand for PDF integers, booleans and the "null".
{class}`~decimal.Decimal` is used for floating point numbers in PDFs. If a
value in a PDF is assigned a Python `float`, pikepdf will convert it to
`Decimal`.

Types that are not directly convertible to Python are represented as
{class}`pikepdf.Object`, a compound object that offers a superset of possible
methods, some of which only if the underlying type is suitable. Use the
{abbr}`EAFP (easier to ask forgiveness than permission)` idiom, or
`isinstance` to determine the type more precisely. This partly reflects the
fact that the PDF specification allows many data fields to be one of several
types.

## Explicit conversion mode

By default, pikepdf automatically converts PDF scalar types to Python native
types (`int`, `bool`, `Decimal`). This is convenient but can make type checking
difficult, especially when handling potentially malformed PDFs where a field
might contain an unexpected type.

pikepdf provides an **explicit conversion mode** that preserves PDF type
information by returning {class}`pikepdf.Integer`, {class}`pikepdf.Boolean`,
and {class}`pikepdf.Real` objects instead of native Python types.

:::{versionadded} 10.14
`implicit_conversion()`, the per-`Pdf` `conversion_mode`,
{meth}`~pikepdf.Object.get_raw`, the `get_int`/`get_bool`/`get_float`/
`get_decimal`/`get_dict`/`get_list` typed getters, and `coerce=` on the
`as_*` accessors.
:::

### Three scopes, one precedence order

The conversion mode can be set at three different scopes, resolved in this
order (most specific wins):

1. **Context manager** (thread-local) — {func}`pikepdf.explicit_conversion`
   and {func}`pikepdf.implicit_conversion` push a mode for the current thread
   only, for the duration of the `with` block. This is the same mechanism as
   before, just now symmetric: you can force implicit mode from inside code
   that runs under explicit mode, or vice versa.
2. **Per-document** — {meth}`pikepdf.Pdf.open` and {meth}`pikepdf.Pdf.new`
   accept a keyword-only `conversion_mode` argument (`'implicit'` or
   `'explicit'`), and the mode can be read or changed later through the
   {attr}`pikepdf.Pdf.conversion_mode` property. This mode travels with the
   `Pdf` object itself: it is the same regardless of which thread touches the
   document, which makes it the right scope for a library that opens PDFs on
   behalf of a host application without wanting to change that application's
   own behavior. Setting the property to `None` makes the document inherit
   whatever mode applies globally (or from a context manager).
3. **Global** — {func}`pikepdf.set_object_conversion_mode` sets a
   process-wide default, read back with
   {func}`pikepdf.get_object_conversion_mode`. This is visible from every
   thread immediately, so it is a poor fit for code embedded inside another
   application; prefer the per-document mode there.

```python
>>> import pikepdf
>>> pdf = pikepdf.open("example.pdf", conversion_mode='explicit')
>>> pdf.conversion_mode
'explicit'
>>> count = pdf.Root.Pages.Count
>>> isinstance(count, pikepdf.Integer)
True
>>> int(count)
5

>>> with pikepdf.implicit_conversion():
...     pdf.Root.Pages.Count  # context manager overrides the per-Pdf mode
5
```

An object with no owning `Pdf` — for example a bare
`pikepdf.Dictionary(...)` you constructed yourself, before attaching it to a
document — has no per-document mode to consult, so it always resolves through
the context-manager/global scopes. Once such an object is attached to a `Pdf`
(for example by assigning it into the document), it takes on that document's
mode.

You can also set explicit mode globally:

```python
>>> pikepdf.set_object_conversion_mode('explicit')
>>> pikepdf.get_object_conversion_mode()
'explicit'
```

`set_object_conversion_mode` raises `ValueError` for any value other than
`'implicit'` or `'explicit'`.

### Reading values without depending on the mode

Because the conversion mode changes the *type* of value a caller receives,
code that reads optional fields out of possibly-malformed PDFs has
historically had to pick a mode first. Two APIs sidestep that:

{meth}`~pikepdf.Object.get_raw` behaves like {meth}`~pikepdf.Object.get` (it
accepts a key, a {class}`~pikepdf.Name`, or a {class}`~pikepdf.NamePath`, and
a `default`), but it never unboxes: it always returns a `pikepdf.Object`
(or the `default`), regardless of the current conversion mode:

```python
>>> d = pikepdf.Dictionary(I=42, S=pikepdf.String('x'))
>>> type(d.get_raw('/I'))    # Object, even in implicit mode
<class 'pikepdf.objects.Object'>
>>> d.get_raw('/I').as_int()
42
>>> d.get_raw('/S').as_int(0)
0
>>> d.get_raw('/Missing', 'fallback')
'fallback'
```

A PDF null inside an array is returned as a `Null`-typed `Object` rather than
`None`. A dictionary key whose value is null is treated by qpdf as absent, so
`get_raw` returns the `default` for it, just as `get` does.

The typed getters — {meth}`~pikepdf.Object.get_int`,
{meth}`~pikepdf.Object.get_bool`, {meth}`~pikepdf.Object.get_float`,
{meth}`~pikepdf.Object.get_decimal`, {meth}`~pikepdf.Object.get_dict`, and
{meth}`~pikepdf.Object.get_list` — combine `get_raw` with the matching `as_*`
accessor, so reading an optional, possibly-wrong-typed value is a
mode-independent one-liner:

```python
>>> width = d.get_int('/Width', 0)
>>> flag = d.get_bool(NamePath.MarkInfo.Marked, False, coerce=True)
```

Each accepts `key_or_path` (a `str`, `Name`, or `NamePath`), a `default`
(`None` if omitted), and, for the numeric and boolean getters, a
`coerce=` keyword with the same meaning as on the corresponding `as_*`
method below. These are the recommended way to read a value whose type
you cannot guarantee, in *either* conversion mode.

### Safe accessor methods

When working with PDF objects, you often need to extract scalar values while
handling type mismatches gracefully. The `as_*` methods provide type-safe
access with optional defaults:

```python
>>> with pikepdf.explicit_conversion():
...     d = pikepdf.Dictionary(Width=100, Name=pikepdf.Name.Foo)
...     d.Width.as_int()  # Returns 100
...     d.Name.as_int(default=0)  # Returns 0 (Name is not an integer)
...     d.Name.as_int()  # Raises TypeError
```

Available methods:
- {meth}`~pikepdf.Object.as_int` - convert to `int`, or return default
- {meth}`~pikepdf.Object.as_bool` - convert to `bool`, or return default
- {meth}`~pikepdf.Object.as_float` - convert to `float`, or return default
- {meth}`~pikepdf.Object.as_decimal` - convert to `Decimal`, or return default
- {meth}`~pikepdf.Object.as_dict` - as a `Dictionary`/mapping, or return
  default; raises `TypeError` (not `PdfError`) if the object is not a
  dictionary (for a stream, use `stream.stream_dict.as_dict()`)
- {meth}`~pikepdf.Object.as_list` - as an `Array`/list, or return default;
  raises `TypeError` if the object is not an array

:::{versionchanged} 10.14
`as_dict()` and `as_list()` now accept a `default` argument and raise
`TypeError` on a type mismatch (previously `PdfError`, and no `default`
parameter existed).
:::

#### Lenient coercion with `coerce=True`

By default the `as_*` accessors are strict: they only succeed on the exact
PDF type they name (plus a default). Real PDFs, especially malformed ones,
often encode a value using a "nearby" type — a boolean written as the
integer `0`/`1`, a number written as a string in exponential notation. Pass
`coerce=True` to `as_int`, `as_bool`, `as_float`, or `as_decimal` to accept
these:

- `as_int(coerce=True)` — also accepts a `Real` (truncated toward zero, like
  `int()`) and a numeric `String` (parsed as an integer if the text is
  exactly integral, otherwise via a floating-point parse).
- `as_bool(coerce=True)` — also accepts an `Integer` or `Real`, true iff
  nonzero.
- `as_float(coerce=True)` and `as_decimal(coerce=True)` — also accept an
  `Integer` and a numeric `String`, including exponent notation such as
  `"1e-5"`.

```python
>>> d = pikepdf.Dictionary(Marked=1, X=pikepdf.String("1e-5"))
>>> d.get_raw('/Marked').as_bool(coerce=True)  # accept 0/1
True
>>> d.get_float('/X', coerce=True)
1e-05
```

`coerce=True` does not widen the *failure* mode: a value that is not
convertible under any of these rules still returns the default (or raises
`TypeError` with no default), it just widens which stored types are
accepted. A value too large for a 64-bit integer is handled the same way:
`as_int(coerce=True)` raises `OverflowError` when no default is given, and
returns the supplied default when there is one.

### Arithmetic and comparisons with scalar types

{class}`pikepdf.Integer` and {class}`pikepdf.Real` support the arithmetic
operators (`+`, `-`, `*`, `/`, `//`, `%`, `**`, unary `-`, `abs()`) and the
ordering comparisons (`<`, `<=`, `>`, `>=`) with each other and with Python
`int`, `float`, `bool` and `Decimal` operands. The result is always a native
Python number, of the same type that implicit mode would have produced:

```python
>>> with pikepdf.explicit_conversion():
...     d = pikepdf.Dictionary(Value=10, Scale=pikepdf.Real('2.5'))
...     d.Value + 5             # 15 (int)
...     d.Value + 2.5           # 12.5 (float)
...     d.Value / 4             # 2.5 (float, true division)
...     d.Value // 3            # 3 (int, floor division)
...     d.Scale * d.Value       # Decimal('25.0')
...     d.Scale + 1             # Decimal('3.5')
...     d.Scale + 1.5           # 4.0 (float)
...     d.Scale > d.Value       # False
```

An `Integer` behaves like an `int`. A `Real` behaves like the
{class}`~decimal.Decimal` of its token text, exact and lossless, so
`Real('0.1') + Real('0.2') == Decimal('0.3')`; the one exception is a `float`
operand, which `Decimal` would refuse, so a `Real` combined with a `float`
gives a `float`. Errors are Python's own: `ZeroDivisionError` for division by
zero, and `TypeError` for a non-numeric object or operand.

This means a quick script can compute `page.MediaBox[2] - page.MediaBox[0] > 100`
under explicit mode without unboxing anything, and receives a `TypeError`
rather than a silently wrong answer if the PDF stored something other than a
number there. Careful code should still use the `as_*` accessors or the
`get_*` getters to unbox, coerce, and handle a wrong type deliberately.

### Unboxing a value of unknown numeric type

The `as_*` accessors require knowing which PDF type a value has. Where a
value may be any of `Integer`, `Boolean` or `Real`, and may already be a
native value because the code also runs under implicit mode,
{func}`pikepdf.unbox` returns the native Python value in either mode and
passes anything else through unchanged:

```python
>>> with pikepdf.explicit_conversion():
...     d = pikepdf.Dictionary(MaxLen=12, Marked=True, Scale=pikepdf.Real('2.5'))
...     [pikepdf.unbox(v) for v in (d.MaxLen, d.Marked, d.Scale, d)]
[12, True, Decimal('2.5'), pikepdf.Dictionary(...)]
```

Because arithmetic and comparisons already produce native results, `unbox`
is only needed at the boundaries where Python offers no protocol for a
foreign number: `isinstance` checks against `int`/`bool`/`Decimal`,
identity checks such as `x is True`, `Decimal(x)`, `json.dumps`, and a
function documented to return a native type.

For convenience, the `repr()` of a `pikepdf.Object` will display a
Python expression that replicates the existing object (when possible), so it
will say:

```python
>>> catalog_name = pdf.Root.Type
pikepdf.Name("/Catalog")
>>> isinstance(catalog_name, pikepdf.Name)
True
>>> isinstance(catalog_name, pikepdf.Object)
True
```

`repr()` honors the effective conversion mode of the object being displayed
(context manager, then the object's own `Pdf`, then the global setting), so a
document opened with `conversion_mode='explicit'` shows `pikepdf.Integer(5)`
rather than `5` even if the global mode is implicit.

:::{versionchanged} 10.14
`bool()` on a `pikepdf.Integer` or `pikepdf.Real` now returns the truth value
of the number (`bool(pikepdf.Integer(0))` is `False`), rather than raising
`NotImplementedError`.
:::

### Migrating to explicit mode

Switching a codebase from implicit to explicit conversion (whether via the
global setting, a per-document mode, or the context manager) is a **breaking
change** for code that was written assuming native Python scalars, and some
of the breakage is silent rather than an exception. Before flipping the
default, check for:

- **`isinstance(x, int | bool | Decimal)` silently becomes `False`.** This is
  the most dangerous case: no exception is raised, so a guard clause written
  this way (for example `if not isinstance(value, int): return None`) simply
  takes the wrong branch on every explicit-mode value. Search for
  `isinstance` checks against `int`, `bool`, or `Decimal` on anything that
  might be a pikepdf object, and replace them with `as_int`/`as_bool`/
  `as_decimal`/`get_int`/etc., or with `isinstance(x, pikepdf.Integer)` and
  friends if you specifically need to detect the PDF type.
- **`x is True` / `x is False` silently becomes `False`.** A `Boolean` can
  never be identical to a Python `bool`. Use `get_bool`/`as_bool`, or
  compare with `==`.
- **Arithmetic, comparisons, `str()`, `hash()`, `int()`, `float()` and
  `bool()` keep working**, with the same results as implicit mode, so
  expressions such as `mediabox[2] - mediabox[0]` need no change.
- **`Decimal(x)`** of a `Real` raises `TypeError`, since `Decimal` accepts
  only its own inputs. Use `as_decimal()` or {func}`pikepdf.unbox`.
- **`json.dumps()`** of a scalar raises `TypeError`, since the standard
  library does not know how to serialize a `pikepdf.Object`.
- **Functions documented to return `int`, `bool` or `Decimal`** now return an
  object unless they unbox. A `cast(Decimal, obj)` that a type checker
  accepted was hiding exactly this; replace it with `unbox` or a typed getter.

Prefer the mode-independent `as_*` accessors, the `get_*`/`get_raw`
container methods described above, and {func}`pikepdf.unbox` for any code
that must work regardless of mode. When you do switch a mode, run your test suite once with
`pikepdf.set_object_conversion_mode('explicit')` in effect (or wrap the
relevant tests in {func}`pikepdf.explicit_conversion`) to catch call sites
that assumed implicit conversion.

pikepdf intends to make explicit conversion the default in a future major
release. New code that reads values of uncertain type should prefer the
mode-independent getters (`get_raw`, `get_int`, `get_bool`, `get_float`,
`get_decimal`, `get_dict`, `get_list`) so it is unaffected by that change.

## Making PDF objects

You may construct a new object with one of the classes:

- {class}`pikepdf.Array`
- {class}`pikepdf.Dictionary`
- {class}`pikepdf.Name` - the type used for keys in PDF Dictionary objects
- {class}`pikepdf.String` - a text string
  (treated as `bytes` and `str` depending on context)
- {class}`pikepdf.Integer` - a PDF integer (explicit mode)
- {class}`pikepdf.Boolean` - a PDF boolean (explicit mode)
- {class}`pikepdf.Real` - a PDF real/floating-point number (explicit mode)

These may be thought of as subclasses of `pikepdf.Object`. (Internally they
**are** `pikepdf.Object`.)

There are a few other classes for special PDF objects that don't
map to Python as neatly.

- `pikepdf.Operator` - a special object involved in processing content
  streams
- `pikepdf.Stream` - a special object similar to a `Dictionary` with
  binary data attached
- `pikepdf.InlineImage` - an image that is embedded in content streams

The great news is that it's often unnecessary to construct `pikepdf.Object`
objects when working with pikepdf. Python types are transparently *converted* to
the appropriate pikepdf object when passed to pikepdf APIs – when possible.
However, pikepdf sends `pikepdf.Object` types back to Python on return calls,
in most cases, because pikepdf needs to keep track of objects that came from
PDFs originally.

## Working with Arrays

`pikepdf.Array` objects implement the standard Python {class}`list` interface,
supporting indexing, slicing (including `del` on slices), and iteration.

### List methods

The following methods modify a pikepdf array in-place:
`append()`, `extend()`, `insert()`, `pop()`, `remove()`, `clear()`, and `reverse()`.

You can also use `count()`, `index()`, and `copy()`.

```{note}
**Shallow vs Deep Copy**: While `copy()` is a shallow copy of the handle,
PDF "direct objects" (those without an object number) behave like values.
Modifying a direct object inside a copied array will not affect the original.
For "indirect objects," standard shallow copy behavior applies.
```

`pikepdf.Array` does not implement `sort()`. Instead you can use the pattern

```python
sorted_pikepdf_array = pikepdf.Array(sorted(original_pikepdf_array))
```

## Accessing nested objects

For accessing deeply nested structures, {class}`pikepdf.NamePath` provides
ergonomic syntax with helpful error messages. See
{ref}`Accessing nested objects with NamePath <namepath>` for details.

## Object lifecycle and memory management

As mentioned above, a {class}`pikepdf.Object` may reference data that is lazily
loaded from its source {class}`pikepdf.Pdf`. Closing the `Pdf` with
{meth}`pikepdf.Pdf.close` will invalidate some objects, depending on whether
or not the data was loaded, and other implementation details that may change.
Generally speaking, a {class}`pikepdf.Pdf` should be held open until it is no
longer needed, and objects that were derived from it may or may not be usable
after it is closed.

Simple objects (booleans, integers, decimals, `None`) are copied directly
to Python as pure Python objects.

For PDF stream objects, use {meth}`pikepdf.Object.read_bytes()` to obtain a
copy of the object as pure bytes data, if this information is required after
closing a PDF.

When objects are copied from one {class}`pikepdf.Pdf` to another, the
underlying data is copied immediately into the target. As such it is possible
to merge hundreds of `Pdf` into one, keeping only a single source at a time and the
target file open.

## Indirect objects

PDF has two ways to represented a PDF dictionary that contains another dictionary:
it can contain the inner dictionary, or provide a reference to another object.
In the PDF file itself, most objects have an object number that is for referencing.

pikepdf hides the details about whether an object is directly or indirectly
referenced, since in many situations it does not matter and manually testing each
object to see if it needs to be dereferenced before accessing it is tedious.
However, you may need to create indirect references. Sometimes, the {{ pdfrm }}
specifically requires that a value be an indirect object.

You can use {attr}`pikepdf.Object.is_indirect` to check if an object is actually
an indirect reference. If you require an indirect object, use
{meth}`pikepdf.Pdf.make_indirect` to attach the dictionary to a `Pdf` and return
an indirect copy of it. Direct objects are not attached to any particular `Pdf`
and can be copied from one to another, just like scalars. Indirect objects
must be attached.

Stream objects are always indirect objects, and must always be attached to a
PDF.

## Object helpers

pikepdf also provides {class}`pikepdf.ObjectHelper` and various subclasses of
this class. Usually these are wrappers around a {class}`pikepdf.Dictionary` with
special rules applicable to that type of dictionary. {class}`pikepdf.Page` is
an example of an object helper. The underlying object can be accessed with
{attr}`pikepdf.ObjectHelper.obj`.
