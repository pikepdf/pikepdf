Installation
============

.. |latest| image:: https://img.shields.io/pypi/v/pikepdf.svg
    :alt: pikepdf latest released version on PyPI

|latest|

Most users on Linux, macOS or Windows with x64 systems should take advantage of
the binary wheels.

.. code-block:: bash

    pip install pikepdf

64-bit wheels are available for Windows, Linux and macOS.

32-bit wheels are available for Windows, for use with the 32-bit version of
Python (regardless of the bitness  of Windows). 32-bit wheels for Linux will be
added if anyone uses them.

Binary wheels should work on most systems work on Linux distributions 2007
and newer, macOS 10.11 and newer (for Homebrew), Windows 7 and newer.

Managed distributions
---------------------

pikepdf is not yet widely distributed, but a few Linux distributions do make it
available.

**Debian**

.. |deb-experimental| image:: https://repology.org/badge/version-for-repo/debian_experimental/pikepdf.svg
    :alt: Debian experimental

|deb-experimental|

.. code-block:: bash

    apt-get -t experimental install pikepdf

**Fedora 29**

.. |fedora| image:: https://repology.org/badge/version-only-for-repo/fedora_29/python:pikepdf.svg
    :alt: Fedora 29

|fedora|

.. code-block:: bash

    dnf install python-pikepdf

**ArchLinux**

Available in `ArchLinux User Repository <https://aur.archlinux.org/packages/python-pikepdf/>`_.

.. code-block:: bash

    pacman -S pikepdf

Building from source
--------------------

**Requirements**

.. |qpdf-version| replace:: 8.2.1

pikepdf requires:

-   a C++11 compliant compiler - GCC (4.8 and up) and clang (3.3 and up); C++14
    is recommended and will produced smaller binaries
-   `pybind11 <https://github.com/pybind/pybind11>`_
-   libqpdf |qpdf-version| or higher from the
    `QPDF <https://github.com/qpdf/qpdf>`_ project.
-   defusedxml - Python package

On Linux the library and headers for libqpdf must be installed because pikepdf
compiles code against it and links to it.

Check `Repology for QPDF <https://repology.org/metapackage/qpdf/badges>`_ to
see if a recent version of QPDF is available for your platform. Otherwise you
must
`build QPDF from source <https://github.com/qpdf/qpdf/blob/master/INSTALL>`_.
(Consider using the binary wheels, which bundle the required version of
libqpdf.)

**GCC and Clang**

-  clone this repository
-  install libjpeg, zlib and libqpdf on your platform, including headers
-  ``pip install .``

.. note::

    pikepdf should be built with the same compiler and linker as libqpdf; to be
    precise both **must** use the same C++ ABI. On some platforms, setup.py may
    not pick the correct compiler so one may need to set environment variables
    ``CC`` and ``CXX`` to redirect it. If the wrong compiler is selected,
    ``import pikepdf._qpdf`` will throw an ``ImportError`` about a missing
    symbol.

**On Windows (requires Visual Studio 2015)**

.. |msvc-zip| replace:: qpdf-|qpdf-version|-bin-msvc64.zip

pikepdf requires a C++11 compliant compiler (i.e. Visual Studio 2015 on
Windows). See our continuous integration build script in ``.appveyor.yml``
for detailed and current instructions. Or use the wheels which save this pain.

These instructions require the precompiled binary ``qpdf.dll``. See the QPDF
documentation if you also need to build this DLL from source. Both should be
built with the same compiler. You may not mix and match MinGW and Visual C++
for example.

Running a regular ``pip install`` command will detect the
version of the compiler used to build Python and attempt to build the
extension with it. We must force the use of Visual Studio 2015.

- clone this repository
- ``"%VS140COMNTOOLS%\..\..\VC\vcvarsall.bat" x64``
- ``set DISTUTILS_USE_SDK=1``
- ``set MSSdk=1``
- download |msvc-zip| from the `QPDF releases page <https://github.com/qpdf/qpdf/releases>`_
- extract ``bin\qpdfXX.dll`` from the zip file above, where XX is the version
  of the ABI, and copy it to the ``src/pikepdf`` folder in the repository
- run ``pip install .`` in the root directory of the repository

.. note::

    The user compiling ``pikepdf`` to must have registry editing rights on the
    machine to be able to run the ``vcvarsall.bat`` script.

.. note::

    If you are attempting to build pikepdf because you want to use OCRmyPDF,
    **OCRmyPDF is not supported on Windows** at this time.

Windows runtime requirements
----------------------------

On Windows, the Visual C++ 2015 redistributable packages are a runtime
requirement for this project. It can be found
`here <https://www.microsoft.com/en-us/download/details.aspx?id=48145>`__.

Building the documentation
--------------------------

Documentation is generated using Sphinx and you are currently reading it. To
regenerate it:

-  ``pip install -r requirements/docs.txt``
-  ``cd pikepdf/docs``
-  ``make html``
