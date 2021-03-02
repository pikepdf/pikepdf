#!/bin/bash
set -ex

mkdir zlib && wget -q $ZLIB_RELEASE -O - | tar xz -C zlib --strip-components=1 &
mkdir jpeg && wget -q $JPEG_RELEASE -O - | tar xz -C jpeg --strip-components=1 &
wait
