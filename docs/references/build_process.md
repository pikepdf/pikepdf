# Build process notes

This section contains notes on complexities in the GitHub Actions
build-deploy workflow.

For general build instructions, see {ref}`source-build`.

## Crypto provider

qpdf can get its MD5, RC4, SHA-2 and AES from its own native implementation, from
OpenSSL, or from GnuTLS. Which one a wheel ends up with depends on how that
platform obtains libqpdf.

On Linux and macOS we compile libqpdf ourselves, and select the provider
explicitly:

```
cmake -DREQUIRE_CRYPTO_NATIVE=1 -DUSE_IMPLICIT_CRYPTO=OFF ...
```

See `build-scripts/posix-build-wheel-deps.bash`. This is the only provider
compiled in, so those wheels link no TLS library at all.

On Windows we do not build qpdf. `build-scripts/win-download-qpdf.ps1` downloads
qpdf's official `msvc64` release, which statically links OpenSSL into
`qpdf30.dll`. Both `openssl` and `native` are compiled into that binary and
OpenSSL is the default, per qpdf's `gnutls > openssl > native` precedence. We
have no build-time control over this short of compiling qpdf from source on
Windows.

Two reasons to keep the POSIX selection explicit rather than letting
`USE_IMPLICIT_CRYPTO` choose:

- It is deterministic. The implicit setting picks whatever headers happen to be
  present in the build image, so a base image that gained `gnutls-devel` would
  silently change what we ship.
- It keeps `third-party-licenses/` honest. An implicitly acquired dependency
  would be vendored into the wheel without appearing in the license manifest.

The user-facing consequences of this choice — what native crypto costs in
assurance, and how to get a different provider — are documented in
{ref}`security`. Keep the two in sync when changing the build.

## macOS generally

Here are the current constraints for building on macOS:

- General rule for macOS: build on the oldest available macOS runner,
  and set `MACOSX_DEPLOYMENT_TARGET="that version.0"`, e.g. macos-14 and
  `MACOSX_DEPLOYMENT_TARGET="14.0"`
- QPDF needs at least `MACOSX_DEPLOYMENT_TARGET="11.0"` since it uses
  C++20.
- Homebrew requires macOS 13+, and we depend on it so we can't support
  older versions.
- Homebrew creates binaries with MACOSX_DEPLOYMENT_TARGET="macos-x".
  Therefore, we should build on the minimum runner. For x86_64 that is
  macos-15-intel.
- Setting `SYSTEM_VERSION_COMPAT=0` was necessary for pip to understand
  `MACOSX_DEPLOYMENT_TARGET="13.0"` rather than macOS X 10.x syntax.
  Should not be necessary from here on.
- GitHub introduced macos-15-intel as a way of requested Intel runners.
  There are no macos-14-intel images and it's unclear if macos-15 is
  capable of supporting it. We try anyway, by setting
  `MACOSX_DEPLOYMENT_TARGET = "14.0"`.
- GitHub's macos-14 runner is the first to be Apple Silicon. Since we
  use Homebrew, it can only build macos-14. We only support macos-14
  for arm64. Cirrus CI did support earlier macos. We no longer use
  Cirrus for Apple Silicon, just for Linux ARM64.

Taking a quick peek at numpy, it may be easier to build universal2 wheels and use QEMU
to confirm that they work. That would be another big build overhaul.

Users who build from source have more options and can likely get
functional builds on anything newer than macOS 14.

## Historical decisions

Background on choices that are no longer current, kept because the reasoning
explains how we arrived at the present configuration.

### macOS used GnuTLS from v8.11.1 to v10.12.0

macOS wheels once linked GnuTLS. This came from {issue}`520`: legacy encrypted
PDFs stopped opening on macOS, because Homebrew's OpenSSL had moved RC4 and MD5
into its legacy provider, which is not loaded by default. qpdf needs those
algorithms for `/R` 2, 3 and 4 documents. Switching macOS to GnuTLS restored
them, and the change was made on the understanding that it aligned macOS with
the Linux builds.

It did not. The manylinux and musllinux images ship neither `gnutls-devel` nor
`openssl-devel`, so `USE_IMPLICIT_CRYPTO` had been quietly falling back to
native on Linux the whole time. The platforms were never aligned, and Linux
wheels had been opening legacy encrypted files on native crypto without
complaint.

Native crypto turned out to be a better answer to {issue}`520` than either
external provider, because it implements the weak algorithms itself and no
upstream deprecation policy can withdraw them. Moving macOS to native also
dropped nine vendored dylibs (gnutls, nettle, hogweed, gmp, idn2, unistring,
tasn1, p11-kit, intl), their LGPL obligations, and about 10 MB per wheel.

### macOS used Homebrew's qpdf before v8.11.1

Before {issue}`520` we linked against Homebrew's prebuilt qpdf rather than
building libqpdf ourselves. That is what exposed us to Homebrew's OpenSSL
configuration in the first place. Building libqpdf ourselves on every POSIX
platform is what makes the crypto provider ours to choose.
