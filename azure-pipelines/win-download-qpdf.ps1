Invoke-WebRequest -Uri $env:QPDF_WINDOWS -OutFile "qpdf-release.zip"
7z x "qpdf-release.zip" -oc:\
$qpdfdir = Get-ChildItem c:\qpdf-*
Move-Item -Path $qpdfdir -Destination c:\qpdf
cp c:\qpdf\bin\$env:QPDF_DLL src\pikepdf
