<!-- SPDX-FileCopyrightText: 2023 James R. Barlow -->
<!-- SPDX-License-Identifier: CC-BY-SA-4.0 -->

# Contributing to pikepdf

Thanks for your interest in improving pikepdf! This guide covers setting up a
development environment, building, testing, and the conventions we follow. For
end-user "build from source" instructions (including linking against a specific
qpdf), see [docs/source_build.md](docs/source_build.md).

## Development setup

pikepdf uses [uv](https://docs.astral.sh/uv/) as its package manager and
scikit-build-core (CMake + nanobind) to build the C++ extension. You need:

- a C++20-compliant compiler
- CMake >= 3.15
- libqpdf (see `QPDF_MIN_VERSION` in `pyproject.toml`) and its headers
- [uv](https://docs.astral.sh/uv/)

A qpdf checkout placed parallel to pikepdf (for example `../qpdf`) is detected
automatically by the build; see [docs/source_build.md](docs/source_build.md) to
link against a particular qpdf version.

Create the virtual environment and install pikepdf in editable mode with all
development dependencies:

```bash
uv venv
uv pip install -e . --group dev --group docs
```

Always drive the project through `uv` — `uv run python`, `uv pip`,
`uv run pytest` — rather than a bare `python`/`pip`, so commands target the
project virtual environment.

## Building the C++ extension

When you change C++ code under `src/core/`, recompile:

```bash
uv run make build
```

> **Important:** build with `uv pip` (which `make build` calls), not a bare
> `pip install -e .`. An older pip (< 22.1) does not reliably recompile the
> scikit-build-core editable extension — it can reuse a stale build and silently
> keep the previous binary, so your changes don't take effect and tests run
> against the old code. After rebuilding, confirm the new build is actually
> loaded (for example, check that a newly added method is present on the compiled
> class) before trusting test results.

## Testing

Tests run in parallel by default via pytest-xdist:

```bash
uv run pytest                                     # full suite
uv run pytest tests/test_pdf.py                   # one file
uv run pytest tests/test_pdf.py::test_function    # one test
uv run pytest --cov=src --cov-report=html -n auto # with coverage
```

## Linting, formatting, and type checking

```bash
# Python: format and lint
uv run ruff format src tests
uv run ruff check --fix src tests

# Python: type check
uv run python -m mypy src

# C++: format (uses .clang-format)
clang-format -i src/core/*.cpp src/core/*.h
```

A pre-commit configuration is included. Install the hooks so these checks run
automatically on each commit:

```bash
uv run pre-commit install
```

## Architecture notes

pikepdf has two layers:

- **C++** (`src/core/*.cpp`): nanobind bindings to libqpdf, compiled to the
  `pikepdf._core` extension module.
- **Python** (`src/pikepdf/`): the high-level, Pythonic API that wraps and
  extends `_core`.

Python methods are attached to the C++ binding classes via the `@augments`
decorator in `src/pikepdf/_methods.py`. This lets a feature move between Python
and C++ without changing the public API. Type stubs and docstrings for the
C++ API live in `src/pikepdf/_core.pyi`; keep them in sync when you change the
bindings. Prefer implementing features in Python unless qpdf provides them
directly or performance requires C++.

## Documentation

Documentation is built with Sphinx:

```bash
uv pip install -e . --group docs
cd docs && make html
```

## Release notes

Update `docs/releasenotes/versionXX.md` (where `XX` is the current major
version) when you complete a feature or fix, following the existing structure.

## Submitting changes

- Branch off `main` and open a pull request against `main`.
- Keep commits focused, and write clear messages in the imperative mood. We use
  conventional-commit prefixes such as `fix:`, `feat:`, `perf:`, `build:`,
  `ci:`, and `docs:`.
- Before requesting review, make sure `uv run pytest`,
  `uv run python -m mypy src`, and the ruff and clang-format checks all pass.

By contributing you agree that your contributions are licensed under the
project's MPL-2.0 license.
