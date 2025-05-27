# Build process notes

This section contains notes on complexities in the GitHub Actions
build-deploy workflow.

For general build instructions, see {ref}`source-build`.

## macOS crypto provider

Users reported trouble with open legacy encrypted files on macOS
specifically, e.g. <https://github.com/pikepdf/pikepdf/issues/520>

It appears this is because we were using Homebrew's qpdf which is
currently linked against Homebrew's openssl. The error came from
qpdf specifically not finding openssl's legacy crypto provider. How
exactly that comes about is unclear - it may be that delocate-wheel
is inconsistent, it may be Homebrew has disabled the legacy
provider, etc. Since we use gnutls for crypto and build libqpdf on
the fly for Linux wheels, might as well do the same for macOS
to address this.

So now we build and link against our own libqpdf, which in turn is
linked against gnutls, which does not seem to have the same issues.
All of our Linux and macOS builds are doing the same thing now,
rather than being split on crypto provider.

## macOS generally

Here are the current constraints for building on macOS:

- General rule for macOS: build on the oldest available macOS runner.
- QPDF needs at least MACOSX_DEPLOYMENT_TARGET="11.0" since it uses
  C++20.
- Homebrew requires macOS 13+, so we can't support older versions.
- Homebrew creates binaries with MACOSX_DEPLOYMENT_TARGET="macos-x".
  Therefore, we should build on the minimum runner. For x86_64 that is
  macos-13.
- Setting SYSTEM_VERSION_COMPAT=0 is necessary for pip to understand
  MACOSX_DEPLOYMENT_TARGET="13.0" rather than macOS X 10.x syntax.
- GitHub's macos-14 runner is the first to be Apple Silicon. Since we
  use Homebrew, it can only build macos-14. We only support macos-14
  for arm64. Cirrus CI did support earlier macos. We no longer use
  Cirrus for Apple Silicon, just for Linux ARM64.
- Environment differences between GitHub runners and Cirrus CI runners
  mean we need to use sudo for Cirrus CI, hence maybe_sudo.

Taking a quick peek at numpy, it may be easier to build universal2 wheels
and use QEMU or Cirrus CI to confirm that they work. That would be another
big build overhaul.

Users who build from source have more options and can likely get
functional builds on anything newer than macOS 14.
