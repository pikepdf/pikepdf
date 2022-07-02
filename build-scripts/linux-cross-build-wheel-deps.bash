#!/bin/bash
set -ex

XCCDEPS=$PWD/xcc
XCCDEPSARCH=$PWD/xcc

mkdir -p $XCCDEPS $XCCDEPSARCH

pushd zlib
./configure --prefix $XCCDEPS --eprefix $XCCDEPSARCH 
make -j install
popd

pushd jpeg
./configure --prefix $XCCDEPS --exec-prefix $XCCDEPSARCH --host aarch64-unknown-linux-gnueabi
make -j install
popd

pushd qpdf
PKG_CONFIG_PATH=$XCCDEPSARCH/lib/pkgconfig ./configure --prefix $XCCDEPS --exec-prefix $XCCDEPSARCH --disable-oss-fuzz
make -j install-libs
popd
