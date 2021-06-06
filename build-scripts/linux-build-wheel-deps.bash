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
    ./configure --disable-oss-fuzz && make -j install
    find /usr/local/lib -name 'libqpdf.so*' -type f -exec strip --strip-debug {} \+
    popd
fi

# For PyPy
yum install -y libxml2-devel libxslt-devel