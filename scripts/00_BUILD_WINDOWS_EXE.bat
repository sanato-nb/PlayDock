@echo off
setlocal EnableExtensions DisableDelayedExpansion
pushd "%~dp0.."
if errorlevel 1 goto FAIL
title PlayDock - Clean Public Release Builder
echo.
echo ==========================================================
echo  PlayDock - Build EXE and clean public distribution
echo ==========================================================
echo  The installed PlayDock folder is NEVER used for packaging.
echo  Build: PlayDock.exe and PlayDock_TitleEditor.exe
echo  Bundle: PlayDock_Setup.exe and PlayDock_Uninstall.exe
echo.
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0Build-Windows-Release.ps1" -NoLaunch
if errorlevel 1 goto FAIL
if not exist ".venv\Scripts\python.exe" goto FAIL
".venv\Scripts\python.exe" "%~dp0make_public_release.py" --dist "%CD%\dist" --out "%CD%\public_release" --manual "%CD%\docs\PlayDock_UserManual_KO_v0.7.7.pdf" --source "%CD%"
if errorlevel 1 goto FAIL
if not exist "public_release\PlayDock_Public_v0.8.3.zip" goto FAIL
if not exist "public_release\PlayDock_Setup_v0.8.3.exe" goto FAIL
echo.
echo SUCCESS! Distribution files are in public_release.
echo DO NOT ZIP your installed PlayDock folder.
explorer.exe "%CD%\public_release"
popd
pause
exit /b 0
:FAIL
echo.
echo FAILED. Do not publish anything until the errors are fixed.
popd
pause
exit /b 1
