@echo off
setlocal
pushd "%~dp0"
if exist ".venv\Scripts\python.exe" (
    ".venv\Scripts\python.exe" title_editor.py
) else (
    where py >nul 2>nul
    if not errorlevel 1 (
        py -3 title_editor.py
    ) else (
        python title_editor.py
    )
)
if errorlevel 1 pause
popd
exit /b
