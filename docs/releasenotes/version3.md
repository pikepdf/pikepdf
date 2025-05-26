# v3.2.0

- Fixed support for outline items that have PDF 1.1-style named destinations.
  {issue}`258, 261`
- We now issue a warning if an unnecessary password was provided when opening
  an unencrypted PDF.

# v3.1.1

- Fixed errors that occurred on `import pikepdf` for an extension module built with
  pybind11 2.8.0.

# v3.1.0

- Extraction of common inline image file formats is now supported.
- Some refactoring and documentation improvements.

# v3.0.0

## Breaking changes

- libqpdf 10.3.1 is now required and other requirements were adjusted.
- pybind11 2.7.1 is now required.
- **Improved page API.** `Pdf.pages` now returns `Page` instead of
  page object dictionaries, so it is no longer necessary to wrap page objects
  as in the previous idiom `page = Page(pdf.pages[0])`. In most cases,
  if you use the Dictionary object API on a page, it will automatically do the
  right thing to the underlying dictionary.
- **Improved content stream API.** `parse_content_stream` now returns a list of
  {class}`pikepdf.ContentStreamInstruction` or {class}`pikepdf.ContentStreamInlineImage`.
  These are "duck type"-compatible with the previous data structure but may
  affect code that strongly depended on the return types. `unparse_content_stream`
  still accepts the same inputs.
- `TokenType.name` and `ObjectType.name` were renamed to
  `TokenType.name_` and `ObjectType.name_`, respectively. Unfortunately,
  Python's `Enum` class (of which these are both a subclass) uses the `.name`
  attribute in a special way that interfered.
- Deprecated or private functions were removed:
  \- `Object.page_contents_*` (use `Page.contents_*`)
  \- `Object.images` (use `Page.images`)
  \- `Page._attach` (use the new attachment API)
  \- `Stream(obj=)` (deprecated `obj` parameter removed)
  \- `Pdf.root` (use `Pdf.Root`)
  \- `Pdf._process` (use `Pdf.open(BytesIO(...))` instead)
- {meth}`pikepdf.Page.calc_form_xobject_placement` previously returned `str` when
  it should have returned `bytes`. It now returns the correct type.
- {func}`pikepdf.open` and {func}`pikepdf.save`, and their counterparts in
  {class}`pikepdf.Pdf`, now expect keyword arguments for all except the first parameter.
- Some other functions have stricter typing, required keyword arguments, etc.,
  for clarity.
- If a calculating the `repr()` of a page, we now describe a reference to that
  page rather than printing the page's representation. This makes the output
  of `repr(obj)` more useful when examining data structures that reference
  many pages, such as `/Outlines`.
- Build scripts and wheel building updated.
- We now internally use a different API call to close a PDF in libqpdf. This
  may change the behavior of attempts to manipulate a PDF after it has been
  closed. In any case, accessing a closed file was never supported.

## New functionality

- Added {class}`pikepdf.NameTree`. We now bind to QPDF's Name Tree API, for
  manipulating these complex and important data structures.
- We now support adding and removing PDF attachments. {issue}`209`
- Improved support for PDF images that use special printer colorspaces such as
  DeviceN and Separation, and support extracting more types of images. {issue}`237`
- Improved error message when `Pdf.save()` is called on PDFs without a known
  source file.
- Many documentation fixes to StreamParser, return types, PdfImage.
- `x in pikepdf.Array()` is now supported; previously this construct raised a
  TypeError. {issue}`232`
- It is now possible to test our cibuildwheel configuration on a local machine.

## Fixes

- `repr(pikepdf.Stream(...))` now returns syntax matching what the constructor
  expects.
- Fixed certain wrong exception types that occurred when attempting to extract
  special printer colorspace images.
- Lots of typing fixes.
