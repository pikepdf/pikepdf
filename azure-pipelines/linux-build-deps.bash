#!/bin/bash
set -ex

if test "$(arch)" == "x86_64"; then
    apt-get -y install libxml2-dev libxslt-dev
fi

pushd $1/zlib
./configure &&
make -j install &&
popd

pushd $1/jpeg
./configure &&
make -j install &&
popd

pushd $1/qpdf
./autogen.sh &&
./configure &&
make -j install &&
popd
