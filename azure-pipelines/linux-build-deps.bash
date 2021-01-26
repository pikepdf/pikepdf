#!/bin/bash
set -ex

if test "$(arch)" == "x86_64"; then
    yum install -y libxml2-devel libxslt-devel
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
