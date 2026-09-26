(pdfa)=

# PDF/A validation and repair

:::{versionadded} 10.14
:::

PDF/A (ISO 19005) is the archival subset of PDF. The {mod}`pikepdf.pdfa`
module can prepare a document for PDF/A, check whether it would conform when
saved, and save it with a guarantee that the bytes written were validated.

## What this is, and what it is not

{mod}`pikepdf.pdfa` is an **allowlist** validator for the level B
("basic") conformance of PDF/A-1, PDF/A-2 and PDF/A-3, that is
PDF/A-1b, PDF/A-2b and PDF/A-3b. It approves a document only if every construct
it encounters is one it recognizes and knows to conform. Anything it does not
recognize is reported, rather than guessed at. A denial may therefore be a false
alarm; an approval should never be wrong.

It is not:

- **A certification.** [veraPDF] is the reference validator for PDF/A. The
  rule identifiers used here are veraPDF's, and pikepdf's validator was
  developed by comparing its verdicts with veraPDF's on the veraPDF test corpus.
  If you need an authoritative answer, use veraPDF.
- **A converter.** pikepdf repairs structure and metadata. It does not convert
  colour, embed or subset fonts, rasterize transparency, or rewrite page content.
  A document that needs any of those will not pass, and you will need a tool
  such as Ghostscript to convert it first.
- **A validator for levels A or U, or for PDF/A-4.** Only 1b, 2b and 3b are
  supported.

Constructs that PDF/A permits but that the validator does not examine are
reported as `not_checked` instead of passing. The list of such constructs is in
{ref}`pdfa-unsupported`; it will shrink over time without changes to the API.

## Installing

{mod}`pikepdf.pdfa` needs a few pure Python dependencies (jsonschema, referencing
and fontTools) that the rest of pikepdf does not. They are an optional extra:

```bash
pip install 'pikepdf[pdfa]'
```

`import pikepdf` never loads {mod}`pikepdf.pdfa` or its dependencies. The module
is imported on first use, either explicitly or as the attribute `pikepdf.pdfa`.
If the dependencies are missing, importing it raises {class}`ImportError` naming
the extra.

## Quick start

For most uses, {func}`pikepdf.pdfa.save` is the only call you need:

```python
import pikepdf
from pikepdf import pdfa

with pikepdf.open('input.pdf') as pdf:
    report = pdfa.save(pdf, 'output.pdf', '2b')

for line in report.prepared.describe():
    print(line)
```

`save` repairs what it can, writes the file, reads back what it wrote and
validates it. It returns only if the written file passed. Otherwise it raises
{class}`pikepdf.pdfa.PdfaError`, whose `report` explains why (and, as on
success, `report.prepared` records what was repaired), and the destination is
left untouched:

```python
try:
    with pikepdf.open('form.pdf') as pdf:
        pdfa.save(pdf, 'form-pdfa.pdf', '2b')
except pdfa.PdfaError as e:
    print(e.report.summary())
```

The flavour can be given as a string (`'1b'`, `'2b'`, `'3b'`) or as a
{class}`pikepdf.pdfa.Flavour`.

## Prepare, check and save

The module has three verbs, which differ in what they change and what they
promise.

{func}`pikepdf.pdfa.prepare`

: Applies repairs to the open document, in memory, and returns a
  {class}`pikepdf.pdfa.PrepareResult` recording what it changed. Calling it
  again makes no further changes. It does not validate anything. See
  {ref}`pdfa-prepare` for the list of repairs.

{func}`pikepdf.pdfa.check`

: Predicts the verdict for the file that `save` would write, without writing
  anything and without changing the document. It is pure and cheap, and returns
  a {class}`pikepdf.pdfa.Report`.

{func}`pikepdf.pdfa.save`

: Runs `prepare` (unless `repair=False`), writes the document to a temporary
  file, reopens the file and validates the bytes written, and only then moves
  it into place. It is the only call that promises anything.

Use `save` when you want a PDF/A file. Use `prepare` and `check` when you want
to know whether a document can become PDF/A, or to decide what to do before
saving, for example whether to fall back to a converter:

```{eval-rst}
.. doctest::

    >>> from pikepdf import pdfa

    >>> pdf = pikepdf.open('../tests/resources/pdfa/francais.pdf')

    >>> pdfa.check(pdf, '2b').verdict
    'fail'

    >>> result = pdfa.prepare(pdf, '2b')

    >>> result.changed
    True

    >>> report = pdfa.check(pdf, '2b')

    >>> print(report.summary())
    PDF/A-2b: pass
```

`check` describes the document **at the moment of the call**. pikepdf cannot
tell whether a document changed since it was checked, so a stored report is
only a hint. In particular, run `check` after your last metadata edit:
{meth}`pikepdf.Pdf.open_metadata` writes the XMP packet when its context
manager exits, not while you are editing.

```python
with pikepdf.open('input.pdf') as pdf:
    pdfa.prepare(pdf, '2b')
    with pdf.open_metadata() as meta:
        meta['dc:title'] = 'Un document en français'
    report = pdfa.check(pdf, '2b')  # after the metadata was written
    if report.passed:
        pdfa.save(pdf, 'output.pdf', '2b')
```

`check` is advisory. If you save the document yourself with
`pdf.save(path, **report.save_kwargs)`, the file should get the same verdict,
but nothing verifies that it does. {func}`pikepdf.pdfa.validate_written`
validates a file that is already written, if you need to confirm it.

## Verdicts and findings

A {class}`pikepdf.pdfa.Report` has a `verdict` with one of three values:

`'pass'`
: Nothing was found that prevents approval.

`'fail'`
: At least one finding is a **violation**: a construct that breaks PDF/A.

`'not_checked'`
: There are findings, but all of them are constructs the validator does not
  check (**unsupported**). The document may well be valid PDF/A; pikepdf cannot
  say. `save` treats this like `'fail'` and raises.

`report.passed` is true only for `'pass'`. `report.violations` and
`report.unsupported` split the findings by kind.

Each {class}`pikepdf.pdfa.Finding` is a named tuple of `rule`, `where`,
`message` and `kind` (`'violation'` or `'unsupported'`):

```{eval-rst}
.. doctest::

    >>> pdf = pikepdf.open('../tests/resources/pdfa/francais.pdf')

    >>> report = pdfa.check(pdf, '2b')

    >>> finding = report.violations[0]

    >>> finding.rule
    'ISO_19005_2:6.2.4.3-4'

    >>> finding.kind
    'violation'

    >>> print(finding)
    [violation] ISO_19005_2:6.2.4.3-4 at obj 10 0 (Page) content Do /Im0: DeviceGray used without a PDF/A OutputIntent
```

Rule identifiers follow these conventions:

- `ISO_19005_2:6.2.8-3`: a veraPDF rule, named by the part of ISO 19005
  (`ISO_19005_1` for PDF/A-1, `ISO_19005_2` and `ISO_19005_3` for the others),
  the clause and veraPDF's test number. The rule's description is in the
  [veraPDF validation profiles](https://github.com/veraPDF/veraPDF-validation-profiles).
- `pikepdf:<name>`: a local policy, or a construct the validator does not
  support, such as `pikepdf:shading` or `pikepdf:pattern`.
- `pikepdf:schema-<Role>`: a key or value the validator does not recognize in
  an object of a particular role, such as `pikepdf:schema-Page` for an unknown
  key in a page dictionary. PDF permits private and future keys, so these are
  usually unsupported rather than violations. They are violations only where
  PDF/A itself forbids unlisted keys.
- `pikepdf:internal`: an unexpected error while checking. Problems with the
  document never raise from `check`; they become findings like this one.

`report.summary()` gives a readable description, listing up to 20 findings by
default:

```text
PDF/A-2b: not_checked (0 violation(s), 5 unsupported)
  [unsupported] pikepdf:colour-space at obj 8 0 (Page) content cs /Pattern: pattern colour is not supported
  [unsupported] pikepdf:pattern at obj 8 0 (Page) content: scn with a pattern /p5
  [unsupported] pikepdf:shading at obj 8 0 (Page) content: shadings (sh) are not supported
  [unsupported] pikepdf:schema-Resources at obj 2 0 (Resources) /Pattern: patterns are not supported
  [unsupported] pikepdf:schema-Resources at obj 2 0 (Resources) /Shading: shadings are not supported
```

## Output intents

PDF/A requires an output intent, an ICC profile that says how device colours
are to be interpreted. `prepare` and `save` install one, replacing any output
intents the document had:

- `output_intent='sRGB'` (the default) installs the sRGB profile shipped with
  pikepdf.
- `output_intent=<bytes>` installs the ICC profile you supply: an RGB, CMYK or
  gray output profile. PDF/A-1 requires an ICC version 2 profile; PDF/A-2 and
  PDF/A-3 accept up to version 4. An unusable profile raises
  {class}`ValueError` before the document is changed.
- `output_intent=None` keeps the document's output intents as they are.

`output_condition_identifier` sets the intent's `/OutputConditionIdentifier`.
It defaults to `'sRGB'` for the built-in profile, and otherwise to the
profile's description.

```python
with open('press.icc', 'rb') as f:
    icc = f.read()

with pikepdf.open('input.pdf') as pdf:
    report = pdfa.save(
        pdf, 'output.pdf', '2b',
        output_intent=icc, output_condition_identifier='Press',
    )
print(report.output_intent)  # 'CMYK' for a CMYK profile
```

`report.output_intent` is the colour space of the document's PDF/A output
intent (`'RGB'`, `'CMYK'` or `'GRAY'`) as the validator found it, and
`result.output_intent` on a `PrepareResult` is the colour space of the intent
that was requested. The validator checks that device colours used in the
document are compatible with it; it does not convert them.

## Save settings

Some {meth}`pikepdf.Pdf.save` settings change the written bytes in ways that
would make a verdict meaningless, or produce files PDF/A forbids. The PDF/A
functions therefore **pin** them, and refuse a conflicting value with
{class}`ValueError`. Passing a pinned setting with its pinned value is allowed.

| Setting | Pinned value | Reason |
| --- | --- | --- |
| `preserve_pdfa` | `True` | the PDF/A version constraints must be kept |
| `encryption` | `None` | PDF/A forbids encryption |
| `qdf` | `False` | QDF mode writes uncompressed, annotated output |
| `normalize_content` | `False` | it rewrites content streams after the check |
| `stream_decode_level` | `StreamDecodeLevel.generalized` | the validator evaluates filters as qpdf rewrites them at this level |
| `fix_metadata_version` | `False` | it rewrites the XMP packet after the check |

For PDF/A-1, which is based on PDF 1.4, two more are pinned:

| Setting | Pinned value | Reason |
| --- | --- | --- |
| `object_stream_mode` | `ObjectStreamMode.disable` | PDF 1.4 has no object streams |
| `force_version` | `'1.4'` | PDF/A-1 is based on PDF 1.4 |

`fix_metadata_version` defaults to true in {meth}`pikepdf.Pdf.save`, where it
updates the PDF version recorded in the XMP metadata while saving. That is a
change to the XMP packet made after the check, so the verdict would describe
different metadata from what was written. It is pinned to false, and `prepare`
writes the metadata the flavour needs instead.

The remaining settings are yours to choose: `compress_streams`,
`recompress_flate`, `linearize`, `progress`, `deterministic_id`, `static_id`,
`min_version`, and for PDF/A-2 and PDF/A-3 `object_stream_mode` and
`force_version`. Versions may not exceed 1.4 for PDF/A-1 or 1.7 for PDF/A-2
and PDF/A-3, and extension levels are refused. An unknown keyword raises
{class}`TypeError`.

{func}`pikepdf.pdfa.resolve_save_kwargs` returns the complete settings for a
flavour, with your choices applied, and `report.save_kwargs` holds the settings
a verdict assumed:

```{eval-rst}
.. doctest::

    >>> kwargs = pdfa.resolve_save_kwargs('2b', linearize=True)

    >>> kwargs['linearize'], kwargs['fix_metadata_version']
    (True, False)

    >>> pdfa.resolve_save_kwargs('2b', fix_metadata_version=True)
    Traceback (most recent call last):
    ...
    ValueError: fix_metadata_version=True is not allowed for PDF/A-2b: it must be False because it rewrites the XMP packet after the check
```

`pdf.save(path, **kwargs)` works directly with the result.

(pdfa-prepare)=

## What prepare changes

`prepare` changes structure and metadata, never page content. It:

- replaces the output intents with a single PDF/A output intent, unless the
  requested intent is already the only one, or `output_intent=None`;
- removes `/Interpolate` from images;
- removes annotations that are hidden, invisible or not viewable (the Hidden,
  Invisible and NoView flags, and ToggleNoView for PDF/A-2 and PDF/A-3), along
  with their popup annotations, and sets the Print flag on the annotations that
  remain;
- adds a `/CIDSet` to subset CIDFonts (PDF/A-1 only);
- rewrites the XMP metadata to keep only the properties predefined for the
  flavour, replacing a packet that cannot be read. The properties of every
  `rdf:Description` are kept when all of them have the same `rdf:about`, even a
  non-empty one such as `uuid:...` (pikepdf's own metadata editor writes one);
  when their `rdf:about` values differ, only the Descriptions with an empty
  `rdf:about` are kept. The rewritten packet has an empty `rdf:about`;
- gives document dates that have no time zone the **local time zone** of the
  machine running pikepdf;
- declares PDF/A conformance in the XMP metadata, and sets the DocInfo entries
  that have XMP equivalents to agree with the XMP;
- records pikepdf as the producer (`pdf:Producer`) and the current time as
  `xmp:MetadataDate`.

{meth}`pikepdf.pdfa.PrepareResult.describe` returns a sentence for each kind of
change, and {meth}`pikepdf.pdfa.PrepareResult.messages` the same sentences
paired with a suggested log level: `'warning'` for annotations removed,
`'info'` for Print flags set, XMP properties removed and an unreadable XMP
packet replaced (`PrepareResult.xmp_problem` says why it could not be read),
and `'debug'` for the rest. `PrepareResult.changed` is false if nothing but the
producer and metadata date was updated.

```python
import logging

log = logging.getLogger(__name__)
for level, sentence in report.prepared.messages():
    log.log(logging.getLevelName(level.upper()), sentence)
```

Removing hidden annotations and pruning XMP properties discard information. If
that matters, inspect the `PrepareResult` or call `check` first.

## Guarantees and limits

- **`save` validates the written bytes.** The report it returns always describes
  the file at the destination. On failure it raises `PdfaError`; an existing
  destination file is left unchanged and a new one is not created. A stream
  destination is written only on success. The cost is one extra parse of the
  output.
- **`check` models the writer.** qpdf changes some things between the objects in
  memory and the bytes it writes: stream filters, the trailer, the PDF version,
  encryption, the cross-reference format, and which objects are written at all
  (unreachable objects are dropped). `check` evaluates the document as it will
  be written, not as it is in memory.
- **Write-time stream failures cannot be predicted.** If a stream's data cannot
  be decoded when qpdf writes it, `check` cannot know in advance. `save` catches
  this when it validates the written file.
- **Conversion mode does not matter.** The validator and `prepare` give the
  same results whether the document is read in implicit or explicit conversion
  mode, however that mode is chosen: {func}`pikepdf.explicit_conversion`, the
  document's `conversion_mode`, or {func}`pikepdf.set_object_conversion_mode`.
  They work in explicit mode internally, switching to it for the calling
  thread only while they run.
- **Files are replaced atomically where possible.** `save` writes a temporary
  file beside the destination and renames it into place. An existing file keeps
  its permissions; a new file gets the default permissions of your umask. A
  destination that is a symbolic link is replaced by a regular file. If the
  destination's directory is not writable, the temporary file is created
  elsewhere and the verified bytes are copied into place, which is not atomic.
  To save over the input file, open it with
  `pikepdf.open(..., allow_overwriting_input=True)` and pass the same path, or
  `None`, as the destination.
- `prepare` changes the in-memory document; those changes remain whether or not
  a subsequent `save` succeeds.

(pdfa-unsupported)=

## Unsupported constructs

These constructs are reported as unsupported, so a document containing them
gets `'not_checked'` (or `'fail'`, if something else is wrong). Most are allowed
in PDF/A under conditions the validator does not yet verify.

- `/OpenAction` in the document catalog
- interactive forms (`/AcroForm`) and widget annotations
- the `/Names` dictionary, including named destinations
- Type 3 fonts
- optional content (`/OCProperties`) and marked-content properties
- patterns and shadings
- Separation and DeviceN colour spaces
- JPEG 2000 (JPX) images
- halftones
- `/Font` in graphics state parameter dictionaries (ExtGState)
- `/CIDSet` in TrueType-based CIDFont subsets
- embedded files and associated files (PDF/A-3 allows them)
- annotation types other than Text, Link, Popup and the markup annotations
- `/Metadata` streams attached to objects other than the catalog
- XMP extension schemas and `xmpMM` structures
- output intents other than sRGB are accepted, but less exercised than sRGB

## Threads

Independent {class}`pikepdf.Pdf` objects may be checked, prepared and saved
concurrently from different threads. As with the rest of pikepdf, do not modify
one `Pdf` from several threads at once.

## Credits

The validator and repairs were developed in [OCRmyPDF], which needs to know
whether its output is PDF/A before it can promise that it is, and moved to
pikepdf so that other applications can use them. Because pikepdf owns the
writer, it can validate the bytes that are actually written.

The rule catalogue is derived from the
[veraPDF validation profiles](https://github.com/veraPDF/veraPDF-validation-profiles),
Copyright © veraPDF Consortium, used under the
[Creative Commons Attribution 4.0 International License](https://creativecommons.org/licenses/by/4.0/).
The veraPDF Consortium does not endorse pikepdf or this validator.

[ocrmypdf]: https://github.com/ocrmypdf/OCRmyPDF
[verapdf]: https://verapdf.org
