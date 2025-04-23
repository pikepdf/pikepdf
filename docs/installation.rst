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

* ⚠️ wheel is released but cannot be tested - use with caution

Binary wheels should work on most systems, **provided a recent version
of pip is used to install them**. Old versions of pip, especially before 20.0,
may fail to check appropriate versions.

macOS 14 or newer is typically required for binary wheels. Older versions may
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

    pkg install py311-pikepdf

To attempt a manual install, try something like:

.. code-block:: bash

    pkg install python3 py311-lxml py311-pip py311-pybind11 qpdf
    pip install --user pikepdf

This procedure is known to work on FreeBSD 13.4 and 14.1.


PyPy3 support
-------------

PyPy3 is supported in certain configurations as listed in the binary wheel
availability table above.

PyPy3 is not more performant than CPython for pikepdf, because the core of pikepdf
is already written in C++. The benefit is for applications that want to use PyPy
for improved performance of native Python and also want to use pikepdf.
