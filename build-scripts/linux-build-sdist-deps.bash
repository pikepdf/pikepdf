#!/bin/bash
# SPDX-FileCopyrightText: 2022 James R. Barlow
# SPDX-License-Identifier: MPL-2.0

set -ex

pushd qpdf
./configure --disable-oss-fuzz && make -j && sudo make install
popd

sudo ldconfig