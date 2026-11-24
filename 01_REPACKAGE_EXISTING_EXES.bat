@echo off
setlocal EnableExtensions DisableDelayedExpansion
pushd "%~dp0"
if errorlevel 1 goto FAIL
title PlayDock - Repackage Existing Windows EXEs
echo.
echo ==========================================================
echo  PlayDock - Package previously built EXEs (no rebuild)
echo ==========================================================
if not exist ".venv\Scripts\python.exe" goto NO_PY
".venv\Scripts\python.exe" "%~dp0make_public_release.py" --dist "%~dp0dist" --out "%~dp0public_release" --manual "%~dp0docs\PlayDock_UserManual_KO_v0.7.7.pdf" --source "%~dp0"
if errorlevel 1 goto FAIL
if not exist "public_release\PlayDock_Public_v0.8.1.zip" goto FAIL
if not exist "public_release\PlayDock_Setup_v0.8.1.exe" goto FAIL
echo.
echo SUCCESS! Only share files from public_release.
explorer.exe "%~dp0public_release"
popd
pause
exit /b 0
:NO_PY
echo ERROR: Missing .venv\Scripts\python.exe. Run 00_BUILD_WINDOWS_EXE.bat first.
goto FAIL
:FAIL
echo.
echo FAILED. Do not publish unverified files.
popd
pause
exit /b 1
