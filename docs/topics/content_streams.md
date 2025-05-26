(working-with-content-streams)=

# Working with content streams

A content stream is a stream object associated with either a page or a Form
XObject that describes where and how to draw images, vectors, and text. (These
PDF streams have nothing to do with Python I/O streams.)

Content streams are binary data that can be thought of as a list of operators
and zero or more operands. Operands are given first, followed by the operator.
It is a stack-based language, loosely based on PostScript. (It's not actually
PostScript, but sometimes well-meaning people mistakenly say that it is!)
Like HTML, it has a precise grammar, and also like (pure) HTML, it has no loops,
conditionals or variables.

A typical example is as follows (with additional whitespace and PostScript-style
`%`-comments):

```
q                   % 1. Push graphics stack.
100 0 0 100 0 0 cm  % 2. The 6 numbers are the operands, followed by cm operator.
                    %    This configures the current transformation matrix.
/Image1 Do          % 3. Draw the object named /Image1 from the /Resources
                    %    dictionary.
Q                   % 4. Pop graphics stack.
```

The pattern `q, cm, <drawing commands>, Q` is extremely common. The drawing
commands may recurse with another `q, cm, ..., Q`.

pikepdf provides a C++ optimized content stream parser and a filter. The parser
is best used for reading and interpreting content streams; the filter is better
for low level editing.

## Pretty-printing content streams

To pretty-print a content stream, you can use parse and then unparse it. This
converts it from binary data form to pikepdf objects and back. In the process,
the content stream is cleaned up. Every instruction will be separated by a line
break.

```{eval-rst}
.. doctest::

  with pikepdf.open("../tests/resources/congress.pdf") as pdf:
      page = pdf.pages[0]
      instructions = pikepdf.parse_content_stream(page)
      data = pikepdf.unparse_content_stream(instructions)
      print(data.decode('ascii'))
```

:::{note}
Content streams are not always decodable to ASCII. This one just happens to be.
:::

## How content streams draw images

This example prints a typical content stream from a real file, which like the
contrived example above, displays an actual image.

```{eval-rst}
.. doctest::

  with pikepdf.open("../tests/resources/congress.pdf") as pdf:
      page = pdf.pages[0]
      commands = []
      for operands, operator in pikepdf.parse_content_stream(page):
          print(f"Operands {operands}, operator {operator}")
          if operator == pikepdf.Operator('cm'):
              matrix = pikepdf.Matrix(operands)
          commands.append([operands, operator])
```

PDF content streams are stateful. The commands `q`, `cm` and `Q`
manipulate the current transform matrix (CTM) which describes where we will draw
next. *In most cases* you have to track every manipulation of the CTM to figure
out what will happen, even to answer a question like, "where will this image
be drawn, and how big will it be?"

But *in this simple case*, we can read the matrix directly. The decimal numbers
200.0 and 304.0 establish the width and height at which the image should be drawn,
in PDF points (1/72" or about 0.35 mm). The pixel dimensions of the image have
no effect. If we substituted that image for another, the new image would be
drawn in the same location on the page, painted into the 200 × 304 rectangle
regardless of its pixel dimensions.

## Editing a content stream

Let's continue with the file above and center the image on the page, and reduce
its size by 50%. Because we can! For that, we need to rewrite the second command
in the content stream.

We take the original matrix (`matrix`) and then translated it to the center
of this page. We're currently in a coordinate system where (0, 0) is the bottom
left corner of the page, and (1, 1) is the top right corner. Without actually
having to track the image's position, we can translate it by 0.25 of its
dimensions (to create a border of 25% all around) and then scale it by 0.5.
(We could also scale by 50%, and then translate by 50%, which would be 25% in
the full image coordinate system.)

```{eval-rst}
.. doctest::

  new_matrix = matrix.translated(0.25, 0.25).scaled(0.5, 0.5)
  new_matrix
```

On an important note, the PDF coordinate system is nailed to the **bottom left**
corner of the page, and on y-axis, **up is positive**. That is, the coordinate
system is more like the first quadrant of a Cartesian graph than the
**down is positive** convention normally used in pixel graphics:

:::{figure} /images/pdfcoords.svg
:align: center
:alt: PDF positive-up coordinate system
:figwidth: 50%
:::

(Some PDF programs insert a command to "flip" the coordinate system, by
translating to the top left corner and scaling by (1, -1).)

After calculating our new matrix, we need to insert it back into the parsed
content stream, "unparse" it to binary data, and replace the old content
stream.

```{eval-rst}
.. doctest::

  commands[1][0] = pikepdf.Array(new_matrix)
  new_content_stream = pikepdf.unparse_content_stream(commands)
  new_content_stream
  page.Contents = pdf.make_stream(new_content_stream)

  # You could save the file here to see it
  # pdf.save(...)
```

:::{note}
To rotate an image, first translate it so that the image is centered at (0, 0),
rotate then apply the rotate, then translate it to its new center position.
This is because rotations occur around (0, 0).
:::

:::{note}
In this illustration, the page's MediaBox is located at (0, 0) for simplicity.
The MediaBox can be offset from the origin, and code that edits content streams
may need to account for this relatively condition.
:::

## Editing content streams robustly

The stateful nature of PDF content streams makes editing them complicated. Edits
like the example above will work when the input file is known to have a fixed
structure (that is, the state at the time of editing is known). You can always
prepend content to the top of the content stream, since the initial state is
known. And you can often append content to the end the stream, since the final
state is predictable if every `q` (push state) has a matching `Q` (pop
state).

Otherwise, you must track the graphics state and maintain a stack of states.

Most applications will end up parsing the content stream into a higher level
representation that is easier edit and then serializing it back, totally
rewriting the content stream. Content streams should be thought of as an
output format.

## Extracting text from PDFs

If you guessed that the content streams were the place to look for text inside a
PDF – you'd be correct. Unfortunately, extracting the text is fairly difficult
because content stream actually specifies as a font and glyph numbers to use.
Sometimes, there is a 1:1 transparent mapping between Unicode numbers and glyph
numbers, and dump of the content stream will show the text. In general, you
cannot rely on there being a transparent mapping; in fact, it is perfectly legal
for a font to specify no Unicode mapping at all, or to use an unconventional
mapping (when a PDF contains a subsetted font for example).

**We strongly recommend against trying to scrape text from the content stream.**

pikepdf does not currently implement text extraction. We recommend [pdfminer.six](https://github.com/pdfminer/pdfminer.six), a
read-only text extraction tool. If you wish to write PDFs containing text, consider
[reportlab](https://www.reportlab.com/opensource/).

## Interpreting and generating content streams

{mod}`pikepdf.ctm` has functions to interpret content streams, specifically
to determine the state of the current transformation matrix at certain rendering
events.

{mod}`pikepdf.canvas` has functions to generate simple content streams.
