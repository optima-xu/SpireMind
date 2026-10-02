@echo off
setlocal
if not exist "%~dp0.venv\Scripts\python.exe" (
    echo Run powershell -ExecutionPolicy Bypass -File scripts\setup.ps1 first.
    exit /b 1
)
pushd "%~dp0"
"%~dp0.venv\Scripts\python.exe" -m spiremind %*
set "spiremind_exit=%ERRORLEVEL%"
popd
exit /b %spiremind_exit%
