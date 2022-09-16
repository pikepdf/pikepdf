#!/bin/bash
# SPDX-FileCopyrightText: 2022 James R. Barlow
# SPDX-License-Identifier: MPL-2.0

set -ex

pushd qpdf
cmake -S . -B build -DCMAKE_BUILD_TYPE=RelWithDebInfo -DREQUIRE_CRYPTO_OPENSSL=1 -DBUILD_STATIC_LIBS=OFF
cmake --build build --parallel $(nproc) --target libqpdf
sudo cmake --install build --component lib
sudo cmake --install build --component dev
popd

sudo ldconfig