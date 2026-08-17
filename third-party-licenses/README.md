<!-- SPDX-FileCopyrightText: 2026 James R. Barlow -->
<!-- SPDX-License-Identifier: MPL-2.0 -->

# Third-party components in pikepdf binary wheels

pikepdf itself is licensed under the Mozilla Public License 2.0 (MPL-2.0); see
`LICENSE.txt` in the distribution root. That is the license of *pikepdf's own
source code*, and it is what the package's `License-Expression` metadata field
declares.

pikepdf **source distributions** (sdists) contain only pikepdf's own code and
carry no third-party binaries.

pikepdf **binary wheels** additionally contain compiled third-party libraries
that the wheel-repair tools (`auditwheel` on Linux, `delocate` on macOS,
`delvewheel` on Windows) vendored into the wheel so it is self-contained. This
file is the attribution and license mapping for those components. The license
texts referenced below are distributed alongside this file, and every file in
this directory is listed in the wheel's `License-File` metadata.

None of the components below change pikepdf's own license. They are separate
works redistributed in unmodified binary form.

## Which components are in which wheel

Exact upstream versions move between pikepdf releases. The versions in the
"Version" column were those in pikepdf 10.11.0 and are given as a concrete
example, not a guarantee. To determine the versions in a specific wheel:

- Linux wheels carry a CycloneDX SBOM at
  `pikepdf-<version>.dist-info/sboms/auditwheel.cdx.json` that names each
  vendored system library and its distribution package version.
- The qpdf version is reported at runtime by `pikepdf.__libqpdf_version__`.

### All platforms

| Component | Version | How it is included | License | Text |
| --- | --- | --- | --- | --- |
| [qpdf](https://github.com/qpdf/qpdf) | 12.3.2 | separate shared library (`libqpdf`/`qpdf30.dll`) | Apache-2.0 | [`qpdf.txt`](qpdf.txt) |
| [libjpeg-turbo](https://libjpeg-turbo.org/) | varies, see below | separate shared library on Linux/macOS; statically linked into `qpdf30.dll` on Windows | IJG + BSD-3-Clause + Zlib | [`libjpeg-turbo.txt`](libjpeg-turbo.txt), [`libjpeg-turbo-README.ijg.txt`](libjpeg-turbo-README.ijg.txt) |

libjpeg-turbo comes from the build platform, so its version differs per wheel:
1.5.3 (manylinux, AlmaLinux 8), 3.1.0 (musllinux, Alpine), 3.2.0 (macOS,
Homebrew). The IJG portion of its license requires that
`libjpeg-turbo-README.ijg.txt` accompany redistribution, so it is included.

### Windows wheels only

The Windows wheel uses qpdf's official `msvc64` binary release. That build
statically links OpenSSL and zlib into `pikepdf.libs/qpdf30-<hash>.dll`; there
is no separate `libcrypto` or `zlib` DLL in the wheel.

| Component | Version | How it is included | License | Text |
| --- | --- | --- | --- | --- |
| [OpenSSL](https://www.openssl.org/) | 3.6.0 | **statically linked** into `qpdf30-<hash>.dll`; provides qpdf's `QPDFCrypto_openssl` crypto backend | Apache-2.0 | [`openssl.txt`](openssl.txt) |
| [zlib](https://zlib.net/) | 1.3.1 | **statically linked** into `qpdf30-<hash>.dll` | Zlib | [`zlib.txt`](zlib.txt) |
| Microsoft Visual C++ Runtime | 14.x | separate DLL, `pikepdf.libs/msvcp140-<hash>.dll` | Microsoft Distributable Code terms | [`microsoft-visual-cpp-runtime.txt`](microsoft-visual-cpp-runtime.txt) |

### musllinux wheels only

| Component | Version | Library | License | Text |
| --- | --- | --- | --- | --- |
| GCC runtime libraries | 14.2.0 | `libstdc++-<hash>.so.6`, `libgcc_s-<hash>.so.1` | GPL-3.0-or-later **with** GCC Runtime Library Exception 3.1 | [`GPL-3.0.txt`](GPL-3.0.txt), [`GCC-exception-3.1.txt`](GCC-exception-3.1.txt) |

The GCC Runtime Library Exception permits redistribution of these libraries
with independent works without imposing GPL terms on those works.

### Not bundled

For reference, these are *not* redistributed in pikepdf wheels:

- **OpenSSL and GnuTLS on Linux and macOS.** These builds of qpdf select its
  built-in `QPDFCrypto_native` backend explicitly
  (`-DREQUIRE_CRYPTO_NATIVE=1 -DUSE_IMPLICIT_CRYPTO=OFF`). No TLS or crypto
  library is linked or vendored. Only the Windows wheel contains OpenSSL, and
  there it is statically linked inside qpdf's own DLL.
- **zlib on Linux and macOS.** `libqpdf` links the platform's system zlib,
  which is not copied into the wheel.
- **The Python interpreter's own runtime.** On Windows, `vcruntime140.dll` is
  supplied by CPython, not by pikepdf.

## Reporting a problem with this file

If you are performing a compliance review and find a component that is present
in a wheel but missing here, or a mapping that looks wrong, please open an issue
at https://github.com/pikepdf/pikepdf/issues — that is a bug in this file and we
want to fix it.
