#!/bin/bash
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
    ./configure --disable-oss-fuzz 
    make -j $MAX_JOBS install-libs
    find /usr/local/lib -name 'libqpdf.so*' -type f -exec strip --strip-debug {} \+
    popd
fi

ldconfig