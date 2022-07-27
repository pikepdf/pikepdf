#!/bin/bash
# SPDX-FileCopyrightText: 2022 James R. Barlow
# SPDX-License-Identifier: MPL-2.0

set -ex

mkdir zlib && wget -q $ZLIB_RELEASE -O - | tar xz -C zlib --strip-components=1 &
mkdir jpeg && wget -q $JPEG_RELEASE -O - | tar xz -C jpeg --strip-components=1 &
wait
