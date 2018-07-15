Installation
============

Most users on Linux, macOS or Windows with x64 systems should take advantage of
the binary wheels.

- ``pip install pikepdf``

32-bit wheels will be added if there is any sign of demand for them.

The binary wheels should work on most systems work on Linux distributions 2012
and newer, macOS 10.11 and newer (for Homebrew), Windows 7 and newer.

Building from source
--------------------

**From source (GCC or Clang)**

A C++11 compliant compiler is required, which includes most recent versions of
GCC (4.8 and up) and clang (3.3 and up). A C++14 compiler is recommended and
will produce smaller binaries.

libqpdf 8.0.2 is required at compile time and runtime. Many platforms have not
updated to this version, so you may need to build this package from source.

-  clone this repository
-  install libjpeg, zlib and qpdf on your platform, including headers
-  ``pip install .``

**On Windows (Requires Visual Studio 2015)**

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
- download `qpdf binaries for MSVC <https://github.com/qpdf/qpdf/releases/download/release-qpdf-8.0.2/qpdf-8.0.2-bin-msvc64.zip>`_
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
