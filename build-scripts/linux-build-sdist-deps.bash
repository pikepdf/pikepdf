#!/bin/bash
# SPDX-FileCopyrightText: 2022 James R. Barlow
# SPDX-License-Identifier: MPL-2.0

set -ex

pushd qpdf
cmake -S . -B build -DCMAKE_BUILD_TYPE=RelWithDebInfo -DREQUIRE_CRYPTO_OPENSSL=1
cmake --build build --parallel $(nproc) -- -k
sudo cmake --install build
popd

sudo ldconfig