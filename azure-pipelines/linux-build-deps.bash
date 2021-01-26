#!/bin/bash
set -ex

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
