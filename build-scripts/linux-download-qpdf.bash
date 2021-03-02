#!/bin/bash
set -ex

QPDF_RELEASE=${QPDF_PATTERN//VERSION/$1}

mkdir qpdf && wget -q $QPDF_RELEASE -O - | tar xz -C qpdf --strip-components=1
