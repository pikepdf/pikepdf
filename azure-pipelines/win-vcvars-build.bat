@echo on
if %1 == 64 (
    call "%VS140COMNTOOLS%\..\..\VC\bin\amd64\vcvars64.bat"
) else (
    call "%VS140COMNTOOLS%\..\..\VC\bin\vcvars32.bat"
)

bash win-build.bash
