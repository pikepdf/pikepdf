# SPDX-FileCopyrightText: 2022 James R. Barlow
# SPDX-License-Identifier: MPL-2.0

$version = $args[0]
$platform = $args[1]

if ($platform -eq "win_amd64") {
    $msvc = "msvc64"
} else {
    throw "I don't recognize platform=$platform"
}

$qpdfurl = "https://github.com/qpdf/qpdf/releases/download/v$version/qpdf-$version-$msvc.zip"
echo "Download $qpdfurl"

Invoke-WebRequest -Uri $qpdfurl -OutFile "qpdf-release.zip"
7z x "qpdf-release.zip" -oD:\
$qpdfdir = Get-ChildItem D:\qpdf-*
Move-Item -Path $qpdfdir -Destination D:\qpdf

# Copy only qpdf's own library (and any genuine third-party deps it ships),
# but NOT the MSVC C++ runtime redistributable (msvcp140*, vcruntime140*,
# concrt140*). qpdf's msvc64 release bundles those runtime DLLs alongside
# qpdf30.dll; shipping them inside the package directory makes a fixed-version
# copy of the runtime shadow/collide with the system runtime (and other wheels'
# copies), which corrupts CPython's per-thread state ("the GIL is released /
# thread state is NULL"). The runtime must come from the system VC++
# Redistributable (which CPython and qpdf's msvc build already require), and
# delvewheel vendors any non-system deps with name mangling. See issue #718.
Get-ChildItem D:\qpdf\bin\*.dll |
    Where-Object { $_.Name -notmatch '^(msvcp140|vcruntime140|concrt140)' } |
    Copy-Item -Destination src\pikepdf
