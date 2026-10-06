# Content streams

In PDF, drawing operations are all performed in content streams that describe
the positioning and drawing order of all graphics (including text, images and
vector drawing).

:::{seealso}
[Working with content streams](#working-with-content-streams)
:::

pikepdf (and libqpdf) provide two tools for interpreting content streams:
a parser and a token filter. The parser returns higher level information,
conveniently grouping each operator with its operands. Use it when you need to
know what an instruction means, whether to retrieve information, such as the
position of an element, or to remove, insert and change instructions. A content
stream that is parsed and then unparsed draws the same thing, but its
whitespace is normalized and its comments are lost.

The token filter works at a lower level, considering each token including
comments, and distinguishing different types of spaces. It passes through
everything it does not change exactly as written, so it suits changes to how a
content stream is spelled, such as rounding numbers. A TokenFilter must be
subclassed; the specialized version describes how it should transform the
stream of tokens.

:::{seealso}
[Choosing between the parser and a token filter](#parser-or-token-filter),
which is followed by worked examples of token filters.
:::

## Content stream parsers

```{eval-rst}
.. autoapifunction:: pikepdf.parse_content_stream
```

```{eval-rst}
.. autoapifunction:: pikepdf.unparse_content_stream
```

```{eval-rst}
.. autoapiclass:: pikepdf.StreamParser
    :members:
```

```{eval-rst}
.. autoapiclass:: pikepdf.models.ctm.MatrixStack
```

```{eval-rst}
.. autoapifunction:: pikepdf.models.ctm.get_objects_with_ctm
```

## Content stream token filters

```{eval-rst}
.. autoapiclass:: pikepdf.Token
    :members:
```

```{eval-rst}
.. autoapiclass:: pikepdf.TokenType
    :members:
```

```{eval-rst}
.. autoapiclass:: pikepdf.TokenFilter
    :members:
```
