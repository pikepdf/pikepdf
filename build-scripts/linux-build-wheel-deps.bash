#!/bin/bash
# SPDX-FileCopyrightText: 2022 James R. Barlow
# SPDX-License-Identifier: MPL-2.0

set -ex

if [ "$(uname -m)" == "aarch64" ]; then
    MAX_JOBS=3
else
    MAX_JOBS=
fi

if [ ! -f /usr/local/lib/libz.a ]; then
    pushd zlib
    ./configure
    make -j $MAX_JOBS install
    popd
fi

if [ ! -f  /usr/local/lib/libjpeg.a ]; then
    pushd jpeg
    ./configure
    make -j $MAX_JOBS install
    popd
fi

if [ ! -f /usr/local/lib/libqpdf.a ]; then
    pushd qpdf
    cmake -S . -B build -DCMAKE_BUILD_TYPE=Release -DBUILD_STATIC_LIBS=OFF
    cmake --build build --parallel $MAX_JOBS --target libqpdf
    cmake --install build --component lib
    cmake --install build --component dev
    popd
fi

ldconfig