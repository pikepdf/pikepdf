# Debugging

pikepdf does a complex job in providing bindings from Python to a C++ library,
both of which have different ideas about how to manage memory. This page
documents some methods that may help should it be necessary to debug the Python
C++ extension (`pikepdf._core`).

## Using gdb to debug C++ and Python

Current versions of gdb can debug Python and C++ code simultaneously. See
the Python developer's guide on [gdb Support]. To use this effectively, a debug
build of pikepdf and qpdf should be created.

## Compiling a debug build of qpdf

To download qpdf and compile a debug build:

```bash
# in qpdf source tree
cd $QPDF_SOURCE_TREE
cmake -S . -B build -DENABLE_QTC=ON -DCMAKE_BUILD_TYPE=Debug
cmake --build build -j
```

## Compile and link against qpdf source tree

Build `pikepdf._core` against the version of qpdf above, rather than the
system version:

```bash
env QPDF_SOURCE_TREE=<location of qpdf> \
  QPDF_BUILD_LIBDIR=<directory containing libqpdf.so> \
  python setup.py build_ext --inplace
```

The libqpdf.so file should be located in the `libqpdf` subdirectory of your cmake
build directory but may be in a subdirectory of that if you are using a
multi-configuration generator with cmake. In addition to building against the qpdf
source, you'll need to force your operating system to load the locally compiled
version of qpdf instead of the installed version:

```bash
# Linux
env LD_LIBRARY_PATH=<directory containing libqpdf.so> python ...
```

```bash
# macOS - may require disabling System Integrity Protection
env DYLD_LIBRARY_PATH=<directory containing libqpdf.so> python ...
```

On macOS you can make the library persistent by changing the name of the library
to use in pikepdf's binary extension module:

```bash
install_name_tool -change /usr/local/lib/libqpdf*.dylib \
    $QPDF_BUILD_LIBDIR/libqpdf*.dylib \
    src/pikepdf/_core.cpython*.so
```

You can also run Python through a debugger (`gdb` or `lldb`) in this manner,
and you will have access to the source code for both pikepdf's C++ and qpdf.

## Enabling qpdf tracing

For builds of qpdf having ENABLE_QTC=ON, setting the environment variables
`TC_SCOPE=qpdf` and `TC_FILENAME=your_log_file.txt` will cause libqpdf to
log debug messages to the designated file. For example:

```bash
env TC_SCOPE=qpdf TC_FILENAME=libqpdf_log.txt python my_pikepdf_script.py
```

## Valgrind

Valgrind may also be helpful - see the Python [documentation] for information
on setting up Python and Valgrind.

## Profiling pikepdf

The standard Python profiling tools in {mod}`cProfile` work fine for many
purposes but cannot explore inside pikepdf's C++ functions.

The [py-spy] program can effectively profile time spent in Python or executing
C++ code and demangle many C++ names to the appropriate symbols.

Happily it also does not require recompiling in any special mode, unless one
desires more symbol information than libqpdf or the C++ standard library exports.

For best results, use py-spy to generate speedscope files and use the [speedscope]
application to view them. py-spy's SVG output is illegible due to long C++ template
names as of this writing.

To install profiling and use profiling software:

```bash
# From a virtual environment with pikepdf installed...

# Install
pip install py-spy
npm install -g speedscope  # may need sudo to install this

# Run profile on a script that executes some pikepdf code we want to profile
py-spy record --native --format speedscope -o profile.speedscope -- python some_script.py

# View results (this will open a browser window)
speedscope profile.speedscope
```

To profile pikepdf's test suite, ensure that you run `pytest -n0` to disable
multiple CPU usage, since py-spy cannot trace inside child processes.

## pymemtrace

[pymemtrace] is another helpful tool for diagnosing memory leaks.

[documentation]: https://github.com/python/cpython/blob/d5d33681c1cd1df7731eb0fb7c0f297bc2f114e6/Misc/README.valgrind
[gdb support]: https://devguide.python.org/gdb/
[py-spy]: https://github.com/benfred/py-spy
[pymemtrace]: https://pymemtrace.readthedocs.io/en/latest/index.html
[speedscope]: https://github.com/jlfwong/speedscope
