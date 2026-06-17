(jobs)=

# Batch operations with JobBuilder

qpdf, the library pikepdf is built on, ships a powerful command line program.
Most of what that command line tool can do is exposed through qpdf's *job*
interface: a single, declarative description of an operation -- encrypt, decrypt,
merge or split pages, linearize, recompress, optimize images, manage attachments,
overlay or underlay content, and so on. pikepdf binds this as
{class}`pikepdf.Job`, and {class}`pikepdf.JobBuilder` provides a fluent, Pythonic
way to assemble one.

## When to use a job

A job is the right tool for **high-level, whole-document tasks that you might
otherwise run from the `qpdf` command line**, especially when you want to apply
the same recipe to many PDFs:

- Encrypt or decrypt a batch of files.
- Merge several PDFs, or split one into per-page files.
- Linearize ("web-optimize") or recompress files to shrink them.
- Recompress images, flatten annotations, or strip metadata across a directory.

Because a job is just a specification, it is easy to build once and run against
thousands of files. The operation runs entirely inside qpdf's optimized C++
code, with no per-object round trips into Python.

A job is **not** the right tool for surgical, object-level edits. Jobs operate at
the granularity qpdf's command line offers -- whole pages, whole documents, whole
streams. They cannot reach inside a content stream to move a single text run,
rewrite one dictionary key, splice an object graph, or make a change that depends
on inspecting the PDF's contents first. For that, open the file as a
{class}`pikepdf.Pdf` and manipulate the object model directly. The two approaches
compose: you can run a job to produce an intermediate file, then open it for
fine-grained work, or vice versa.

:::{note}
`JobBuilder` is a convenience layer. Anything it can express, you could also
express by hand-writing qpdf's job JSON and passing it to {class}`pikepdf.Job`.
The builder exists so you do not have to: it translates familiar, snake_case
Python into qpdf's camelCase JSON, and lets you describe encryption with the same
{class}`pikepdf.Permissions` and {class}`pikepdf.Encryption` models used
elsewhere in pikepdf.
:::

## A first job

Every job needs an input and an output. Methods return the builder, so calls
chain:

```python
from pikepdf import JobBuilder

JobBuilder().input('in.pdf').output('out.pdf').linearize().run()
```

This is equivalent to running `qpdf --linearize in.pdf out.pdf`.

Use {meth}`~pikepdf.JobBuilder.empty` instead of `input()` to start from a blank
PDF (the equivalent of qpdf's `--empty`), and
{meth}`~pikepdf.JobBuilder.replace_input` to overwrite the input file in place.

## Encryption

Encryption permissions in qpdf's JSON are expressed as *restrictions* with a
specialized vocabulary that differs per key length. `JobBuilder` lets you use
pikepdf's allow-oriented {class}`pikepdf.Permissions` and
{class}`pikepdf.Encryption` instead:

```python
from pikepdf import JobBuilder, Permissions

JobBuilder().input('in.pdf').output('out.pdf').encrypt(
    owner_password='secret',
    user_password='',
    allow=Permissions(extract=False, modify_annotation=False),
).run()
```

You may also pass a fully-formed {class}`pikepdf.Encryption` object positionally,
which is convenient if you already construct one elsewhere:

```python
from pikepdf import Encryption

enc = Encryption(owner='secret', user='', allow=Permissions(extract=False))
JobBuilder().input('in.pdf').output('out.pdf').encrypt(enc).run()
```

40- and 128-bit RC4 encryption are weak and additionally require
{meth}`~pikepdf.JobBuilder.allow_weak_crypto`. To go the other way and remove
encryption, use {meth}`~pikepdf.JobBuilder.decrypt`.

## Merging and splitting pages

{meth}`~pikepdf.JobBuilder.add_pages` is repeatable; each call appends a source
file (and optional page range) to the selection. The special filename `'.'`
refers to the primary input file.

```python
# Concatenate the first 5 pages of a.pdf with all of b.pdf
JobBuilder().empty().output('merged.pdf') \
    .add_pages('a.pdf', '1-5') \
    .add_pages('b.pdf') \
    .run()
```

To split a file into one output per page, use
{meth}`~pikepdf.JobBuilder.split_pages` with a `%d` placeholder in the output
filename:

```python
JobBuilder().input('book.pdf').output('page-%d.pdf').split_pages().run()
```

:::{note}
qpdf's `--pages` operation (which `add_pages` drives) is **form-aware**: when the
sources contain interactive AcroForm fields, qpdf carries them across. This makes
{class}`pikepdf.Job`/`JobBuilder` a good choice for merging whole files from
disk. For in-memory, page-level form-aware copying on a `Pdf` you are actively
editing, use {meth}`pikepdf.Pdf.add_pages_from` instead -- see
{ref}`interactive_forms`.
:::

## Compression, images and content transforms

`JobBuilder` groups qpdf's many tuning knobs into a handful of methods:

```python
JobBuilder().input('in.pdf').output('out.pdf') \
    .compress(object_streams='generate', recompress_flate=True) \
    .optimize_images(min_width=100, jpeg_quality=85) \
    .run()
```

Other transforms each have a dedicated method, including
{meth}`~pikepdf.JobBuilder.flatten_annotations`,
{meth}`~pikepdf.JobBuilder.flatten_rotation`,
{meth}`~pikepdf.JobBuilder.generate_appearances`,
{meth}`~pikepdf.JobBuilder.coalesce_contents`,
{meth}`~pikepdf.JobBuilder.externalize_inline_images`, the content-removal
helpers ({meth}`~pikepdf.JobBuilder.remove_metadata`,
{meth}`~pikepdf.JobBuilder.remove_info`,
{meth}`~pikepdf.JobBuilder.remove_acroform`,
{meth}`~pikepdf.JobBuilder.remove_structure`,
{meth}`~pikepdf.JobBuilder.remove_page_labels`), page labels
({meth}`~pikepdf.JobBuilder.set_page_labels`), version pinning
({meth}`~pikepdf.JobBuilder.min_version`,
{meth}`~pikepdf.JobBuilder.force_version`), and reproducibility helpers
({meth}`~pikepdf.JobBuilder.deterministic_id`,
{meth}`~pikepdf.JobBuilder.static_id`).

## Attachments and overlays

Attachments and overlay/underlay sections are list-valued, so their `add_*`
methods are repeatable:

```python
JobBuilder().input('report.pdf').output('out.pdf') \
    .add_attachment('data.csv', mimetype='text/csv') \
    .add_overlay('watermark.pdf', repeat='1') \
    .run()
```

## The escape hatch

`JobBuilder` covers the common options with typed methods, but qpdf has a long
tail of scalar flags. {meth}`~pikepdf.JobBuilder.set` reaches any of them using
the same snake_case-to-camelCase convention. A boolean `True` enables a flag;
any other value is stringified:

```python
JobBuilder().input('in.pdf').output('out.pdf') \
    .set(no_warn=True, keep_files_open=False) \
    .run()
```

If you pass a name that is not a recognized qpdf job option, `set()` raises
`ValueError` immediately rather than producing JSON that qpdf would reject.

## Running, building, and inspecting

There are three terminal methods:

- {meth}`~pikepdf.JobBuilder.run` builds the job, validates the configuration
  (unless `validate=False`), and runs it. It returns the underlying
  {class}`pikepdf.Job`, so you can inspect `exit_code`, `has_warnings`, and
  `encryption_status` afterwards.
- {meth}`~pikepdf.JobBuilder.build` returns the {class}`pikepdf.Job` without
  running it. qpdf validates the specification during construction.
- {meth}`~pikepdf.JobBuilder.create_pdf` runs only the first stage and returns a
  {class}`pikepdf.Pdf`, for the staged workflow where you modify the PDF and then
  call {meth}`pikepdf.Job.write_pdf`.

`JobBuilder` performs only minimal local validation; qpdf is the source of truth
and raises {class}`pikepdf.JobUsageError` (or `RuntimeError` for malformed JSON)
for invalid configurations.

To see what a builder will send to qpdf -- handy for debugging, logging, or
caching a recipe -- use {meth}`~pikepdf.JobBuilder.to_json` (a `dict`) or
{meth}`~pikepdf.JobBuilder.to_json_str` (a string):

```python
>>> JobBuilder().input('in.pdf').output('out.pdf').linearize().to_json()
{'inputFile': 'in.pdf', 'outputFile': 'out.pdf', 'linearize': ''}
```

## Relationship to the qpdf command line

A `JobBuilder` specification maps almost one-to-one onto a `qpdf` command line,
because both funnel through the same qpdf job machinery. If you already know the
`qpdf` invocation you want, you can translate it directly, or skip the builder
entirely and pass an argv list to {class}`pikepdf.Job`:

```python
from pikepdf import Job

Job(['pikepdf', '--linearize', 'in.pdf', 'out.pdf']).run()
```

(The first list element is the program-name slot, like `argv[0]`; qpdf ignores
it. This runs in-process and does not shell out to a `qpdf` binary.)

For the full catalogue of options, see qpdf's own documentation on the
[command-line tool](https://qpdf.readthedocs.io/en/stable/cli.html) and the
[QPDFJob JSON format](https://qpdf.readthedocs.io/en/stable/qpdf-job.html).
