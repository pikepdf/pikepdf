#!/bin/bash
# SPDX-FileCopyrightText: 2022 James R. Barlow
# SPDX-License-Identifier: MPL-2.0

set -ex

# If we want to test master, use:
#QPDF_RELEASE=https://github.com/qpdf/qpdf/archive/refs/heads/main.tar.gz

# Normally:
QPDF_RELEASE=${QPDF_PATTERN//VERSION/$1}

mkdir qpdf && wget -q $QPDF_RELEASE -O - | tar xz -C qpdf --strip-components=1
