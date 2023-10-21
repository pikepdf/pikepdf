Installation
============

Basic installation
------------------

.. |latest| image:: https://img.shields.io/pypi/v/pikepdf.svg
    :alt: pikepdf latest released version on PyPI

|latest|

Most users on Linux, macOS or Windows with x64 systems should use ``pip`` to
install pikepdf in their current Python environment (such as your project's
virtual environment).

.. code-block:: bash

    pip install pikepdf

Use ``pip install --user pikepdf`` to install the package for the current user
only. Use ``pip install pikepdf`` to install to a virtual environment.

Binary wheel availability
-------------------------

.. csv-table:: Python binary wheel availability
    :file: binary-wheels.csv
    :header-rows: 1

* ✅ wheels are available

* ❌ wheels are not likely to be produced for this platform and Python version

* ⏳ we are waiting on a third party to implement better support for this configuration

Binary wheels should work on most systems, **provided a recent version
of pip is used to install them**. Old versions of pip, especially before 20.0,
may fail to check appropriate versions.

macOS 10.14 or newer is typically required for binary wheels. Older versions may
work if compiled from source.

Windows 7 or newer is required. Windows wheels include a recent copy of libqpdf.

Most Linux distributions support manylinux2014, with the notable except of
`Alpine Linux`_, and older Linux distributions that do not have C++17-capable
compilers. The Linux wheels include recent copies of libqpdf, libjpeg, and zlib.

Source builds are usually possible where binary wheels are available.

Platform support
----------------

Some platforms include versions of pikepdf that are distributed by the system
package manager (such as ``apt``). These versions may lag behind the version
distributed with PyPI, but may be convenient for users that cannot use binary
wheels.

.. figure:: /images/sushi.jpg
   :align: right
   :alt: Bento box containing sushi
   :figwidth: 40%

   Packaged fish.

.. |python-pikepdf| image:: https://repology.org/badge/vertical-allrepos/python:pikepdf.svg
    :alt: Package status for python:pikepdf

|python-pikepdf|


Debian, Ubuntu and other APT-based distributions
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

.. code-block:: bash

    apt install pikepdf

Fedora
^^^^^^

.. |fedora| image:: https://repology.org/badge/version-for-repo/fedora_rawhide/python:pikepdf.svg
    :alt: Fedora Rawhide

|fedora|

.. code-block:: bash

    dnf install python-pikepdf

Alpine Linux
^^^^^^^^^^^^

.. |alpine| image:: https://repology.org/badge/version-for-repo/alpine_edge/python:pikepdf.svg
    :alt: Alpine Linux Edge

|alpine|

.. code-block:: bash

    apk add py3-pikepdf

Installing on FreeBSD
---------------------

.. |freebsd| image:: https://repology.org/badge/version-for-repo/freebsd/python:pikepdf.svg
    :alt: FreeBSD
    :target: https://repology.org/project/python:pikepdf/versions

.. code-block:: bash

    pkg install py38-pikepdf

To attempt a manual install, try something like:

.. code-block:: bash

    pkg install python3 py38-lxml py38-pip py38-pybind11 qpdf
    pip install --user pikepdf

This procedure is known to work on FreeBSD 11.3, 12.0, 12.1-RELEASE and
13.0-CURRENT. It has not been tested on other versions.

Building from source
--------------------

Requirements
^^^^^^^^^^^^

pikepdf requires:

-   a C++17 compliant compiler - roughly GCC 7+, clang 6+, or MSVC 19+
-   `pybind11 <https://github.com/pybind/pybind11>`_
-   libqpdf |qpdf-min-version| or higher from the
    `QPDF <https://github.com/qpdf/qpdf>`_ project.

On Linux the library and headers for libqpdf must be installed because pikepdf
compiles code against it and links to it.

Check `Repology for QPDF <https://repology.org/project/qpdf/badges>`_ to
see if a recent version of QPDF is available for your platform. Otherwise you
must
`build QPDF from source <https://github.com/qpdf/qpdf/blob/main/INSTALL>`_.
(Consider using the binary wheels, which bundle the required version of
libqpdf.)

.. note::

    pikepdf should be built with the same compiler and linker as libqpdf; to be
    precise both **must** use the same C++ ABI. On some platforms, setup.py may
    not pick the correct compiler so one may need to set environment variables
    ``CC`` and ``CXX`` to redirect it. If the wrong compiler is selected,
    ``import pikepdf._core`` will throw an ``ImportError`` about a missing
    symbol.

:fa:`linux` :fa:`apple` GCC or Clang, linking to system libraries
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

To link to system libraries (the ones installed by your package manager, such
``apt``, ``brew`` or ``dnf``:

-  Clone the pikepdf repository
-  Install libjpeg, zlib and libqpdf on your platform, including headers
-  If desired, activate a virtual environment
-  Run ``pip install .``

:fa:`linux` :fa:`apple` GCC or Clang and linking to user libraries
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

setuptools will normally attempt to link against your system libraries.
If you wish to link pikepdf against a different version of the QPDF (say,
because pikepdf requires a newer version than your operating system has),
then you might do something like:

-  Install the development headers for libjpeg and zlib (e.g. ``apt install libjpeg-dev``)
-  Build qpdf from source and run ``cmake --install`` to install it to ``/usr/local``
-  Clone the pikepdf repository
-  From the pikepdf directory, run

    .. code-block:: bash

        env CXXFLAGS=-I/usr/local/include/libqpdf LDFLAGS=-L/usr/local/lib  \
            pip install .

:fa:`windows` On Windows (requires Visual Studio 2015)
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

.. |msvc-zip| replace:: qpdf-|qpdf-version|-bin-msvc64.zip

pikepdf requires a C++17 compliant compiler (i.e. Visual Studio 2015 on
Windows). See our continuous integration build script in ``.appveyor.yml``
for detailed and current instructions. Or use the wheels which save this pain.

These instructions require the precompiled binary ``qpdf.dll``. See the QPDF
documentation if you also need to build this DLL from source. Both should be
built with the same compiler. You may not mix and match MinGW and Visual C++
for example.

Running a regular ``pip install`` command will detect the
version of the compiler used to build Python and attempt to build the
extension with it. We must force the use of Visual Studio 2015.

-  Clone this repository.
-  In a command prompt, run:

    .. code-block:: bat

        %VS140COMNTOOLS%\..\..\VC\vcvarsall.bat" x64
        set DISTUTILS_USE_SDK=1
        set MSSdk=1

-  Download |msvc-zip| from the `QPDF releases page <https://github.com/qpdf/qpdf/releases>`_.
-  Extract ``bin\*.dll`` (all the DLLs, both QPDF's and the Microsoft Visual C++
   Runtime library) from the zip file above, and copy it to the ``src/pikepdf``
   folder in the repository.
-  Run ``pip install .`` in the root directory of the repository.

.. note::

    The user compiling ``pikepdf`` to must have registry editing rights on the
    machine to be able to run the ``vcvarsall.bat`` script.

:fa:`linux` :fa:`apple` :fa:`windows` Building against a QPDF source tree
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Follow these steps to build pikepdf against a different version of QPDF, rather than
the one provided with your operating system. This may be useful if you need a more
recent version of QPDF than your operating system package manager provides, and you
do not want to use Python wheels.

.. code-block:: bash

    # Build libqpdf from source
    cd $QPDF_SOURCE_TREE
    cmake -S . -B build -DCMAKE_BUILD_TYPE=RelWithDebInfo -DBUILD_SHARED_LIBS=ON
    cmake --build build --parallel --target libqpdf
    QPDF_BUILD_LIBDIR=$PWD/build/libqpdf

    # Build pikepdf against the custom libqpdf
    cd $PIKEPDF_SOURCE_TREE
    env QPDF_SOURCE_TREE=$QPDF_SOURCE_TREE QPDF_BUILD_LIBDIR=$QPDF_BUILD_LIBDIR \
        pip install -e .

Note that the Python wheels for pikepdf currently compile their own version of
QPDF and several of its dependencies to ensure the wheels have the latest version.
You can also refer to the GitHub Actions YAML files for build steps.

Building the documentation
--------------------------

Documentation is generated using Sphinx and you are currently reading it. To
regenerate it:

.. code-block:: bash

    pip install pikepdf[docs]
    cd docs
    make html

PyPy3 support
-------------

PyPy3 is supported in certain configurations as listed in the binary wheel
availability table above.

PyPy3 is not more performant than CPython for pikepdf, because the core of pikepdf
is already written in C++. The benefit is for applications that want to use PyPy
for improved performance of native Python and also want to use pikepdf.
