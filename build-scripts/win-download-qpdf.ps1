$version = $args[0]
$platform = $args[1]

if ($platform -eq "win_amd64") {
    $msvc = "msvc64"
} elseif ($platform -eq "win32") {
    $msvc = "msvc32"
} else {
    throw "I don't recognize platform=$platform"
}

if (($version -eq "10.3.2") -and ($msvc -eq "msvc32")) {
    $msvc = "msvc32-rebuild"
}


$qpdfurl = "https://github.com/qpdf/qpdf/releases/download/release-qpdf-$version/qpdf-$version-bin-$msvc.zip"
echo "Download $qpdfurl"

Invoke-WebRequest -Uri $qpdfurl -OutFile "qpdf-release.zip"
7z x "qpdf-release.zip" -oD:\
$qpdfdir = Get-ChildItem D:\qpdf-*
Move-Item -Path $qpdfdir -Destination D:\qpdf
cp D:\qpdf\bin\*.dll src\pikepdf
