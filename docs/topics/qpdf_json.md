(qpdf_json)=

# qpdf JSON

In addition to reading and writing PDF files, qpdf can represent an entire PDF as
JSON, and reconstruct a PDF from that JSON. pikepdf exposes this *qpdf JSON*
format through a small set of methods on {class}`pikepdf.Pdf`. It is a niche
feature -- most users never need it -- but it is valuable when you want to
inspect, diff, or transform a PDF with tools that understand JSON rather than
PDF's binary object syntax.

:::{important}
This is qpdf's own JSON representation of a *whole PDF file*, not a general PDF
interchange standard. The format is specific to qpdf and is documented in full in
the qpdf manual under [qpdf JSON](https://qpdf.readthedocs.io/en/stable/json.html).
pikepdf reads and writes **version 2** of the format (`qpdf --json-output` /
`--json-input`), introduced in qpdf 11.

Do not confuse it with the *QPDFJob JSON format*, which describes an *operation*
to perform (see {ref}`jobs`), nor with {meth}`pikepdf.Object.to_json`, which
serializes a *single object*. qpdf JSON serializes the complete document --
every object, the trailer, and optionally the stream data.
:::

## Writing qpdf JSON

{meth}`pikepdf.Pdf.write_qpdf_json` serializes the open PDF to a filename or
writable binary stream:

```python
import pikepdf

with pikepdf.open('input.pdf') as pdf:
    pdf.write_qpdf_json('input.json')
```

The result is a JSON document whose top level describes the qpdf and PDF
versions, the trailer, and a dictionary of every object in the file keyed by its
object/generation number. This is the same output as `qpdf --json-output
input.pdf input.json`.

### Controlling stream data

Stream objects (image data, content streams, fonts, and so on) hold arbitrary
binary data that does not fit naturally into JSON. {class}`pikepdf.JSONStreamData`
controls how that data is represented:

- {attr}`~pikepdf.JSONStreamData.inline` (the default) embeds each stream's data
  directly in the JSON as a base64 string. The JSON is self-contained but can be
  large.
- {attr}`~pikepdf.JSONStreamData.file` writes each stream to a separate sidecar
  file named `{file_prefix}-{object_number}`, keeping the JSON itself small and
  text-friendly.
- {attr}`~pikepdf.JSONStreamData.none` omits stream data entirely -- useful when
  you only care about the document's structure.

```python
from pikepdf import JSONStreamData

with pikepdf.open('input.pdf') as pdf:
    # Structure only, no binary blobs
    pdf.write_qpdf_json('structure.json', json_stream_data=JSONStreamData.none)

    # Streams written alongside as input-1, input-2, ...
    pdf.write_qpdf_json(
        'input.json',
        json_stream_data=JSONStreamData.file,
        file_prefix='input',
    )
```

The `decode_level` argument controls how much qpdf uncompresses stream data
before encoding it. The default, {attr}`pikepdf.StreamDecodeLevel.generalized`,
makes streams more readable; pass {attr}`pikepdf.StreamDecodeLevel.none` to
preserve the stored bytes exactly.

## Reading qpdf JSON

{meth}`pikepdf.Pdf.from_qpdf_json` builds a brand-new {class}`pikepdf.Pdf` from a
complete qpdf JSON document:

```python
pdf = pikepdf.Pdf.from_qpdf_json('input.json')
pdf.save('roundtrip.pdf')
```

The JSON must be a complete representation of a PDF. If you have edited only part
of a document's JSON and want to apply those changes back onto an existing PDF,
use {meth}`pikepdf.Pdf.update_from_qpdf_json` instead. It overlays the objects
present in the JSON onto the open `Pdf`, leaving objects that the JSON does not
mention unchanged:

```python
with pikepdf.open('input.pdf') as pdf:
    pdf.update_from_qpdf_json('patch.json')
    pdf.save('patched.pdf')
```

This update workflow is the intended way to make targeted edits through JSON:
export the PDF (or part of it), modify the JSON with any tooling you like, and
merge the changes back.

## When to use it

qpdf JSON is worth reaching for when you want to:

- **Inspect** a PDF's structure with `jq`, a text editor, or any JSON-aware tool.
- **Diff** two PDFs meaningfully -- comparing JSON object trees is far more
  legible than comparing binary files.
- **Edit** a document with a pipeline that manipulates JSON, then round-trips
  back to PDF via `update_from_qpdf_json`.
- **Interoperate** with other software that already speaks qpdf's JSON format.

For most programmatic editing, working directly with the {class}`pikepdf.Pdf`
object model is more convenient and avoids a serialization round trip. Reach for
qpdf JSON when the JSON representation itself is the thing you want to work with.
For the precise schema, see the qpdf manual's
[qpdf JSON](https://qpdf.readthedocs.io/en/stable/json.html) chapter.
