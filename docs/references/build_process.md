# Build process notes

This section contains notes on complexities in the GitHub Actions
build-deploy workflow.

For general build instructions, see {ref}`source-build`.

## Crypto provider

We build libqpdf with `-DREQUIRE_CRYPTO_NATIVE=1 -DUSE_IMPLICIT_CRYPTO=OFF` on
every POSIX platform, so qpdf uses its own MD5/RC4/SHA2/AES implementations and
links no TLS library at all.

This traces back to <https://github.com/pikepdf/pikepdf/issues/520>, where
legacy encrypted PDFs failed to open on macOS. The cause was Homebrew's openssl
retiring its legacy provider, which qpdf needs for the RC4 and MD5 that older
PDFs use. At the time we switched macOS to gnutls, believing that matched the
Linux builds.

It did not. The manylinux and musllinux images ship neither gnutls-devel nor
openssl-devel, so `USE_IMPLICIT_CRYPTO` had been quietly falling back to native
on Linux all along -- the two platforms were never aligned, and Linux wheels
have been opening legacy encrypted files on native crypto without complaint
ever since.

Native crypto is the better answer to #520 than either external provider: it
implements the weak algorithms itself, so no upstream deprecation policy can
take them away. It also removes nine vendored dylibs (gnutls, nettle, hogweed,
gmp, idn2, unistring, tasn1, p11-kit, intl) and their LGPL obligations from
macOS wheels.

Selecting the provider explicitly rather than relying on the implicit fallback
also keeps `third-party-licenses/` accurate: a build image that gained gnutls
or openssl headers would otherwise add a bundled dependency that the license
manifest does not describe.

qpdf's manual notes that external crypto providers should be preferred "in
nearly all cases" while calling native "fully supported". The preference is
about hardware acceleration and independent vetting; pikepdf uses crypto only
for PDF encryption, which is weak by specification, so the tradeoff favours
having no external dependency.

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
