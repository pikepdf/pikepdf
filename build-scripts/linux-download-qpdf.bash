#!/bin/bash
# SPDX-FileCopyrightText: 2022 James R. Barlow
# SPDX-License-Identifier: MPL-2.0

set -ex

#QPDF_RELEASE=${QPDF_PATTERN//VERSION/$1}
QPDF_RELEASE=https://github.com/qpdf/qpdf/archive/refs/heads/main.tar.gz
mkdir qpdf && wget -q $QPDF_RELEASE -O - | tar xz -C qpdf --strip-components=1
