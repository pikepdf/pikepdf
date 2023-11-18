Content streams
***************

In PDF, drawing operations are all performed in content streams that describe
the positioning and drawing order of all graphics (including text, images and
vector drawing).

.. seealso::
    :ref:`working_with_content_streams`

pikepdf (and libqpdf) provide two tools for interpreting content streams:
a parser and filter. The parser returns higher level information, conveniently
grouping all commands with their operands. The parser is useful when one wants
to retrieve information from a content stream, such as determine the position
of an element. The parser should not be used to edit or reconstruct the content
stream because some subtleties are lost in parsing.

The token filter works at a lower level, considering each token including
comments, and distinguishing different types of spaces. This allows modifying
content streams. A TokenFilter must be subclassed; the specialized version
describes how it should transform the stream of tokens.

Content stream parsers
----------------------

.. autoapifunction:: pikepdf.parse_content_stream

.. autoapifunction:: pikepdf.unparse_content_stream


Content stream token filters
----------------------------

.. autoapiclass:: pikepdf.Token
    :members:

.. autoapiclass:: pikepdf.TokenType
    :members:

.. autoapiclass:: pikepdf.TokenFilter
    :members:
