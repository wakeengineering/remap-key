@echo off
setlocal enableextensions

set "SCRIPT_DIR=%~dp0"
set "SCRIPT_FILE=%SCRIPT_DIR%remap-key.py"
set "LOG_FILE=%SCRIPT_DIR%remap-key.task.log"

call :find_python
if not defined PYTHON_EXE (
  echo [%DATE% %TIME%] Could not find a virtual-environment python.exe.>>"%LOG_FILE%"
  exit /b 1
)

if not exist "%SCRIPT_FILE%" (
  echo [%DATE% %TIME%] Missing script: %SCRIPT_FILE%>>"%LOG_FILE%"
  exit /b 1
)

cd /d "%SCRIPT_DIR%"
"%PYTHON_EXE%" "%SCRIPT_FILE%" >> "%LOG_FILE%" 2>&1
exit /b %errorlevel%

:find_python
for %%P in (
  "%SCRIPT_DIR%python.venv-remap\Scripts\python.exe"
  "%SCRIPT_DIR%.venv-remap\Scripts\python.exe"
  "%SCRIPT_DIR%..\python.venv-remap\Scripts\python.exe"
  "%SCRIPT_DIR%..\.venv-remap\Scripts\python.exe"
) do (
  if exist "%%~P" (
    set "PYTHON_EXE=%%~P"
    goto :eof
  )
)
goto :eof
