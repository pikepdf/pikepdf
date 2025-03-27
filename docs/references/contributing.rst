=======================
Contributing guidelines
=======================

Contributions are welcome!

Big changes
===========

Please open a new issue to discuss or propose a major change. Not only is it fun
to discuss big ideas, but we might save each other's time too. Perhaps some of the
work you're contemplating is already half-done in a development branch.

Code style: Python
==================

We use PEP8, ``black`` for code formatting and ``isort`` for import sorting. The
settings for these programs are in :file:`pyproject.toml` and :file:`setup.cfg`. Pull
requests should follow the style guide. One difference we use from "black" style
is that strings shown to the user are always in double quotes (``"``) and strings
for internal uses are in single quotes (``'``).

Code style: C++
===============

The file :file:`.clang-format` contains our C++ format
based on Clang's formatter, imperfect as it is. We eagerly await a dangling parenthesis
(https://reviews.llvm.org/D33029).

In general we prefer to make our C++ look similar to Python PEP8, within reason,
because our code is primarily a Python binding. That is, variable and method names
are snake_case, class names are CamelCase. Our coding conventions are closer to
pybind11's than qpdf's. When a C++ object wraps is a Python object, it should follow
the Python naming conventions for that type of object, e.g.
``auto Decimal = py::module_::import("decimal").attr("Decimal")``
for a reference to the Python ``Decimal`` class even though it is a C++ object.

We don't like the traditional C++ .cpp/.h separation that results in a lot of
repetition. Headers that are included by only one .cpp can contain a complete class,
and get the ``-inl.h`` suffix, unless multiple inclusion is required.

Use RAII. Avoid naked pointers. Use the STL, use ``std::string`` instead of ``char *``.
Use ``#pragma once`` as a header guard rather than silly ``#ifdef``; they have
been around for 25 years.

Tests
=====

New features should come with tests that confirm their correctness.

New dependencies
================

If you are proposing a change that will require a new dependency, we
prefer dependencies that are already packaged by Debian or Red Hat. This makes
life much easier for our downstream package maintainers.

Dependencies must also be compatible with the source code license.

English style guide
===================

pikepdf is always spelled "pikepdf", and never capitalized even at the beginning
of a sentence.

Periodic allusions to fish are required, and the writer shall be energetic and
mildly amusing.

Known ports/packagers
=====================

pikepdf has been ported to many platforms already. If you are interesting in
porting to a new platform, check with
`Repology <https://repology.org/projects/?search=pikepdf>`__ to see the status
of that platform.
