@echo off
setlocal EnableExtensions DisableDelayedExpansion
pushd "%~dp0.."
if errorlevel 1 goto FAILED
rem Single canonical builder for PlayDock.exe, PlayDock_Setup.exe, PlayDock_Uninstall.exe.
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0Build-Windows-Release.ps1" -NoLaunch
if errorlevel 1 goto FAILED
echo.
echo SUCCESS: dist\PlayDock_Setup.exe
pause
popd
exit /b 0
:FAILED
echo Build failed. Review the log above.
pause
popd
exit /b 1
