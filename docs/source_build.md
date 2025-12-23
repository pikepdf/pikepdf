---
myst:
  substitutions:
    msvc_zip: qpdf-{{ qpdf_version }}-bin-msvc64.zip
---

(source-build)=

# Building from source

If you are a developer and you want to build from source, follow these steps.

## Requirements

pikepdf requires:

- a C++20 compliant compiler
- [Meson](https://mesonbuild.com/) >= 1.2.0 build system
- [pybind11](https://github.com/pybind/pybind11)
- libqpdf {{ qpdf_min_version }} or higher from the
  [qpdf](https://qpdf.org) project.

On Linux the library and headers for libqpdf must be installed because pikepdf
compiles code against it and links to it.

Check [Repology for qpdf](https://repology.org/project/qpdf/badges) to
see if a recent version of qpdf is available for your platform. Otherwise you
must
[build qpdf from source](https://github.com/qpdf/qpdf?tab=readme-ov-file#building-from-source-distribution-on-unixlinux).
(Consider using the binary wheels, which bundle the required version of
libqpdf.)

:::{note}
pikepdf should be built with the same compiler and linker as libqpdf; to be
precise both **must** use the same C++ ABI. On some platforms, Meson may
not pick the correct compiler so one may need to set environment variables
`CC` and `CXX` to redirect it. If the wrong compiler is selected,
`import pikepdf._core` will throw an `ImportError` about a missing
symbol.
:::

## {fa}`linux` {fa}`apple` GCC or Clang, linking to system libraries

To link to system libraries (the ones installed by your package manager, such
`apt`, `brew` or `dnf`:

- Clone the pikepdf repository
- Install libjpeg, zlib and libqpdf on your platform, including headers
- If desired, activate a virtual environment
- Run `pip install .`

## {fa}`linux` {fa}`apple` GCC or Clang and linking to user libraries

pikepdf's Meson build will check the following locations, in the order given here, for
qpdf's headers and libraries (both of which are required for a build):
1. the paths specified by Meson options `-Dqpdf_source_tree=...` and
   `-Dqpdf_build_libdir=...`
1. a folder named `qpdf` that is installed parallel to `pikepdf`, e.g. if pikepdf is
   located in `$HOME/src/pikepdf`, then we check `$HOME/src/qpdf` for qpdf
1. the system default's location for these resources (via pkg-config)

If you wish to link pikepdf against a different version of the qpdf (say,
because pikepdf requires a newer version than your operating system has),
then you might do something like:

- Install the development headers for libjpeg and zlib (e.g. `apt install libjpeg-dev`)

- Build qpdf from source and run `cmake --install` to install it to `/usr/local`

- Clone the pikepdf repository

- From the pikepdf directory, run

  > ```bash
  > pip install .
  > ```
  >
  > (Meson will find libqpdf via pkg-config if it was installed to a standard location.)

### {fa}`windows` On Windows (requires Visual Studio 2015)

pikepdf requires a C++20 compliant compiler.
See our continuous integration build script in `.appveyor.yml`
for detailed and current instructions. Or use the wheels which save this pain.

These instructions require the precompiled binary `qpdf.dll`. See the qpdf
documentation if you also need to build this DLL from source. Both should be
built with the same compiler. You may not mix and match MinGW and Visual C++
for example.

Running a regular `pip install` command will detect the
version of the compiler used to build Python and attempt to build the
extension with it. We must force the use of Visual Studio 2015.

- Clone this repository.

- In a command prompt, run:

  > ```bat
  > %VS140COMNTOOLS%\..\..\VC\vcvarsall.bat" x64
  > set DISTUTILS_USE_SDK=1
  > set MSSdk=1
  > ```

- Download {{ msvc_zip }} from the [qpdf releases page](https://github.com/qpdf/qpdf/releases).

- Extract `bin\*.dll` (all the DLLs, both qpdf's and the Microsoft Visual C++
  Runtime library) from the zip file above, and copy it to the `src/pikepdf`
  folder in the repository.

- Run `pip install .` in the root directory of the repository.

:::{note}
The user compiling `pikepdf` to must have registry editing rights on the
machine to be able to run the `vcvarsall.bat` script.
:::

## {fa}`linux` {fa}`apple` Building against a qpdf source tree

Follow these steps to build pikepdf against a different version of qpdf, rather than
the one provided with your operating system. This may be useful if you need a more
recent version of qpdf than your operating system package manager provides, and you
do not want to use Python wheels.

If you have qpdf checked out as a sibling directory to pikepdf (i.e., `../qpdf`),
pikepdf's build system will auto-detect it. Otherwise, use the Meson options below.

```bash
# Build libqpdf from source
cd $QPDF_SOURCE_TREE
cmake -S . -B build -DCMAKE_BUILD_TYPE=RelWithDebInfo -DBUILD_SHARED_LIBS=ON
cmake --build build --parallel --target libqpdf
QPDF_BUILD_LIBDIR=$PWD/build/libqpdf

# Create a fresh virtual environment
cd $PIKEPDF_SOURCE_TREE
python3 -m venv .venv
source .venv/bin/activate

# Build pikepdf from source (auto-detects ../qpdf if present)
pip install -e .

# Or specify paths explicitly using meson setup options via pip:
pip install -e . -Csetup-args=-Dqpdf_source_tree=$QPDF_SOURCE_TREE \
                 -Csetup-args=-Dqpdf_build_libdir=$QPDF_BUILD_LIBDIR
```

Note that the Python wheels for pikepdf currently compile their own version of
qpdf and several of its dependencies to ensure the wheels have the latest version.
You can also refer to the GitHub Actions YAML files for build steps.

## {fa}`windows` Building against a qpdf source tree

Using Visual Studio C++:

- `winget install git.git`
- `winget install python.python.3.12`
- `winget install  Microsoft.VisualStudio.2022.BuildTools`
- `winget install kitware.cmake`

Download qpdf external libs and unpack in place.

```powershell
wget https://github.com/qpdf/external-libs/releases/download/release-$version/qpdf-external-libs-bin.zip -Outfile libs.zip
expand-archive -path libs.zip -destinationpath .
```

Download qpdf and build from source using:

```powershell
cd $qpdf
cmake -S . -B build
cmake --build build --config Release
```

Switch to pikepdf source folder. Set up environment variables and get pip to build/install:

```powershell
cd $pikepdf
$env:INCLUDE = "$qpdf\include"
$env:LIB = "$qpdf\build\libqpdf\Release\"
cp $LIB\libqpdfXX.dll src\pikepdf  # Help Python loader find libqpdf.dll
python -m venv .venv
.venv\scripts\activate
pip install -e .
```

## Building the documentation

Documentation is generated using Sphinx and you are currently reading it. To
regenerate it:

```bash
pip install pikepdf[docs]
cd docs
make html
```
