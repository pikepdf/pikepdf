(structure)=

# Tagged PDF and logical structure

A *tagged* PDF carries a logical structure tree alongside its page content: a
hierarchy of headings, paragraphs, lists, tables and figures that describes what
the marks on the page mean. Screen readers and reflow use it, and extraction
tools can use its logical reading order and semantics when they are available.
Tagged structure is also a prerequisite for PDF/UA conformance.

pikepdf models the tree with {class}`pikepdf.StructTree`, which wraps the
document catalog's `/StructTreeRoot`. See {{ pdfrm }} section 14.7.

## The three things a tagged PDF needs

1. **A structure tree** of {class}`pikepdf.StructElem` nodes, rooted at
   `/StructTreeRoot`, describing the document's logical organization.
2. **Marked content** in a page's `/Contents`: the operators that render a
   paragraph are bracketed by `BDC`/`EMC` and carry a marked-content identifier
   (MCID) that is unique across the page's complete contents, even when
   `/Contents` is an array of streams. A Form XObject has an independent MCID
   space.
3. **A parent tree** mapping a page's or Form stream's `/StructParents` key and
   MCID back to the structure element that owns the sequence. Objects such as
   annotations use a single `/StructParent` key instead. These reverse links let
   a viewer go from rendered content back to its place in the logical tree.

pikepdf's high-level attachment methods maintain the third for you: attaching
content to an element updates the parent tree, assigns the relevant page or
stream a `/StructParents` key (or an object a `/StructParent` key), and advances
`/ParentTreeNextKey`.

## Tagging a page

Marking content and building the tree are separate steps, joined by the MCID.
{class}`pikepdf.ContentMarker` handles the content stream: you choose which
ranges of instructions become marked-content sequences, and it allocates
identifiers that do not collide with any identifiers the page already uses.

Starting from a one-line untagged page:

```{eval-rst}
.. doctest::

    >>> from pikepdf import ContentMarker, Dictionary, Name, Pdf

    >>> pdf = Pdf.new()

    >>> page = pdf.add_blank_page()

    >>> page.obj.Resources = Dictionary(Font=Dictionary(F1=pdf.make_indirect(
    ...     Dictionary(Type=Name.Font, Subtype=Name.Type1, BaseFont=Name.Helvetica))))

    >>> page.contents_add(b"BT /F1 12 Tf 72 720 Td (Hello) Tj ET\n")

    >>> page.contents_coalesce()
```

Build the tree first, then mark the content that belongs to it:

```{eval-rst}
.. doctest::

    >>> tree = pdf.open_structure_tree()

    >>> document = tree.add(Name.Document, lang='en-US')

    >>> paragraph = document.add_child(Name.P, page=page)

    >>> marker = ContentMarker(page)

    >>> [str(instruction.operator) for instruction in marker.instructions]
    ['BT', 'Tf', 'Td', 'Tj', 'ET']

    >>> _ = marker.mark(Name.P, 0, 5, element=paragraph)

    >>> _ = marker.apply()

    >>> tree.validate()
    []
```

Ranges are half-open index pairs into
{attr}`pikepdf.ContentMarker.instructions`. Ranges bound to structure elements
may not nest inside one another. Unbound marked content and artifacts may nest
with tagged ranges in either direction; conformance profiles may impose
additional policy. Ranges may not partially overlap, cross an existing
`BMC`/`BDC`...`EMC`, `q`/`Q`, `BT`/`ET`, or compatibility-section `BX`/`EX`
boundary, or split a path object. `ContentMarker` raises
{exc}`pikepdf.StructureTreeError` rather than emit an invalid sequence.
Calls to `mark()` only queue work. `apply()` preflights every queued range and
structure attachment before writing, and restores the page, elements and parent
tree if a later write fails.

A nonempty page or Form MCID space starts at 0. Identifiers may have gaps, and
an MCID does not need to be claimed by a structure element in core PDF, but it
must not be reused in the same identifier space. `ContentMarker` enforces these
rules when it allocates identifiers.

Passing `element=` is what ties the two halves together: on
{meth}`pikepdf.ContentMarker.apply`, the sequence is appended to that element's
`/K` and registered in the parent tree. Without it you get an intentionally
unbound marked-content sequence, which core PDF permits and which can be wired
to the structure tree later.

For normal writes, prefer {meth}`~pikepdf.StructElem.add_content`,
{meth}`~pikepdf.StructElem.add_object`, or
{meth}`~pikepdf.ContentMarker.mark` with `element=`.
{class}`pikepdf.ParentTree` is also exposed for inspection and repair, but its
mapping-style `__setitem__` is deliberately low level and does not create the
matching `/K` claim. `register_content()` and `register_object()` repair reverse
maps only when matching reachable claims already exist.

## Reading a tree

{meth}`pikepdf.StructTree.walk` iterates depth first up to the configured
`max_depth`; {attr}`pikepdf.StructElem.children` gives one level. The limit is
only a reading convenience. Validation and cleanup always traverse the complete
tree so a shallow public walk cannot hide or leave behind deeper references.

Readers are lenient by default, as {meth}`pikepdf.Pdf.open_outline` is: a
structure element damaged beyond what the accessor can express -- a `/P` that
names nothing, an unusable `/Pg` -- reads as `None` rather than raising, so a
malformed document can still be inspected and repaired. Open the tree with
`strict=True` to have those defects raise {exc}`pikepdf.StructureTreeError`
instead. Either way {meth}`pikepdf.StructTree.validate` reports them, and
either way *writes* validate what they touch: leniency is a concession to
reading damaged files, not a licence to write into them.

```{eval-rst}
.. doctest::

    >>> tree.marked
    True

    >>> [str(elem.tag) for elem in tree.walk()]
    ['/Document', '/P']

    >>> next(tree.elements_with_tag(Name.P)).content
    [<pikepdf.MarkedContentRef: mcid=0>]

    >>> page.obj.StructParents
    0
```

{attr}`pikepdf.StructElem.kids` reports every child in order, as a mixture of
`StructElem`, {class}`pikepdf.MarkedContentRef` and {class}`pikepdf.ObjectRef`.
Use {attr}`~pikepdf.StructElem.children` and
{attr}`~pikepdf.StructElem.content` when you want only one kind.

Elements may also have a document-wide {attr}`~pikepdf.StructElem.element_id`.
Assigning a `str` or `bytes` value creates and maintains `/IDTree`, and
{meth}`pikepdf.StructTree.find_by_id` performs an exact lookup. Most identifiers
are exposed as text. If decoding and re-encoding a PDF string would change its
original bytes, `element_id` returns those bytes instead so a read/write
round-trip remains lossless.

## Detaching and re-attaching

{meth}`pikepdf.StructElem.remove` detaches an element and its descendants and
clears the parent tree entries they owned. A removed element keeps no `/P`, so
it is *detached* rather than corrupt: it can still be edited, and
{meth}`pikepdf.StructElem.attach_child` (or {meth}`pikepdf.StructTree.attach`
for the top level) splices it back in, restoring the parent tree entries for
everything in the subtree. The same pair lets a subtree be built off to one
side and inserted once it is complete.

Editing a detached element is allowed because it changes only that element.
Operations that write into the parent tree -- {meth}`~pikepdf.StructElem.add_content`,
{meth}`~pikepdf.StructElem.add_object` -- require an attached element, since the
parent tree indexes the document as a whole and an entry pointing at an
unreachable element is corruption.

```{eval-rst}
.. doctest::

    >>> section = document.add_child(Name.Sect, page=page)

    >>> section.remove()

    >>> section.alt = 'edited while detached'

    >>> _ = document.attach_child(section)

    >>> [str(elem.tag) for elem in tree.walk()]
    ['/Document', '/P', '/Sect']

    >>> tree.validate()
    []
```

## Artifacts

For accessible output, content that carries no meaning -- running heads, page
numbers, rules, background art -- is normally marked as an *artifact* rather
than tagged. PDF/UA requires every content item to be tagged or artifacted,
although core PDF permits content that is neither and viewers will still
display it.

```{eval-rst}
.. doctest::

    >>> page.contents_add(b"q 0 0 m 10 0 l S Q\n")

    >>> page.contents_coalesce()

    >>> marker = ContentMarker(page)

    >>> marker.mark_artifact(7, 12, properties={Name.Type: Name.Pagination})

    >>> _ = marker.apply()

    >>> tree.validate()
    []
```

## Deciding what to tag

pikepdf will not guess which structure type a block of text deserves; that is a
decision about the document, not about the PDF format. What it offers is the
evidence and the mechanism.

{func}`pikepdf.find_font_usage` reports every valid `Tf` font selection in a
page's own content stream, in order:

```{eval-rst}
.. doctest::

    >>> from pikepdf import find_font_usage

    >>> sorted(
    ...     (str(u.font), u.size, str(u.base_font)) for u in find_font_usage(page)
    ... )
    [('/F1', Decimal('12'), '/Helvetica')]
```

Once you have decided which font means which tag,
{func}`pikepdf.mark_text_runs` applies that decision to the page's own content
stream. It tracks effective `Tf` selections across text objects and `q`/`Q`
save/restore pairs and honors font changes within a text object. It creates a
range only for a segment that actually shows text; that range also includes the
surrounding text-state and positioning instructions needed to preserve valid
PDF syntax. An extended graphics state that selects a font is left untagged
until a later `Tf`. Adjacent compatible text objects are merged, while mapped
`None` values and graphics outside text objects are left alone. Form XObjects
are not scanned by this convenience function.

```{eval-rst}
.. doctest::

    >>> from decimal import Decimal

    >>> from pikepdf import mark_text_runs

    >>> report = Pdf.new()

    >>> heading_and_body = report.add_blank_page()

    >>> heading_and_body.obj.Resources = Dictionary(Font=Dictionary(
    ...     F1=report.make_indirect(Dictionary(
    ...         Type=Name.Font, Subtype=Name.Type1, BaseFont=Name.Helvetica)),
    ...     F2=report.make_indirect(Dictionary(
    ...         Type=Name.Font, Subtype=Name.Type1,
    ...         BaseFont=Name('/Helvetica-Bold')))))

    >>> heading_and_body.contents_add(
    ...     b"BT /F2 24 Tf 72 720 Td (Title) Tj ET\n"
    ...     b"BT /F1 12 Tf 72 690 Td (Body.) Tj ET\n")

    >>> heading_and_body.contents_coalesce()

    >>> report_tree = report.open_structure_tree()

    >>> report_document = report_tree.add(Name.Document, lang='en-US')

    >>> marked = mark_text_runs(
    ...     heading_and_body,
    ...     {
    ...         (Name.F2, Decimal(24)): Name.H1,
    ...         (Name.F1, Decimal(12)): Name.P,
    ...     },
    ...     parent=report_document,
    ... )

    >>> [(str(mc.tag), mc.mcid) for mc in marked]
    [('/H1', 0), ('/P', 1)]

    >>> [str(elem.tag) for elem in report_tree.walk()]
    ['/Document', '/H1', '/P']
```

A callable may be passed instead of a mapping, for policies that depend on more
than the exact font and size:

```python
>>> mark_text_runs(page, lambda usage: Name.H1 if usage.size > 20 else Name.P)
```

For anything finer-grained, drive {class}`pikepdf.ContentMarker` yourself.

## Annotations and other objects

An annotation is a structural content item in its own right rather than a
marked-content sequence. {meth}`pikepdf.StructElem.add_object` writes the
`/OBJR` entry, sets the annotation's `/StructParent`, and registers it:

```{eval-rst}
.. doctest::

    >>> from pikepdf import Array

    >>> page.obj.Annots = Array([pdf.make_indirect(Dictionary(
    ...     Type=Name.Annot, Subtype=Name.Link,
    ...     Rect=Array([72, 680, 300, 700])))])

    >>> link = document.add_child(Name.Link, page=page)

    >>> reference = link.add_object(page.obj.Annots[0], page)

    >>> page.obj.Annots[0].StructParent
    1

    >>> tree.validate()
    []
```

An annotation dictionary may occur in the `/Annots` array of exactly one page,
and an `/OBJR` for it must name that page. pikepdf enforces this in both the
writer and validator.

Content drawn from a form XObject lives in a different stream, with its own MCID
space. `ContentMarker` rewrites page content only; it does not insert marks into
a Form. After the Form's stream already contains the marked-content sequence,
call
{meth}`~pikepdf.StructElem.add_content` as
`element.add_content(page, mcid, stream=form)`. pikepdf then records the parent
tree entry against the XObject's `/StructParents` rather than the page's.
This internal-MCID form is valid only when the Form is rendered once. If the
same Form is painted repeatedly, associate each `Do` invocation with its own
distinct claimed marked-content sequence in the invoking page or Form stream.
An entire Form may also be associated as an {class}`pikepdf.ObjectRef`; one
reference covers repeated renditions on the same page, while each page needs
its own reference.

When the stream is owned by another indirect object, such as an annotation
appearance, also pass `stream_owner=annotation` to write the MCR dictionary's
`/StmOwn` entry. An annotation must reference the stream through its `/AP`
appearance dictionary; direct and indirect appearance/state dictionaries are
supported. Other owner types must reference the stream through their direct
dictionary or array graph.

## Custom structure types

Any name may be used as a structure type. If it is not one of the standard
types, map it to one so that consumers that do not know your vocabulary can
still make sense of the document:

```{eval-rst}
.. doctest::

    >>> tree.add_role(Name.Recipe, Name.Sect)

    >>> tree.role_map[Name.Recipe]
    pikepdf.Name("/Sect")
```

## Checking the result

{meth}`pikepdf.StructTree.validate` cross-checks the tree, the parent tree,
structural-parent keys, Form and object references, every page's marked content,
and marked content in Forms named by structure claims. It returns a list of
problem descriptions, empty when everything it checks agrees. Passing
`check_content=False` skips content-stream parsing, which is the expensive part.

Problems that differ only in their marked-content identifier are reported once
per container, with the remaining identifiers named after the message. One
systemic defect -- a file whose artifact stubs are all unreachable, say -- reads
as one line per page rather than dozens, so it cannot bury the rest of the
report. Treat each entry as one defect rather than assuming one entry per
identifier.

Validation follows page `Do` execution paths that are visible in the document,
so it can reject positively observed structural nesting and repeated execution
of a Form that uses internal MCIDs. It does not assume that a stream is unused
merely because no page `Do` reaches it: appearance streams, patterns, soft
masks, Type 3 fonts and other PDF mechanisms can render streams indirectly.
Likewise, an unclaimed MCID is allowed by core PDF and is not itself an error.
This is a structural consistency check, not a complete PDF/UA conformance test;
use a dedicated validator such as veraPDF when PDF/UA conformance is required.

## Limitations

- Page operations do not maintain the structure tree. Copying a page with
  {attr}`pikepdf.Pdf.pages` or deleting one leaves orphaned elements and stale
  parent tree entries behind; run {meth}`pikepdf.StructTree.validate`
  afterwards.
- {meth}`pikepdf.StructElem.remove` detaches a subtree and clears the parent-tree
  mappings it owned. Object references whose scalar mapping is removed also
  lose `/StructParent`; a page or Form may retain its reusable `/StructParents`
  key and now-empty array slots. The method does not remove the corresponding
  marked content from page or Form streams, so those sequences become unbound.
  {meth}`pikepdf.StructTree.remove` removes the complete logical tree and clears
  `/StructParent` and `/StructParents` keys throughout the document, but
  likewise does not rewrite content streams.
- Direct terminal structure elements can be read, walked and validated, but
  they must have no `/K`, cannot be mutated, and prevent their containing
  subtree from being removed individually. PDF object wrappers cannot identify
  one direct dictionary unambiguously after it has been retrieved from an
  array; writers created by pikepdf use indirect elements. Removing the whole
  structure tree remains supported.
- {class}`pikepdf.ContentMarker` re-serializes the page's content stream rather
  than patching it in place. Its recursive Form analysis protects the page
  rewrite; it does not insert marked content into Forms.
- {func}`pikepdf.find_marked_content`, {func}`pikepdf.next_mcid`,
  {func}`pikepdf.find_font_usage`, and {func}`pikepdf.mark_text_runs` read a
  page's own contents only. They do not recurse into Form XObjects, whose
  streams have their own identifier spaces.
- {attr}`pikepdf.StructElem.namespace` registers and validates PDF 2.0
  namespace dictionaries in `/StructTreeRoot /Namespaces`, but pikepdf does
  not interpret namespace-specific `/RoleMapNS` mappings.
