"""Windows folder chooser for the console scanner (UI only, never scans files).

Requires no third-party packages or bundled Tkinter. PowerShell opens the native
FolderBrowserDialog; the resulting path goes through the scanner's Y/N guard.
"""
from __future__ import annotations

import base64
import subprocess
import sys


def pick_windows_folder() -> str | None:
    """Return a selected directory, or None when the dialog is cancelled."""
    if sys.platform != "win32":
        raise RuntimeError("폴더 선택창은 Windows에서만 사용 가능합니다. 경로를 직접 입력하세요.")

    # EncodedCommand avoids shell quoting issues and handles Korean folder names.
    command = r"""
Add-Type -AssemblyName System.Windows.Forms
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
$chooser = New-Object System.Windows.Forms.FolderBrowserDialog
$chooser.Description = 'Select folder containing ZIP, 7z or RAR games'
$chooser.ShowNewFolderButton = $false
try {
    if ($chooser.ShowDialog() -eq [System.Windows.Forms.DialogResult]::OK) {
        [Console]::Out.WriteLine($chooser.SelectedPath)
    }
} finally {
    $chooser.Dispose()
}
"""
    encoded = base64.b64encode(command.encode("utf-16le")).decode("ascii")
    try:
        process = subprocess.run(
            ["powershell.exe", "-NoLogo", "-NoProfile", "-STA",
             "-EncodedCommand", encoded],
            text=True, encoding="utf-8", errors="replace",
            capture_output=True, check=False,
        )
    except OSError as exc:
        raise RuntimeError("Windows 폴더 선택창을 실행할 수 없습니다.") from exc
    if process.returncode != 0:
        raise RuntimeError("폴더 선택창에 오류가 발생했습니다. 경로를 직접 입력해 주세요.")
    return process.stdout.strip() or None
