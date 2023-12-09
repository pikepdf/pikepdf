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

if [ "$os" == "Darwin" ]; then
    # Setting this here only affects the QPDF build, not pikepdf.
    # pybind11 will set --macosx-version-min automatically based on
    # the requested cxx_std unless MACOSX_DEPLOYMENT_TARGET is set.
    export MACOSX_DEPLOYMENT_TARGET="11.0"
fi

maybe_sudo () {
    if [ "$os" == "Darwin" -a "${CIRRUS_CI:-}" == "true" ]; then
        sudo -E "$@"
    else
        "$@"
    fi
}

if [ ! -f /usr/local/lib/libqpdf.so -a ! -f /usr/local/lib/libqpdf.dylib ]; then
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

