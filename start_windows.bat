@echo off
setlocal EnableExtensions DisableDelayedExpansion
title PlayDock - Launcher
pushd "%~dp0"
if errorlevel 1 goto ERROR_FOLDER

set "VENV_PY=%CD%\.venv\Scripts\python.exe"
echo.
echo ===============================================
echo   PlayDock - Windows Startup
echo ===============================================
echo.

if exist "%VENV_PY%" goto CHECK_PYTHON

echo [1/3] Creating Python virtual environment...
where py >nul 2>nul
if errorlevel 1 goto TRY_PYTHON
py -3 -m venv ".venv"
if exist "%VENV_PY%" goto CHECK_PYTHON

:TRY_PYTHON
where python >nul 2>nul
if errorlevel 1 goto ERROR_NO_PYTHON
python -m venv ".venv"
if not exist "%VENV_PY%" goto ERROR_NO_PYTHON

:CHECK_PYTHON
"%VENV_PY%" -c "import sys; sys.exit(0 if sys.version_info >= (3,10) else 1)"
if errorlevel 1 goto ERROR_VERSION

if exist ".venv\deps_ready.txt" goto LAUNCH

echo [2/3] Installing required packages...
"%VENV_PY%" -m pip install -r "requirements.txt"
if errorlevel 1 goto ERROR_PIP
> ".venv\deps_ready.txt" echo Installed

:LAUNCH
echo [3/3] Starting PlayDock...
"%VENV_PY%" "app.py"
if errorlevel 1 goto ERROR_APP
popd
exit /b 0

:ERROR_FOLDER
echo ERROR: Cannot enter the application folder.
goto ERROR_END

:ERROR_NO_PYTHON
echo ERROR: Python was not found or the virtual environment could not be created.
echo Install Python 3.10 or newer and enable the Python launcher or PATH.
goto ERROR_END

:ERROR_VERSION
echo ERROR: Python 3.10 or newer is required.
goto ERROR_END

:ERROR_PIP
echo ERROR: Package installation failed.
echo Check your internet connection and Python installation.
goto ERROR_END

:ERROR_APP
echo ERROR: The app stopped with an error.
echo Copy the error text above if you need help.
goto ERROR_END

:ERROR_END
echo.
echo Please check README_KO.md for details.
pause
popd
exit /b 1
