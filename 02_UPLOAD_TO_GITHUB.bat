@echo off
setlocal
pushd "%~dp0"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0UPLOAD_TO_GITHUB.ps1"
if errorlevel 1 (
  echo GitHub upload failed. Check messages above.
) else (
  echo GitHub upload complete.
)
popd
pause
