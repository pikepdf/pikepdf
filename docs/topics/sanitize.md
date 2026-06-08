(sanitize)=

# Sanitizing PDFs

:::{versionadded} 10.9
:::

If you accept PDFs from untrusted sources, you may want to strip out active or
risky content before processing or redistributing them. pikepdf can be one layer
in such a pipeline.

There is no universal notion of a "safe" PDF. **What to sanitize depends entirely
on your use case and threat model.** Many of the advanced features people are
tempted to strip — interactive forms, embedded files, annotations — are used to
do real work, so removing them indiscriminately breaks documents that other users
care about. Decide what you are defending against, and what you are willing to
break, before reaching for any of these tools.

pikepdf provides a small set of curated, low-risk helpers in the
{mod}`pikepdf.sanitize` module. Each performs one narrowly scoped operation and
leaves the standard page content, page geometry, and document metadata untouched.

## Removing JavaScript

PDFs can carry JavaScript that runs when the document is opened, when a page is
viewed, or when a form field changes. The main legitimate use is interactive form
validation. Most PDF viewers other than Adobe Acrobat do not fully execute PDF
JavaScript, and typically warn about or disable it.

{func}`pikepdf.sanitize.remove_javascript` purges the document-level JavaScript
name tree and every JavaScript action, wherever it is reachable — including from
the document catalog, pages, annotations, form fields, and outline (bookmark)
items, and including actions chained via `/Next`:

```{eval-rst}
.. doctest::

    >>> import pikepdf

    >>> pdf = pikepdf.open('../tests/resources/pal.pdf')

    >>> pikepdf.sanitize.remove_javascript(pdf)
```

This may break form validation. Because many PDF viewers don't implement JavaScript, even PDFs that use it are typically designed to function and display correctly without it. JavaScript can alter the appearance of a PDF.

## Removing embedded files

PDFs can embed arbitrary files (attachments). These are sometimes integral to the
document — for example in some digital-signing workflows — so remove them
deliberately, not reflexively.

{func}`pikepdf.sanitize.remove_attachments` clears the embedded files, removes
`/AF` (associated files) references, and defangs FileAttachment annotations by
removing their embedded file while keeping the annotation in place (so page
geometry is unchanged):

```{eval-rst}
.. doctest::

    >>> pikepdf.sanitize.remove_attachments(pdf)
```

## Removing external access

A PDF can contain actions that reach out to the network or filesystem: URI links,
`Launch` actions that start an external program, `GoToR` (remote go-to), `GoToE`
(embedded go-to, which opens content in an embedded file), `SubmitForm`, and
`ImportData`. URI actions are usually benign hyperlinks, so this is a separate
opt-in.

{func}`pikepdf.sanitize.remove_external_access` removes all of these actions,
wherever they are reachable (document, pages, annotations, form fields, and
outline items). Link annotations are kept — so any visible underline or box is
preserved — but their triggering action is removed, rendering them inert:

```{eval-rst}
.. doctest::

    >>> pikepdf.sanitize.remove_external_access(pdf)
```

## Removing thumbnails

A PDF may store a small preview image (`/Thumb`) for each page. Viewers can
regenerate these on the fly, so removing them is safe. Doing so reduces file
size and avoids *stale* thumbnails — some editors fail to keep them in sync with
edited pages, so a thumbnail can leak the prior appearance of a page you
intended to change or redact.

{func}`pikepdf.sanitize.remove_thumbnails` deletes the thumbnail from every
page:

```{eval-rst}
.. doctest::

    >>> pikepdf.sanitize.remove_thumbnails(pdf)
```

## Removing an embedded search index

Adobe Acrobat can embed a full-text search index in a document to speed up
searching. It is stored as a `/SearchIndex` entry in the catalog's `/PieceInfo`
dictionary, and is ignored by non-Acrobat viewers. Like thumbnails, an embedded
index can fall out of sync with the document and leak content you intended to
edit or redact; it also reduces file size to drop it and re-enables Fast Web
View (which an embedded index precludes).

{func}`pikepdf.sanitize.remove_search_index` removes the index; its data streams
become unreferenced and are dropped when you save:

```{eval-rst}
.. doctest::

    >>> pikepdf.sanitize.remove_search_index(pdf)
```

## Removing multimedia and rich-media content

PDFs can embed sound, video, Flash, and 3D (U3D/PRC) content, played through
`Screen`, `Movie`, `Sound`, `RichMedia`, and `3D` annotations and driven by
`Rendition`, `Movie`, `Sound`, and `RichMediaExecute` actions. These handlers
have historically been a source of parser vulnerabilities, and the underlying
media can reference external URLs or files. `Sound` and `Movie` are deprecated
in PDF 2.0.

{func}`pikepdf.sanitize.remove_multimedia` neutralizes the multimedia actions,
drops the document-level `/Renditions` name tree, and defangs media-bearing
annotations by stripping their media references — the annotation rectangle is
kept so page geometry is unchanged:

```{eval-rst}
.. doctest::

    >>> pikepdf.sanitize.remove_multimedia(pdf)
```

## Removing Web Capture information

When Adobe Acrobat captures content from the web, it records a `/SpiderInfo`
dictionary in the catalog holding the source URLs and capture settings. This
provenance is invisible in the rendered document but can leak where the content
came from. {func}`pikepdf.sanitize.remove_web_capture` deletes it:

```{eval-rst}
.. doctest::

    >>> pikepdf.sanitize.remove_web_capture(pdf)
```

## Removing private application data

PDF processors can stash private, application-specific data in `/PieceInfo`
page-piece dictionaries — for example, an editor's own editable representation of
a page. Like thumbnails and search indexes, this data can fall out of sync with
the visible document and leak content you intended to edit or redact. Removing it
does not change how the document renders, but applications that wrote it lose
their private editing state.

{func}`pikepdf.sanitize.remove_private_app_data` removes every `/PieceInfo`
dictionary, at both the document and page level. It is a broader version of
`remove_search_index` (which removes only the catalog's `/SearchIndex` entry):

```{eval-rst}
.. doctest::

    >>> pikepdf.sanitize.remove_private_app_data(pdf)
```

## Removing a PDF portfolio view

A *PDF portfolio* (or package) is a document whose embedded files are presented
through a navigator UI, configured by a `/Collection` dictionary in the catalog.
{func}`pikepdf.sanitize.remove_collection` removes that dictionary, so the
document is presented as an ordinary PDF showing its cover sheet. This does
**not** remove the embedded files themselves — pair it with `remove_attachments`
for that, and with `remove_javascript`, since a portfolio's navigator can be
driven by JavaScript:

```{eval-rst}
.. doctest::

    >>> pikepdf.sanitize.remove_collection(pdf)
```

## Chaining operations

If you apply several of these operations together, {class}`pikepdf.sanitize.Sanitizer`
offers a fluent alternative to calling the functions one at a time. You record
the operations by chaining `remove_*` methods, then call `apply()` on a PDF.
This lets you configure a sanitizer once and reuse it across many documents, and
it coalesces the action-based removals (JavaScript, external access) into a
single pass over the document:

```{eval-rst}
.. doctest::

    >>> scrubber = (
    ...     pikepdf.sanitize.Sanitizer()
    ...     .remove_javascript()
    ...     .remove_external_access()
    ...     .remove_attachments()
    ... )

    >>> pdf = pikepdf.open('../tests/resources/pal.pdf')

    >>> sanitized = scrubber.apply(pdf)
```

`apply()` returns the same PDF, so you can chain straight into a save, and a
single `Sanitizer` can be applied to file after file:

```python
scrubber = pikepdf.sanitize.Sanitizer().remove_javascript().remove_attachments()
for path in untrusted_paths:
    with pikepdf.open(path) as pdf:
        scrubber.apply(pdf).save(out_dir / path.name)
```

By design there is no "remove everything" method — blanket removal of forms,
annotations, or XFA usually destroys legitimate content (see below).

## What not to strip blindly

The ChatGPT-style "sanitizers" circulating online often go much further, and in
doing so destroy legitimate content. pikepdf deliberately does **not** offer
one-click equivalents for the following, because they are usually the wrong thing
to do:

:::{warning}
- **XFA forms.** XFA is a deprecated, Adobe-only form technology, but the form's
  contents live inside the XFA packet. Removing XFA typically reduces the document
  to a single blank page with an error message — destroying everything the
  document was for.
- **All annotations / the whole AcroForm.** Wholesale removal discards links,
  comments, and every form field, not just the risky parts. Prefer the targeted
  helpers above.
- **The document `/ID`.** Erasing the trailer `/ID` does not improve security;
  pikepdf will simply generate a new one when saving.
:::

## Flattening dynamic content with OCR

The helpers above are surgical: they remove specific structures while leaving the
rest of the document as-is. If instead you want to strip out *essentially all*
dynamic and interactive content in one pass — and you can accept rendering the
document down to images — a middleweight option is to rasterize every page and
rebuild a fresh PDF with a clean OCR text layer using
[OCRmyPDF](https://ocrmypdf.readthedocs.io/) (which is built on pikepdf):

```bash
ocrmypdf --force-ocr input.pdf output.pdf
```

`--force-ocr` rasterizes all pages to images and then re-OCRs them. In the
process it discards JavaScript, embedded files, form fields, annotations, the
original (possibly inaccurate or maliciously crafted) text layer, and any
hidden or off-page content — because none of it survives the trip through a
bitmap. The output contains the visible appearance of each page plus a freshly
generated, searchable text layer.

The trade-off is that the text layer is now only as accurate as OCR, vector text
becomes a raster image (larger files, no longer perfectly sharp), and genuinely
interactive features are gone. But for "I want this PDF to be inert and contain
nothing but what a human can see on the page," this is often the cleaner road
than trying to enumerate and remove every kind of active content by hand.

## Scrubbing metadata

To remove personal information from metadata, do **not** blindly delete the
DocumentInfo dictionary and the XMP metadata stream — they are redundant and must
be kept in sync. Use pikepdf's coordinated metadata API instead, which edits both:

```python
with pikepdf.open(...) as pdf, pdf.open_metadata(set_pikepdf_as_editor=False) as meta:
    del meta['dc:creator']
```

By default, {meth}`pikepdf.Pdf.save` and {meth}`pikepdf.Pdf.open_metadata` record
pikepdf as the document's producer/most-recent editor. This is a courtesy to other
PDF developers that helps with tracking down bugs. Pass
`set_pikepdf_as_editor=False` to {meth}`pikepdf.Pdf.open_metadata` to suppress it.
See {ref}`metadata` for the full metadata API.

## The limits of programmatic redaction

:::{warning}
**pikepdf cannot reliably redact text or images from a PDF, and neither can any
purely programmatic tool that operates on the file's structure.**
:::

Removing a visible word from a page is far harder than it looks. Text in a PDF
can be:

- split across many drawing operators, so the string you are searching for never
  appears contiguously;
- drawn and then hidden by a clipping path, an overlapping white rectangle, or
  pushed off the visible page — visually gone but still in the byte stream;
- duplicated in an **invisible OCR text layer** placed behind a scanned image;
- duplicated in an **embedded search index** (tools such as Acrobat can build
  these to speed up searching);
- present in page thumbnails, form XObjects, or alternate representations.

pikepdf works on PDF *structure*, not rendered *appearance*, so it cannot
guarantee that a phrase is gone from every place it might be stored.

For genuine redaction:

- Use a graphical PDF editor with a dedicated **redaction** tool, which removes
  the underlying content rather than merely drawing a black box over it. Then
  verify the result by searching and by inspecting any OCR layer.
- For **truly sensitive** documents, redact **physically**: print the document,
  black out the sensitive parts with a marker, then scan (and, if needed, OCR) the
  result. This severs any digital link to the original bytes.

## Defense in depth

pikepdf is one layer, not a complete solution. For untrusted input, combine it
with other measures appropriate to your threat model: malware scanning, rendering
the PDF to images and rebuilding it, sandboxing, and size/structure limits. And
always validate the result against the threat you are actually trying to defend
against.

See also {ref}`security` for notes on PDF password security and content
restrictions.
