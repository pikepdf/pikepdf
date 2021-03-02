#!/bin/bash
set -ex

pushd qpdf
./configure --disable-oss-fuzz && make -j && sudo make install
popd
