#!/bin/bash
# SPDX-FileCopyrightText: 2022 James R. Barlow
# SPDX-License-Identifier: MPL-2.0

set -euxo pipefail

QPDF_RELEASE=${QPDF_PATTERN//VERSION/$1}

mkdir qpdf

# Stage the tarball to a temp file with retries before extracting. Piping wget
# straight into tar makes a truncated/interrupted transfer (e.g. a flaky GitHub
# Releases CDN, which has bitten us with "gzip: stdin: unexpected end of file")
# unrecoverable; downloading to a file lets wget retry and ensures we only feed
# tar a complete archive.
tarball=$(mktemp)
trap 'rm -f "$tarball"' EXIT

wget -q \
  --tries=5 \
  --retry-connrefused \
  --timeout=30 \
  --waitretry=5 \
  -O "$tarball" \
  "$QPDF_RELEASE"

tar xz -C qpdf --strip-components=1 -f "$tarball"
