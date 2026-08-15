#!/bin/bash
# SPDX-FileCopyrightText: 2022 James R. Barlow
# SPDX-License-Identifier: MPL-2.0

set -euxo pipefail

os=$(uname)
arch=$(uname -m)
max_jobs=

if [ "$arch" == "aarch64" -o "$arch" == "arm64" ]; then
    max_jobs=3
fi

maybe_sudo () {
    if [ "$os" == "Darwin" ]; then
        sudo -E "$@"
    else
        "$@"
    fi
}

echo "Building dependencies for $os $arch MACOSX_DEPLOYMENT_TARGET=${MACOSX_DEPLOYMENT_TARGET:-}"

if [ grep -q almalinux /etc/os-release ]; then
    libdir=/usr/local/lib64
else
    libdir=/usr/local/lib
fi

if [ ! -f $libdir/libqpdf.so -a ! -f $libdir/libqpdf.dylib ]; then
    pushd qpdf
    # Select qpdf's native crypto provider explicitly on every platform.
    #
    # macOS previously required gnutls. That dates to issue #520, where legacy
    # encrypted PDFs failed to open because Homebrew's openssl had retired its
    # legacy provider (RC4/MD5). gnutls was chosen as the escape hatch, on the
    # understanding that it matched what Linux did. It did not: the manylinux
    # and musllinux images ship neither gnutls-devel nor openssl-devel, so
    # USE_IMPLICIT_CRYPTO quietly fell back to native there. Linux wheels have
    # therefore been shipping native crypto ever since, opening legacy files
    # without complaint.
    #
    # Native crypto implements MD5, RC4, SHA2 and AES itself, so it has no
    # external policy that can disable the weak algorithms older PDFs need --
    # it sidesteps #520 by construction rather than by picking a library that
    # has not yet deprecated them. Using it on macOS drops nine vendored
    # dylibs (the gnutls/nettle/gmp stack) and their LGPL obligations from the
    # wheel.
    #
    # Being explicit also keeps third-party-licenses/ honest: with implicit
    # crypto, a build image that happened to gain gnutls or openssl headers
    # would silently add a dependency the license manifest does not describe.
    cmake -S . -B build \
        -DCMAKE_BUILD_TYPE=Release \
        -DBUILD_STATIC_LIBS=OFF \
        -DREQUIRE_CRYPTO_NATIVE=1 \
        -DUSE_IMPLICIT_CRYPTO=OFF
    cmake --build build --parallel $max_jobs --target libqpdf
    maybe_sudo cmake --install build --component lib
    maybe_sudo cmake --install build --component dev
    popd
fi

if [ -f /etc/alpine-release ]; then
    ldconfig /
elif [ "$os" == "Linux" ]; then
    ldconfig
fi

