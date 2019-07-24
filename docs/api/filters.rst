Content streams
***************

In PDF, drawing operations are all performed in content streams that describe
the positioning and drawing order of all graphics (including text, images and
vector drawing).

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

.. autofunction:: pikepdf.parse_content_stream

.. autoclass:: pikepdf.Token
    :members:

.. class:: pikepdf.TokenType

    When filtering content streams, each token is labeled according to the role
    in plays.

    **Standard tokens**

    .. attribute:: array_open

    .. attribute:: array_close

    .. attribute:: brace_open

    .. attribute:: brace_close

    .. attribute:: dict_open

    .. attribute:: dict_close

        These tokens mark the start and end of an array, text string, and
        dictionary, respectively.

    .. attribute:: integer

    .. attribute:: real

    .. attribute:: null

    .. attribute:: bool

        The token data represents an integer, real number, null or boolean,
        respectively.

    .. attribute:: Name

        The token is the name of an object. In practice, these are among the
        most interesting tokens.

    .. attribute:: inline_image

        An inline image in the content stream. The whole inline image is
        represented by the single token.

    **Lexical tokens**

    .. attribute:: comment

        Signifies a comment that appears in the content stream.

    .. attribute:: word

        Otherwise uncategorized bytes are returned as ``word`` tokens. PDF
        operators are words.

    .. attribute:: bad

        An invalid token.

    .. attribute:: space

        Whitespace within the content stream.

    .. attribute:: eof

        Denotes the end of the tokens in this content stream.

.. autoclass:: pikepdf.TokenFilter
    :members:
