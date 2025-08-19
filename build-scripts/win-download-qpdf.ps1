# SPDX-FileCopyrightText: 2022 James R. Barlow
# SPDX-License-Identifier: MPL-2.0

$version = $args[0]
$platform = $args[1]

if ($platform -eq "win_amd64" -or $platform -eq "win_arm64") {
    $msvc = "msvc64"
} else {
    throw "I don't recognize platform=$platform"
}

$qpdfurl = "https://github.com/qpdf/qpdf/releases/download/v$version/qpdf-$version-$msvc.zip"
echo "Download $qpdfurl"

Set-PSDebug -Trace 2

Invoke-WebRequest -Uri $qpdfurl -OutFile "qpdf-release.zip"
7z x "qpdf-release.zip" -ounzipped
tree
$qpdfdir = Get-ChildItem .\unzipped\qpdf-*
Move-Item -Path $qpdfdir -Destination .\qpdf
tree qpdf
cp .\qpdf\bin\*.dll src\pikepdf
