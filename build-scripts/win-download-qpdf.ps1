# SPDX-FileCopyrightText: 2022 James R. Barlow
# SPDX-License-Identifier: MPL-2.0

$version = $args[0]
$platform = $args[1]

if ($platform -eq "win_amd64") {
    $msvc = "msvc64"
} elseif ($platform -eq "win32") {
    $msvc = "msvc32"
} else {
    throw "I don't recognize platform=$platform"
}

$qpdfurl = "https://github.com/qpdf/qpdf/releases/download/v$version/qpdf-$version-$msvc.zip"
echo "Download $qpdfurl"

Invoke-WebRequest -Uri $qpdfurl -OutFile "qpdf-release.zip"
7z x "qpdf-release.zip" -oD:\
$qpdfdir = Get-ChildItem D:\qpdf-*
Move-Item -Path $qpdfdir -Destination D:\qpdf
cp D:\qpdf\bin\*.dll src\pikepdf
