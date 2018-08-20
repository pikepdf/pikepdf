Installation
============

Most users on Linux, macOS or Windows with x64 systems should take advantage of
the binary wheels.

.. code-block:: bash

    pip install pikepdf

64-bit wheels are always. 32-bit wheels will be added if there is any sign of
demand for them.

The binary wheels should work on most systems work on Linux distributions 2012
and newer, macOS 10.11 and newer (for Homebrew), Windows 7 and newer.

Managed distributions
---------------------

pikepdf is currently packaged for
`ArchLinux <https://aur.archlinux.org/packages/python-pikepdf/>`_.

Building from source
--------------------

**Requirements**

.. |qpdf-version| replace:: 8.1.0

pikepdf requires:

-   a C++11 compliant compiler - GCC (4.8 and up) and clang (3.3 and up); C++14
    is recommended and will produced smaller binaries
-   `pybind11 <https://github.com/pybind/pybind11>`_ (currently a vendored
    version is included in the pikepdf source, but this may change)
-   libqpdf |qpdf-version| or higher from the
    `QPDF <https://github.com/qpdf/qpdf>`_ project.

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

    pikepdf should be built with the same compiler and linker as pikepdf; to be
    precise both must use the same C++ ABI. On some platforms, setup.py may not
    pick the correct compiler so one may need to set environment variables
    ``CC`` and ``CXX`` to redirect it. If the wrong compiler is selected,
    ``import pikepdf._qpdf`` will throw an ``ImportError`` about a missing
    symbol.

**On Windows (requires Visual Studio 2015)**

pikepdf requires a C++11 compliant compiler (i.e. Visual Studio 2015 on
Windows). See our continuous integration build script in ``.appveyor.yml``
for detailed instructions. Or use the wheels which save this pain.

Running a regular ``pip install`` command will detect the
version of the compiler used to build Python and attempt to build the
extension with it. We must force the use of Visual Studio 2015.

- clone this repository
- ``"%VS140COMNTOOLS%\..\..\VC\vcvarsall.bat" x64``
- ``set DISTUTILS_USE_SDK=1``
- ``set MSSdk=1``
- download ``qpdf-[latest version]-bin-msvc64.zip`` from the `QPDF releases page <https://github.com/qpdf/qpdf/releases>`_
- ``pip install .``

Note that this requires the user building ``pikepdf`` to have
registry edition rights on the machine, to be able to run the
``vcvarsall.bat`` script.

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
