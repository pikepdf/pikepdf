#!/bin/bash
# SPDX-FileCopyrightText: 2022 James R. Barlow
# SPDX-License-Identifier: MPL-2.0

set -euxo pipefail

QPDF_RELEASE=${QPDF_PATTERN//VERSION/$1}

mkdir qpdf

# Stage the tarball to a temp file before extracting. Piping wget straight into
# tar makes a truncated/interrupted transfer (e.g. a flaky GitHub Releases CDN,
# which has bitten us with "gzip: stdin: unexpected end of file") unrecoverable;
# downloading to a file lets us retry and ensures we only feed tar a complete
# archive.
tarball=$(mktemp)
trap 'rm -f "$tarball"' EXIT

# Retry the whole download in a loop with backoff. wget's own --tries only
# retries connection-level failures, and we can't use --retry-on-http-error
# because the manylinux image ships wget 1.19, which predates that flag. A shell
# loop rides out *any* transient GitHub Releases failure (HTTP 5xx, resets,
# truncation) regardless of wget version. -O truncates the temp file each try.
attempt=0
max_attempts=6
until wget -q --tries=3 --retry-connrefused --timeout=30 -O "$tarball" "$QPDF_RELEASE"; do
  attempt=$((attempt + 1))
  if [ "$attempt" -ge "$max_attempts" ]; then
    echo "qpdf download failed after $max_attempts attempts" >&2
    exit 1
  fi
  echo "qpdf download attempt $attempt failed; retrying in $((attempt * 10))s..." >&2
  sleep $((attempt * 10))
done

tar xz -C qpdf --strip-components=1 -f "$tarball"
