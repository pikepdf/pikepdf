Debugging
=========

pikepdf does a complex job in providing bindings from Python to a C++ library,
both of which have different ideas about how to manage memory. This page
documents some methods that may help should it be necessary to debug the Python
C++ extension (``pikepdf._qpdf``).

Compiling a debug build of QPDF
-------------------------------

It may be helpful to create a debug build of QPDF.

Download QPDF and compile a debug build:

.. code-block:: bash

    # in QPDF source tree
    cd $QPDF_SOURCE_TREE
    ./configure CFLAGS='-g -O0' CPPFLAGS='-g -O0' CXXFLAGS='-g -O0'
    make -j

Compile and link against QPDF source tree
-----------------------------------------

Build ``pikepdf._qpdf`` against the version of QPDF above, rather than the
system version:

.. code-block:: bash

    env QPDF_SOURCE_TREE=<location of QPDF> python setup.py build_ext --inplace

When running Python, ensure that you override shared library load locations:

.. code-block:: bash

    # Linux
    env LD_LIBRARY_PATH=$QPDF_SOURCE_TREE/libqpdf/build/.libs python ...

.. code-block:: bash

    # macOS - may require disabling System Integrity Protection
    env DYLD_LIBRARY_PATH=$QPDF_SOURCE_TREE/libqpdf/build/.libs python ...

You can also run Python through a debugger (``gdb`` or ``lldb``) in this manner,
and you will have access to the source code for both pikepdf's C++ and QPDF.

Valgrind
--------

Valgrind may also be helpful - see the Python `documentation`_ for information
on setting up Python and Valgrind.

.. _documentation: https://github.com/python/cpython/blob/d5d33681c1cd1df7731eb0fb7c0f297bc2f114e6/Misc/README.valgrind
