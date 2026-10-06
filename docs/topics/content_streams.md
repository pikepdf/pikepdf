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

pikepdf provides a C++ optimized content stream parser and a token filter. The
parser groups each operator with its operands, so it is the tool to use when
you need to know what an instruction means, whether to read it or to edit it.
The token filter sees one token at a time and is suited to rewriting how a
content stream is spelled without interpreting it. See
[Choosing between the parser and a token filter](#parser-or-token-filter).

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

(editing-content-streams-robustly)=

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

## Removing instructions from a content stream

To delete something from a content stream, parse it, leave out the instructions
you do not want, and unparse the rest. This example removes every instruction
that draws the image `/Im0`, and leaves the rest of the page alone.

```{eval-rst}
.. testcode::

  from pikepdf import Name, Operator, Pdf

  pdf = Pdf.new()
  pdf.add_blank_page()
  page = pdf.pages[0]
  page.Contents = pdf.make_stream(
      b'q 100 0 0 100 0 0 cm /Im0 Do Q q 50 0 0 50 200 200 cm /Im1 Do Q'
  )

  kept = [
      (operands, operator)
      for operands, operator in pikepdf.parse_content_stream(page)
      if not (operator == Operator('Do') and operands[0] == Name.Im0)
  ]
  page.Contents = pdf.make_stream(pikepdf.unparse_content_stream(kept))
  print(page.Contents.read_bytes().decode('ascii'))

.. testoutput::

  q
  100 0 0 100 0 0 cm
  Q
  q
  50 0 0 50 200 200 cm
  /Im1 Do
  Q
```

An instruction that only draws, such as `Do`, can be dropped on its own. Most
other instructions cannot. Removing a curve means removing the whole path it
belongs to, from the `m` that starts it to the operator that paints it, and
if that path is used for clipping, everything drawn afterwards changes. The
advice in [Editing content streams robustly](#editing-content-streams-robustly)
applies.

(parser-or-token-filter)=

## Choosing between the parser and a token filter

Use {func}`pikepdf.parse_content_stream` when the change depends on what an
instruction means: which operator it is, what its operands are, or what the
graphics state is when it runs. Removing, reordering and inserting instructions
all belong here.

Use a {class}`pikepdf.TokenFilter` when the change is about how the content
stream is written and can be decided one token at a time. A token is a single
number, name, string, operator, comment or run of whitespace. A token filter:

- passes through every token it does not change exactly as it was written,
  including whitespace, comments and inline images;
- does not build a Python object for every operand, so it is cheap on large
  content streams;
- can be attached to a page with {meth}`pikepdf.Page.add_content_token_filter`,
  in which case it runs when the content stream is next read or the file is
  saved, and several filters can be attached to the same page.

A token filter does not know which tokens are the operands of which operator.
If it needs to know, it has to hold tokens back until the operator arrives, as
the second example below does. Once that bookkeeping grows past a few lines,
use the parser instead.

Both tools only see the page's own content stream. Neither descends into Form
XObjects that the page draws.

## Shortening numbers with a token filter

Many programs write numbers with more digits than they need, such as
`144.0000`. Rounding them makes content streams smaller. The decision depends
only on the token itself, so a token filter is a good fit.

A token filter is a subclass of {class}`pikepdf.TokenFilter` that implements
`handle_token`. It is called once for each token, and returns the token to
keep it, `None` to drop it, or a new token or list of tokens to write instead.

```{eval-rst}
.. testcode::

  from decimal import Decimal

  from pikepdf import Pdf, Token, TokenFilter, TokenType

  class ShortenNumbers(TokenFilter):
      def __init__(self, places=2):
          super().__init__()
          self.quantum = Decimal(1).scaleb(-places)

      def handle_token(self, token):
          if token.type_ == TokenType.comment:
              return None
          if token.type_ == TokenType.real:
              number = Decimal(token.raw_value.decode('ascii'))
              number = number.quantize(self.quantum).normalize()
              text = format(number, 'f') if number else '0'
              return Token(TokenType.real, text.encode('ascii'))
          return token

  with Pdf.open('../tests/resources/pal-1bit-rgb.pdf') as pdf:
      page = pdf.pages[0]
      print(page.Contents.read_bytes().decode('ascii'))
      print('--')
      print(page.get_filtered_contents(ShortenNumbers()).decode('ascii'))

.. testoutput::

  q
  144.0000 0 0 144.0000 0.0000 0.0000 cm
  /Im0 Do
  Q
  --
  q
  144 0 0 144 0 0 cm
  /Im0 Do
  Q
```

{meth}`pikepdf.Page.get_filtered_contents` returns the filtered data and does
not change the page. To change the file, attach the filter to each page and
save:

```python
with Pdf.open('input.pdf') as pdf:
    for page in pdf.pages:
        page.add_content_token_filter(ShortenNumbers())
    pdf.save('output.pdf')
```

:::{warning}
Rounding moves things. Two decimal places is 1/7200 of an inch for a
coordinate in PDF points, but a number that is later multiplied by a large
scale factor in a `cm` matrix is magnified by that factor, and so is its
rounding error. Check the output of files you care about.
:::

## Converting RGB colors to grayscale with a token filter

The operators `rg` and `RG` set the fill and stroke color from three numbers,
red, green and blue. The operators `g` and `G` do the same from a single gray
level. This filter replaces the first kind with the second.

It has to see the operator before it knows what to do with the numbers in front
of it. So it holds numbers and whitespace back, and when the next token of any
other kind arrives, either replaces the last three numbers or releases
everything unchanged.

```{eval-rst}
.. testcode::

  from pikepdf import Pdf, Token, TokenFilter, TokenType

  NUMBERS = (TokenType.integer, TokenType.real)
  GRAY_OPERATORS = {b'rg': b'g', b'RG': b'G'}

  class RgbToGray(TokenFilter):
      def __init__(self):
          super().__init__()
          self.held = []

      def handle_token(self, token):
          if token.type_ in NUMBERS or token.type_ == TokenType.space:
              self.held.append(token)
              return None

          held, self.held = self.held, []
          numbers = [t for t in held if t.type_ in NUMBERS]
          is_rgb = (
              token.type_ == TokenType.word
              and token.raw_value in GRAY_OPERATORS
              and len(numbers) >= 3
          )
          if not is_rgb:
              return held + [token]

          r, g, b = (float(t.raw_value) for t in numbers[-3:])
          gray = 0.299 * r + 0.587 * g + 0.114 * b
          before_operands = held[: held.index(numbers[-3])]
          return before_operands + [
              Token(TokenType.real, f'{gray:.3f}'.encode('ascii')),
              Token(TokenType.space, b' '),
              Token(TokenType.word, GRAY_OPERATORS[token.raw_value]),
          ]

  pdf = Pdf.new()
  pdf.add_blank_page()
  page = pdf.pages[0]
  page.Contents = pdf.make_stream(
      b'q 1 0 0 rg 0.2 0.4 0.6 RG\n'
      b'10 10 100 50 re B\n'
      b'0.5 g 20 20 30 30 re f Q'
  )
  print(page.get_filtered_contents(RgbToGray()).decode('ascii'))

.. testoutput::

  q 0.299 g 0.363 G
  10 10 100 50 re B
  0.5 g 20 20 30 30 re f Q
```

The last token of every content stream has the type `TokenType.eof`. It is
neither a number nor whitespace, so anything still held back is released when
it arrives. A filter that holds tokens back must always release them by then.

This filter only changes colors set with `rg` and `RG` in the page's own
content stream. Images keep their colors, and so does anything colored through
the `sc`, `scn`, `k` or `cs` operators, a shading, or a Form XObject. Converting
a whole document to grayscale reliably is a job for a PDF renderer such as
Ghostscript.

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
