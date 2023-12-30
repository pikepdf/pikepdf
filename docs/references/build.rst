Build process notes
===================

This section contains notes on complexities in the GitHub Actions
build-deploy workflow.

macOS crypto provider
---------------------

Users reported trouble with open legacy encrypted files on macOS
specifically, e.g. https://github.com/pikepdf/pikepdf/issues/520

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

Some ugly complications emerged:

1. QPDF now uses some C++17 features like std::get that are not
available on macOS 10.9, the default, which seems to support only a
subset of C++17. Because of that we need to explicitly set
MACOSX_DEPLOYMENT_TARGET="11.0"
when building QPDF.

2. x86_64. For reasons unclear, when MACOSX_DEPLOYMENT_TARGET="11.0" is set
and pikepdf builds, the generated wheel is built without issue,
but installing on a macos-12-x86_64 runner gives this error:

.. code-block::

    ERROR: pikepdf-8.11.0-cp38-cp38-macosx_11_0_x86_64.whl is not a supported wheel on this platform.

(Same for MACOSX_DEPLOYMENT_TARGET="12.0").

Thus, we have to pick a different value for this environment variable
for the pikepdf. Clearly something is wrong here, but this unintuitive
configuration is what works. When MACOSX_DEPLOYMENT_TARGET is not set
pybind11's Pybind11Extension class examines other settings and should
set -mmacosx-version-min=10.14 for when cxx_std=17.

Adding to confusion, the build logs from setuptools show that are
targeting 10.9, and the wheels are generated for 10.9.

There may be dragons here, still.

3. arm64. MACOSX_DEPLOYMENT_TARGET="11.0" is the minimum version for arm64.
We set this to ensure that pikepdf builds for this target, and then
because of the aforementioned Pybind11Extension check, pikepdf's
deployment target would be set to 10.14. To override this, we set
MACOSX_DEPLOYMENT_TARGET="11.0" for each builder, as well as when
building libqpdf.

4. Environment differences between GitHub runners and Cirrus CI runners
mean we need to use sudo for Cirrus CI, hence maybe_sudo.

Taking a quick peek at numpy, it may be easier to build universal2 wheels
and use QEMU or Cirrus CI to confirm that they work. That would be another
big build overhaul, so let's wait for GitHub Actions to release arm64
runners instead.