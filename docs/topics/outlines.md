(outlines)=

# Outlines

Outlines (sometimes also called *bookmarks*) are shown in a the PDF viewer
aside of the page, allowing for navigation within the document.

## Creating outlines

Outlines can be created from scratch, e.g. when assembling a set of PDF files
into a single document.

The following example adds outline entries referring to the 1st, 3rd and 9th page
of an existing PDF.

```python
>>> from pikepdf import Pdf, OutlineItem

>>> pdf = Pdf.open('document.pdf')

>>> with pdf.open_outline() as outline:
...     outline.root.extend([
...         # Page counts are zero-based
...         OutlineItem('Section One', 0),
...         OutlineItem('Section Two', 2),
...         OutlineItem('Section Three', 8)
...     ])

>>> pdf.save('document_with_outline.pdf')
```

Another example, for automatically adding an entry for each file in a merged document:

```python
>>> from glob import glob

>>> pdf = Pdf.new()

>>> page_count = 0

>>> with pdf.open_outline() as outline:
...     for file in glob('*.pdf'):
...         src = Pdf.open(file)
...         oi = OutlineItem(file, page_count)
...         outline.root.append(oi)
...         page_count += len(src.pages)
...         pdf.pages.extend(src.pages)

>>> pdf.save('merged.pdf')
```

## Editing outlines

Existing outlines can be edited. Entries can be moved and renamed without affecting
the targets they refer to.

## Destinations

Destinations tell the PDF viewer where to go when navigating through outline items.
The simplest case is a reference to a page, together with the page location, e.g.
`Fit` (default). However, named destinations can also be assigned.

The PDF specification allows for either use of a destination (`Dest` attribute) or
an action (`A` attribute), but not both on the same element. `OutlineItem` elements
handle this as follows:

- When creating new outline entries passing in a page number or reference name,
  the `Dest` attribute is used.
- When editing an existing entry with an assigned action, it is left as-is, unless a
  `destination` is set. The latter is preferred if both are present.

Creating a more detailed destination with page location:

```python
>>> oi = OutlineItem('First', 0, 'FitB', top=1000)
```

The above will call `make_page_destination` when saving to a `Pdf` document,
roughly equivalent to the following:

```python
>>> oi.destination = make_page_destination(pdf, 0, 'FitB', top=1000)
```

An existing destination array (whatever form `.destination` takes -- an
explicit array, a page number, or a named destination) can be resolved to a
`Destination` with named accessors for its page, fit type, and viewport
parameters:

```python
>>> with pdf.open_outline() as outline:
...     dest = outline.root[0].resolved_destination(pdf)
...     dest.page, dest.fit_type, dest.left, dest.top
```

`resolved_destination` follows named destinations (a `String` via the
document's `Names.Dests` name tree, or a `Name` via the legacy `Dests`
dictionary) automatically, and returns `None` if there is no destination, or
a named destination cannot be resolved.

A `Destination` can also be built directly and passed as `destination=`:

```python
>>> from pikepdf import Destination, PageLocation

>>> oi = OutlineItem('First', Destination(pdf.pages[0].obj, PageLocation.FitB, top=1000))
```

## Actions

Instead of a destination, an outline item's `action` can be set to any PDF
action dictionary (`GoTo`, `URI`, `Launch`, etc. -- see PDF spec 12.6). The raw
action dictionary set on `.action` is always what gets written back to the
`Pdf`; `.parsed_action` gives a read-only, typed view of it:

```python
>>> from pikepdf import Dictionary, Name

>>> with pdf.open_outline() as outline:
...     item = outline.root[0]
...     item.action = Dictionary(S=Name.URI, URI='https://example.com')
...     item.parsed_action.uri
'https://example.com'
```

Typed action wrappers -- `GoToAction`, `GoToRAction`, `GoToEAction`,
`GoToDpAction`, `LaunchAction`, `URIAction`, `NamedAction`,
`SetOCGStateAction`, `JavaScriptAction` -- can also be constructed directly
and passed as `action=`; the `OutlineItem` unwraps it to the underlying
dictionary automatically. A `GoToAction`'s destination can be resolved the
same way as an `OutlineItem`'s:

```python
>>> from pikepdf import GoToAction

>>> action = GoToAction(Dictionary(S=Name.GoTo, D=[pdf.pages[0].obj, Name.Fit]))
>>> action.resolve_destination(pdf).page
```

Unrecognized action subtypes (e.g. `Rendition`, `Trans`) are returned as a
plain `Action`, whose `.subtype` and `.obj` give raw access.

## Color and style

An outline item's displayed text can be given a color and italic/bold
styling:

```python
>>> from pikepdf import OutlineItemFlag

>>> with pdf.open_outline() as outline:
...     item = outline.root[0]
...     item.color = (1.0, 0.0, 0.0)  # RGB, each component 0.0-1.0
...     item.bold = True
...     item.flags == OutlineItemFlag.Bold
True
```

`item.italic`/`item.bold` are convenience accessors backed by
`item.flags` (an `OutlineItemFlag`). Setting `item.color = None` (the
default) removes the `/C` entry so viewers fall back to black text.

## Structure element linkage

For tagged PDFs, an outline item can carry a `structure_element` reference
back to the structure element it corresponds to (PDF spec 12.3.3, `/SE`).
Per spec this is not intended for navigation -- use `destination`/`action`
with a structure destination for that -- it is purely a semantic backlink
for accessibility tooling:

```python
>>> with pdf.open_outline() as outline:
...     outline.root[0].structure_element = pdf.Root.StructTreeRoot.K[0]
```

## Outline structure

For nesting outlines, add items to the `children` list of another `OutlineItem`.

```python
>>> with pdf.open_outline() as outline:
...     main_item = OutlineItem('Main', 0)
...     outline.root.append(main_item)
...     main_item.children.append(OutlineItem('A', 1))
```
