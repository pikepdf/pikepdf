Installation
============

.. figure:: images/pike-tree.jpg
    :scale: 50%
    :alt: Picture of pike fish impaled on tree branch
    :align: right

    A pike installation failure.

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

**Linux users:** If you have an older version of ``pip``, such as the one that ships
with Ubuntu 18.04, this command will attempt to compile the project instead of
installing the wheel. If you want to get the binary wheel, upgrade ``pip`` with:

.. code-block:: bash

    wget https://bootstrap.pypa.io/get-pip.py && python3 get-pip.py
    pip --version  # should be 20.0 or newer
    pip install pikepdf

32- and 64-bit wheels are available for Windows, Linux and macOS. Binary wheels
should work on most systems, i.e. Linux distributions 2010 and newer, macOS
10.11 and newer (for Homebrew), Windows 7 and newer, **provided a recent version
of pip is used to install them**. The Linux wheels currently include copies of
libqpdf, libjpeg, and zlib. The Windows wheels include libqpdf. This is to ensure
that up-to-date, compatible copies of dependent libraries are included.

Currently we do not build wheels for architectures other than x86 and x64.

`Alpine Linux`_ does not support Python wheels.

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

    pkg install py37-pikepdf

To attempt a manual install, try something like:

.. code-block:: bash

    pkg install python3 py37-lxml py37-pip py37-pybind11 qpdf
    pip install --user pikepdf

This procedure is known to work on FreeBSD 11.3, 12.0, 12.1-RELEASE and
13.0-CURRENT. It has not been tested on other versions.

Building from source
--------------------

**Requirements**

.. |qpdf-version| replace:: 10.0.3

pikepdf requires:

-   a C++14 compliant compiler - GCC (5 and up), clang (3.3 and up), MSVC
    (2015 or newer)
-   `pybind11 <https://github.com/pybind/pybind11>`_
-   libqpdf |qpdf-version| or higher from the
    `QPDF <https://github.com/qpdf/qpdf>`_ project.

On Linux the library and headers for libqpdf must be installed because pikepdf
compiles code against it and links to it.

Check `Repology for QPDF <https://repology.org/project/qpdf/badges>`_ to
see if a recent version of QPDF is available for your platform. Otherwise you
must
`build QPDF from source <https://github.com/qpdf/qpdf/blob/master/INSTALL>`_.
(Consider using the binary wheels, which bundle the required version of
libqpdf.)

**Compiling with GCC or Clang**

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

pikepdf requires a C++14 compliant compiler (i.e. Visual Studio 2015 on
Windows). See our continuous integration build script in ``.appveyor.yml``
for detailed and current instructions. Or use the wheels which save this pain.

These instructions require the precompiled binary ``qpdf.dll``. See the QPDF
documentation if you also need to build this DLL from source. Both should be
built with the same compiler. You may not mix and match MinGW and Visual C++
for example.

Running a regular ``pip install`` command will detect the
version of the compiler used to build Python and attempt to build the
extension with it. We must force the use of Visual Studio 2015.

#. Clone this repository.
#. In a command prompt, run:

    .. code-block:: bat

        %VS140COMNTOOLS%\..\..\VC\vcvarsall.bat" x64
        set DISTUTILS_USE_SDK=1
        set MSSdk=1

#. Download |msvc-zip| from the `QPDF releases page <https://github.com/qpdf/qpdf/releases>`_.
#. Extract ``bin\*.dll`` (all the DLLs, both QPDF's and the Microsoft Visual C++
   Runtime library) from the zip file above, and copy it to the ``src/pikepdf``
   folder in the repository.
#. Run ``pip install .`` in the root directory of the repository.

.. note::

    The user compiling ``pikepdf`` to must have registry editing rights on the
    machine to be able to run the ``vcvarsall.bat`` script.

**Building against a QPDF source tree**

Follow these steps to build pikepdf against a different version of QPDF, rather than
the one provided with your operating system. This may be useful if you need a more
recent version of QPDF than your operating system package manager provides, and you
do not want to use Python wheels.

* Set the environment variable ``QPDF_SOURCE_TREE`` to the location of the QPDF source
  tree.

* Build QPDF, by running ``make``. Refer to the QPDF installation instructions for
  further options and details.

* On Linux, modify ``LD_LIBRARY_PATH``, prepending the path where the QPDF build
  produces ``libqpdfXX.so``. This might be something like
  ``$QPDF_SOURCE_TREE/.build/libs/libqpdfXX.so``. On macOS, locate the equivalent
  variable is ``DYLD_LIBRARY_PATH``. On Windows, no action is needed. Generally,
  what you are doing here is telling the runtime dynamic linker to use the custom
  compiled version of QPDF instead of the system version.

* Build pikepdf. On Windows, locate the QPDF .dll files and copy them into the folder
  alongside the file named ``_qpdf*.dll``.

Note that the Python wheels for pikepdf currently compile their own version of
QPDF and several of its dependencies to ensure the wheels have the latest version.
You can also refer to the GitHub Actions YAML files for build steps.

**Building against a custom install of QPDF to /usr/local/lib**

If you have previously installed a QPDF from source to ``/usr/local/lib`` on
a POSIX platform, and you try to build pikepdf from source, it will prefer the
operating system version of QPDF installed at ``/usr/lib``. Since pikepdf strongly
prefers recent versions of QPDF, you may want to use a more current version.

From a Git checkout of the pikepdf source tree, run:

.. code-block:: bash

    env LDFLAGS='-L/usr/local/lib' CFLAGS='-I/usr/local/include/qpdf' pip install .

Building the documentation
--------------------------

Documentation is generated using Sphinx and you are currently reading it. To
regenerate it:

.. code-block:: bash

    pip install -r requirements/docs.txt
    cd docs
    make html

PyPy3 support
-------------

PyPy3 3.6 and 3.7 are currently supported. However, binary wheels for PyPy3 are not
available for some platforms, since some dependencies of pikepdf (namely lxml) do not
yet generate PyPy3 wheels of their own.

+----------------+------------------------+-------+
| Platform       | Source build supported | Wheel |
+================+========================+=======+
| Windows 64-bit | ✅                     |       |
+----------------+------------------------+-------+
| Linux 64-bit   | ✅                     |       |
+----------------+------------------------+-------+
| macOS          | ✅                     | ✅    |
+----------------+------------------------+-------+

PyPy3 is not more performant than CPython for pikepdf, because the core of pikepdf
is already written in C++. The benefit is for applications that want to use PyPy
for improved performance of native Python and also want to use pikepdf.
