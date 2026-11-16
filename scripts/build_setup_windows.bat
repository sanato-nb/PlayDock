@echo off
setlocal EnableExtensions DisableDelayedExpansion
pushd "%~dp0.."
if errorlevel 1 goto FAILED

echo =============================================================
echo    PlayDock v0.8.3 - Windows Setup.exe builder
echo =============================================================
echo.
where py >nul 2>nul
if not errorlevel 1 goto USE_PY
where python >nul 2>nul
if errorlevel 1 goto NO_PY
set "SYSTEM_PY=python"
goto MAKE_VENV
:USE_PY
set "SYSTEM_PY=py -3"
:MAKE_VENV
if not exist ".venv\Scripts\python.exe" (
  echo [1/8] Creating Python environment...
  %SYSTEM_PY% -m venv ".venv"
  if errorlevel 1 goto FAILED
)
set "PY=.venv\Scripts\python.exe"
echo [2/8] Installing packaging and test dependencies...
"%PY%" -m pip install --upgrade pip
if errorlevel 1 goto FAILED
"%PY%" -m pip install -r requirements.txt pyinstaller pytest
if errorlevel 1 goto FAILED

echo [3/8] Running unit tests (must pass before packaging)...
"%PY%" -m pytest -q tests
if errorlevel 1 goto FAILED

echo [4/8] Building application EXE...
"%PY%" -m PyInstaller --noconfirm --clean --paths "src\playdock" --onefile --windowed --name "PlayDock" --icon "assets\playdock.ico" --collect-all keyring --collect-all pyzipper --collect-all send2trash --hidden-import game_codes --add-data "assets\playdock.ico;assets" app.py
if errorlevel 1 goto FAILED

echo [5/8] Building standalone title editor EXE...
"%PY%" -m PyInstaller --noconfirm --clean --paths "src\playdock" --onefile --windowed --name "PlayDock_TitleEditor" --icon "assets\playdock.ico" --collect-all keyring --collect-all ddgs --hidden-import game_codes --hidden-import bulk_title_edit --add-data "assets\playdock.ico;assets" title_editor.py
if errorlevel 1 goto FAILED

echo [6/8] Building dedicated uninstaller EXE...
"%PY%" -m PyInstaller --noconfirm --clean --paths "src\playdock" --onefile --windowed --name "PlayDock_Uninstall" --icon "assets\playdock.ico" --add-data "assets\playdock.ico;assets" uninstall_wizard.py
if errorlevel 1 goto FAILED
"dist\PlayDock_Uninstall.exe" --self-test
if errorlevel 1 goto FAILED

echo [7/8] Bundling Windows installer EXE...
"%PY%" -m PyInstaller --noconfirm --clean --paths "src\playdock" --onefile --windowed --name "PlayDock_Setup" --icon "assets\playdock.ico" --add-data "assets\playdock.ico;assets" --add-binary "dist\PlayDock.exe;payload" --add-binary "dist\PlayDock_TitleEditor.exe;payload" --add-binary "dist\PlayDock_Uninstall.exe;payload" setup_wizard.py
if errorlevel 1 goto FAILED

echo [8/8] Verifying all bundled EXE files...
"dist\PlayDock_Setup.exe" --self-test
if errorlevel 1 goto FAILED
echo.
echo SUCCESS: dist\PlayDock_Setup.exe
echo Application EXEs: dist\PlayDock.exe, dist\PlayDock_TitleEditor.exe, dist\PlayDock_Uninstall.exe
echo This Setup.exe can be copied and installed on Windows PCs without Python.
pause
popd
exit /b 0
:NO_PY
echo ERROR: Python 3.10+ is required on the BUILD PC.
echo Download Python from python.org, then rerun.
:FAILED
echo Build failed. Review the log above.
pause
popd
exit /b 1
