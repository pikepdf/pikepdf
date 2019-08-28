Working with content streams
============================

A content stream is a stream object associated with either a page or a Form
XObject that describes where and how to draw images, vectors, and text.

Content streams are binary data that can be thought of as a list of operators
and zero or more operands. Operands are given first, followed by the operator.
It is a stack-based language based loosely on PostScript, but without any
programmable features. There are no variables, loops or conditionals.

A typical example is as follows (with additional
whitespace):

.. code-block::

  q                   # push graphics stack
  100 0 0 100 0 0 cm  # set current transformation matrix
  /Image1 Do          # draw the object named /Image1 from the /Resources dictionary
  Q                   # pop graphics stack

pikepdf provides a C++ optimized content stream parser and a filter. The parser
is best used for reading and interpreting content streams; the filter is best
used for rewriting them.

.. ipython:: python

  pdf = pikepdf.open("../tests/resources/congress.pdf")
  page = pdf.pages[0]
  for operands, operator in pikepdf.parse_content_stream(page):
      print("Operands {}, operator {}".format(operands, operator))

Extracting text from PDFs
-------------------------

If you guessed that the content streams were the place to look for text inside a PDF
– you'd be correct. Unfortunately, extracting the text is fairly difficult because
content stream actually specifies as a font and glyph numbers to use. Sometimes, there
is a 1:1 transparent mapping between Unicode numbers and glyph numbers, and dump of the
content stream will show the text. In general, you cannot rely on there being a
transparent mapping; in fact, it is perfectly legal for a font to specify no Unicode
mapping at all, or to use an unconventional mapping (when a PDF contains a subsetted
font for example).

**We strongly recommend against trying to scrape text from the content stream.**

pikepdf does not currently implement text extraction. We recommend `pdfminer.six <https://github.com/pdfminer/pdfminer.six>`_, a
read-only text extraction tool. If you wish to write PDFs containing text, consider
`reportlab <https://www.reportlab.com/opensource/>`_.
