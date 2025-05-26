(pagelayout)=

# Default appearance in PDF viewers

Using pikepdf you can control the initial page layout and page mode, that is,
how a PDF will appear by default when loaded in a PDF viewer.

These settings are changed written to the PDF's Root object. Note that the PDF
viewer may ignore them and user preferences may override, etc.

```python
from pikepdf import Pdf, Dictionary, Name
with Pdf.open('input.pdf') as pdf:
    pdf.Root.PageLayout = Name.SinglePage
    pdf.Root.PageMode = Name.FullScreen
    pdf.save('output.pdf')
```

For reference, the tables below provide summarize the available options.

```{eval-rst}
.. list-table:: PageLayout definitions
    :widths: 20 80
    :header-rows: 1

    * - Value
      - Meaning
    * - Name.SinglePage
      - Display one page at a time (default)
    * - Name.OneColumn
      - Display the pages in one column
    * - Name.TwoColumnLeft
      - Display the pages in two columns, with odd-numbered pages on the left
    * - Name.TwoColumnRight
      - Display the pages in two columns, with odd-numbered pages on the right
    * - Name.TwoPageLeft
      - Display the pages two at a time, with odd-numbered pages on the left
    * - Name.TwoPageRight
      - Display the pages two at a time, with odd-numbered pages on the right
```

```{eval-rst}
.. list-table:: PageMode definitions
    :widths: 20 80
    :header-rows: 1

    * - Value
      - Meaning
    * - Name.UseNone
      - Neither document outline nor thumbnail images visible (default)
    * - Name.UseOutlines
      - Document outline visible
    * - Name.UseThumbs
      - Thumbnail images visible
    * - Name.FullScreen
      - Full-screen mode, with no menu bar, window controls, or any other window visible
    * - Name.UseOC
      - Optional content group panel visible
    * - Name.UseAttachments
      - Attachments panel visible
```
