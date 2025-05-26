# v7.2.0

- Improved Object.repr() to avoid printing the entire contents of large object trees
  such as those in PDFs with structural element trees.
- Fixed typing of NumberTree.
- Improved matrix documentation, interoperability with numpy, and added matrix inverse.
- Documentation improvements.

# v7.1.2

- Fixed possible segfault if a PDF is opened and accessed without being assigned to a
  variable. {issue}`465`

# v7.1.1

- Add workaround to fix release issue on manylinux-aarch64.
- Improved documentation of Pdf.check().

# v7.1.0

**New features**

- `PdfMetadata.register_xml_namespace` allows registering new XML namespaces for
  PDFs with more complex XMP metadata. {issue}`436`
- The list of XMP namespaces registered by default was expanded to include several
  more common namespaces. {issue}`436`
- Fixed issues creating TIFF images with CCITT Group 3. {issue}`437,401`
- Updated README. {issue}`432`
- Note: due to what is believed to be a change in a third party dependency, the
  manylinux-aarch64 image for this release failed to build. As such, this particular
  wheel is not available.

# v7.0.0

pikepdf 7 introduces a subtle change to how it holds objects from the libqpdf C++ library:
dependent objects no longer keep their parent alive.

The main consequence is that constructs such as the following

```python
def make_obj_and_return():
    pdf = pikepdf.new()
    obj = pdf.make_stream(b'some data')
    return obj

...
obj = make_obj_and_return()
obj.read_bytes()
```

will not work as previously - `obj.read_bytes()` will return a
`DeletedObjectError`, an exception that now occurs when accessing an object that was
garbage collected.

In the vast majority of cases, no changes are needed. In most cases, a `with` block
surrounding access to an opened pikepdf will be sufficient to ensure any objects
from that PDF are kept alive.

The benefits to pikepdf from this change are considerable. Reference counting is
simplified and some possible memory leaks or circular references are avoided. In many
cases, where pikepdf previously used a C++ shared_ptr, it can now used a
lighterweight unique_ptr.

**Breaking changes**

- Support for Python 3.7 is dropped.
- Child objects no longer keep their source Pdf alive, as outlined above.
- libqpdf 11.2.0 or newer is required.
- The C++ binding layer has been renamed from `pikepdf._qpdf` to `pikepdf._core`.
  This has always been a private API but we are making note of the change anyway.
  For the moment, a Python module named `_qpdf` still exists and imports all of the
  modules in `_core`. This compatibility shim will be removed in the next major
  release.

**New features**

- Added Page.form_xobjects, which returns all Form XObjects that are used in a page.
- Accessing Page.resources will now create an empty /Resources dictionary is none
  previously existed.

**Fixes**

- Fixed an issue with extracting images that were compressed with multiple compression
  filters that also had custom decode parameters.

**Packaging changes**

- setuptools >= 61 is now required, since we use pyproject.toml and have discarded
  setup.cfg.
- We now include manylinux's libjpeg-turbo instead of compiling libjpeg.
