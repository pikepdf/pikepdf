call "%VS140COMNTOOLS%\..\..\VC\vcvarsall.bat" x64
set DISTUTILS_USE_SDK=1
set MSSdk=1
"%PYTHON%" setup.py install
if errorlevel 1 exit 1
