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
  uv pip install --no-build-isolation -e .
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

## ThreadSanitizer

pikepdf supports free-threaded Python, where data races in the C++ extension
are real bugs rather than something the GIL hides. [ThreadSanitizer] (TSan)
reports them as they happen. `tests/test_threading.py` holds the stress tests
written for this, and the `tsan.yml` GitHub Actions workflow runs the test suite
under TSan on every push.

TSan only sees code compiled with `-fsanitize=thread`, so the interpreter,
libqpdf and `pikepdf._core` all need to be instrumented. Building such an
interpreter takes a while; the [cpython_sanity] images provide one ready made,
with a matching clang. To reproduce what CI does, from the root of a pikepdf
checkout:

```bash
docker run --rm -it --security-opt seccomp=unconfined \
    -v "$PWD":/src:ro ghcr.io/nascheme/cpython-tsan:3.14t bash

# The rest runs inside the container
apt-get update && apt-get install -y cmake libjpeg-dev wget
cp -r /src /pikepdf && cd /pikepdf && rm -rf build qpdf .venv*
export PYENV_VERSION=$(cd / && pyenv global)  # ignore pikepdf's .python-version
export CFLAGS="-fsanitize=thread -g" CXXFLAGS="-fsanitize=thread -g" \
    LDFLAGS="-fsanitize=thread"

# libqpdf, instrumented, installed to /usr/local
set -a; . <(python build-scripts/environ-from-pyproject.py); set +a
bash build-scripts/posix-build-wheel-deps.bash

# pikepdf._core, instrumented, with debug information for readable reports
SKBUILD_CMAKE_BUILD_TYPE=RelWithDebInfo SKBUILD_INSTALL_STRIP=false \
    python -m pip install --group test .

cat /work/tsan_suppressions/cpython.txt tests/tsan_suppressions.txt > /tmp/supp.txt
export TSAN_OPTIONS="halt_on_error=0:suppressions=/tmp/supp.txt"
PYTHON_GIL=0 python -m pytest -n0 tests/test_threading.py
```

`--security-opt seccomp=unconfined` lets TSan turn off address space layout
randomization for itself, which it needs on kernels configured with a lot of
it; without the option the interpreter may refuse to start. `PYTHON_GIL=0`
keeps the GIL off even if some other extension module asks for it.

Reports are printed to stderr as they occur and the test run carries on. Add
`log_path=/tmp/tsan` to `TSAN_OPTIONS` to collect them in files instead, which
is necessary when running with pytest-xdist since its workers' stderr is not
shown.

`tests/tsan_suppressions.txt` lists the few reports that are known and not
pikepdf's to fix, each with its reason; CPython's own list covers the
interpreter. A report in pikepdf's code should be fixed rather than suppressed.
Most such reports have been a binding that calls into qpdf without first taking
the owning `Pdf`'s lock (`QpdfLockGuard` in `src/core/qpdf_lock.h`). Even a
getter needs the lock, because reading an object can make qpdf load it from the
file, which changes state that the whole `Pdf` shares.

TSan finds races, not deadlocks, in pikepdf's locks: they are built on
CPython's `PyMutex`, which TSan does not model. pikepdf's locks report a
deadlock between two `Pdf` objects themselves, as a {exc}`RuntimeError` (see
{ref}`callback-restrictions`); the threading tests also give up on any thread
that has not finished within a time limit.

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

[cpython_sanity]: https://github.com/nascheme/cpython_sanity
[documentation]: https://github.com/python/cpython/blob/d5d33681c1cd1df7731eb0fb7c0f297bc2f114e6/Misc/README.valgrind
[gdb support]: https://devguide.python.org/gdb/
[py-spy]: https://github.com/benfred/py-spy
[pymemtrace]: https://pymemtrace.readthedocs.io/en/latest/index.html
[speedscope]: https://github.com/jlfwong/speedscope
[threadsanitizer]: https://clang.llvm.org/docs/ThreadSanitizer.html
