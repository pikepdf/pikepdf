#!/bin/bash
set -ex

if [ ! -f /usr/local/lib/libz.a ]; then
    pushd zlib
    ./configure && make -j install
    popd
fi

if [ ! -f  /usr/local/lib/libjpeg.a ]; then
    pushd jpeg
    ./configure && make -j install
    popd
fi

if [ ! -f /usr/local/lib/libqpdf.a ]; then
    pushd qpdf
    if [[ $(uname -p) == 'aarch64' ]]; then
        ./configure --disable-oss-fuzz && make install
    else
        ./configure --disable-oss-fuzz && make -j install
    fi
    find /usr/local/lib -name 'libqpdf.so*' -type f -exec strip --strip-debug {} \+
    popd
fi

ldconfig
