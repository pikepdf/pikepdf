---
myst:
  substitutions:
    alpine: |-
      ```{image} https://repology.org/badge/version-for-repo/alpine_edge/python:pikepdf.svg
      :alt: Alpine Linux Edge
      ```
    fedora: |-
      ```{image} https://repology.org/badge/version-for-repo/fedora_rawhide/python:pikepdf.svg
      :alt: Fedora Rawhide
      ```
    freebsd: |-
      ```{image} https://repology.org/badge/version-for-repo/freebsd/python:pikepdf.svg
      :alt: FreeBSD
      :target: https://repology.org/project/python:pikepdf/versions
      ```
    latest: |-
      ```{image} https://img.shields.io/pypi/v/pikepdf.svg
      :alt: pikepdf latest released version on PyPI
      ```
    python_pikepdf: |-
      ```{image} https://repology.org/badge/vertical-allrepos/python:pikepdf.svg
      :alt: Package status for python:pikepdf
      ```
---

# Installation

## Basic installation

{{ latest }}

Most users on Linux, macOS or Windows with x64 systems should use `pip` to
install pikepdf in their current Python environment (such as your project's
virtual environment).

```bash
pip install pikepdf
```

Use `pip install --user pikepdf` to install the package for the current user
only. Use `pip install pikepdf` to install to a virtual environment.

## Binary wheel availability

```{eval-rst}
.. csv-table:: Python binary wheel availability
    :file: binary-wheels.csv
    :header-rows: 1
```

- ✅ wheels are available
- ❌ wheels are not likely to be produced for this platform and Python version
- ⏳ we are waiting on a third party to implement better support for this configuration
- ⚠️ wheel is released but cannot be tested - use with caution

Binary wheels should work on most systems, **provided a recent version
of pip is used to install them**. Old versions of pip, especially before 20.0,
may fail to check appropriate versions.

macOS 14 or newer is typically required for binary wheels. Older versions may
work if compiled from source.

Windows 7 or newer is required. Windows wheels include a recent copy of libqpdf.

Most Linux distributions support manylinux2014, with the notable except of
[Alpine Linux], and older Linux distributions that do not have C++20-capable
compilers. The Linux wheels include recent copies of libqpdf, libjpeg, and zlib.

Source builds are usually possible where binary wheels are available.

## Platform support

Some platforms include versions of pikepdf that are distributed by the system
package manager (such as `apt`). These versions may lag behind the version
distributed with PyPI, but may be convenient for users that cannot use binary
wheels.

:::{figure} /images/sushi.jpg
:align: right
:alt: Bento box containing sushi
:figwidth: 40%

Packaged fish.
:::

{{ python_pikepdf }}

### Debian, Ubuntu and other APT-based distributions

```bash
apt install pikepdf
```

### Fedora

{{ fedora }}

```bash
dnf install python_pikepdf
```

### Alpine Linux

{{ alpine }}

```bash
apk add py3-pikepdf
```

## Installing on FreeBSD

```bash
pkg install py311-pikepdf
```

To attempt a manual install, try something like:

```bash
pkg install python3 py311-lxml py311-pip py311-pybind11 qpdf
pip install --user pikepdf
```

This procedure is known to work on FreeBSD 13.4 and 14.1.

## PyPy3 support

We stopped generating binary wheels for PyPy3 after pikepdf 9.8.1 since some dependencies are reducing support for PyPy. You can use earlier versions or compile binary wheels from source.
