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

## Outline structure

For nesting outlines, add items to the `children` list of another `OutlineItem`.

```python
>>> with pdf.open_outline() as outline:
...     main_item = OutlineItem('Main', 0)
...     outline.root.append(main_item)
...     main_item.children.append(OutlineItem('A', 1))
```
