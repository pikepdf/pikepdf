# SPDX-FileCopyrightText: 2022 James R. Barlow
# SPDX-License-Identifier: MPL-2.0

$ErrorActionPreference = "Stop"

$version = $args[0]
$platform = $args[1]

if ($platform -eq "win_amd64") {
    $msvc = "msvc64"
} elseif ($platform -eq "win_arm64") {
    $msvc = "msvc-arm64"
} else {
    throw "I don't recognize platform=$platform"
}

$stage = if ($env:RUNNER_TEMP) { $env:RUNNER_TEMP } else { $env:TEMP }
$qpdfdir = Join-Path $stage "qpdf"
if (Test-Path $qpdfdir) {
    Remove-Item -Recurse -Force $qpdfdir
}

$qpdfurl = "https://github.com/qpdf/qpdf/releases/download/v$version/qpdf-$version-$msvc.zip"
echo "Download $qpdfurl"

Invoke-WebRequest -Uri $qpdfurl -OutFile "qpdf-release.zip"
7z x "qpdf-release.zip" "-o$stage"
$extracted = Get-ChildItem -Path $stage -Directory -Filter "qpdf-*" | Select-Object -First 1
if (-not $extracted) {
    throw "qpdf-release.zip did not contain a qpdf-* directory"
}
Move-Item -Path $extracted.FullName -Destination $qpdfdir

echo "QPDF_DIR=$qpdfdir"
if ($env:GITHUB_ENV) {
    "QPDF_DIR=$qpdfdir" | Out-File -FilePath $env:GITHUB_ENV -Append -Encoding utf8
}

# Copy only qpdf's own library (and any genuine third-party deps it ships),
# but NOT the MSVC C++ runtime redistributable (msvcp140*, vcruntime140*,
# concrt140*). qpdf's msvc64 release bundles those runtime DLLs alongside
# qpdf30.dll; copying them un-mangled into the package directory makes a
# fixed-version copy of the runtime shadow/collide with the system runtime
# (and other wheels' copies), which corrupts CPython's per-thread state
# ("the GIL is released / thread state is NULL"). delvewheel later discovers
# qpdf30.dll's runtime dependency via --add-path and vendors a name-mangled
# msvcp140 into pikepdf.libs/ (and uses CPython's own vcruntime140), so the
# wheel stays self-contained without an un-mangled runtime in the package
# directory. See issue #718.
Get-ChildItem (Join-Path $qpdfdir "bin\*.dll") |
    Where-Object { $_.Name -notmatch '^(msvcp140|vcruntime140|concrt140)' } |
    Copy-Item -Destination src\pikepdf
