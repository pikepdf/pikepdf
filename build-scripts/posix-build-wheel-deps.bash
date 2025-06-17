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
    if [ "$os" == "Darwin" ]; then
        cmake -S . -B build \
            -DCMAKE_BUILD_TYPE=Release \
            -DBUILD_STATIC_LIBS=OFF \
            -DREQUIRE_CRYPTO_GNUTLS=1 \
            -DUSE_IMPLICIT_CRYPTO=OFF
    else
        cmake -S . -B build \
            -DCMAKE_BUILD_TYPE=Release \
            -DBUILD_STATIC_LIBS=OFF
    fi
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

