@echo on
if %1 == 32 (
    call "%VS140COMNTOOLS%\..\..\VC\bin\vcvars32.bat"
)

bash azure-pipelines/win-build.bash
