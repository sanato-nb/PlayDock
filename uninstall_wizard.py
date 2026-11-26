"""Per-user uninstaller for PlayDock (Tk; frozen with PyInstaller).

A temporary copy executes the actual removal, since Windows cannot delete a
running Uninstall.exe. Never removes any downloaded archives, installed games,
configuration, title metadata, artwork cache, or saves.
"""
from __future__ import annotations

import base64
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import tkinter as tk
from tkinter import messagebox, ttk


# Source checkout: internal modules live under src/playdock; frozen builds use PyInstaller --paths.
import sys as _playdock_sys
from pathlib import Path as _playdock_Path
_playdock_source = _playdock_Path(__file__).resolve().parent / "src" / "playdock"
if _playdock_source.is_dir() and str(_playdock_source) not in _playdock_sys.path:
    _playdock_sys.path.insert(0, str(_playdock_source))

from install_management import (
    UNINSTALL_EXE, app_install_directory, uninstall_application,
    validate_install_directory,
)
from native_caption import darken_tk_root


class UninstallWizard(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("PlayDock 제거")
        self.geometry("620x380")
        self.minsize(580, 330)
        self.resizable(True, False)
        self.configure(bg="#eff3f7")
        icon = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent)) / "assets" / "playdock.ico"
        if icon.is_file():
            try:
                self.iconbitmap(str(icon))
            except tk.TclError:
                pass
        header = tk.Frame(self, bg="#16283c", height=88)
        header.pack(fill="x")
        header.pack_propagate(False)
        tk.Label(header, text="◈   PLAYDOCK", bg="#16283c", fg="white",
                 font=("Segoe UI", 18, "bold")).pack(anchor="w", padx=28, pady=(17, 2))
        tk.Label(header, text="프로그램 제거", bg="#16283c", fg="#bed6e9",
                 font=("Malgun Gothic", 10)).pack(anchor="w", padx=30)
        self.content = tk.Frame(self, bg="#eff3f7")
        self.content.pack(fill="both", expand=True, padx=30, pady=20)
        tk.Label(self.content, text="PlayDock를 제거하시겠습니까?", bg="#eff3f7",
                 fg="#182c41", font=("Malgun Gothic", 15, "bold")).pack(anchor="w", pady=(0, 17))
        message = (
            "게임 라이브러리, 게임 이름 관리자, 프로그램 바로가기만 제거합니다.\n"
            "게임 압축파일(ZIP·7z), 설치한 게임, 저장 파일, 모음집 및 이미지 캐시는 그대로 남습니다."
        )
        tk.Label(self.content, text=message, justify="left", wraplength=540,
                 bg="#eff3f7", fg="#2e4c64", font=("Malgun Gothic", 10)).pack(anchor="w")
        tk.Label(self.content, text="프로그램 위치: " + str(app_install_directory()),
                 wraplength=540, justify="left", bg="#eff3f7", fg="#637789",
                 font=("Malgun Gothic", 9)).pack(anchor="w", pady=(20, 0))
        bar = tk.Frame(self, bg="#e4eaf0", height=63)
        bar.pack(fill="x", side="bottom")
        bar.pack_propagate(False)
        self.exit_btn = ttk.Button(bar, text="취소", command=self.destroy)
        self.exit_btn.pack(side="right", padx=(0, 23), pady=14)
        self.remove_btn = ttk.Button(bar, text="프로그램 제거", command=self.remove)
        self.remove_btn.pack(side="right", padx=10, pady=14)
        self.after(0, lambda: darken_tk_root(self))

    def remove(self):
        if not messagebox.askyesno("제거 확인", "PlayDock 프로그램만 제거할까요?\n게임과 개인 데이터는 보존됩니다.", parent=self):
            return
        self.remove_btn.state(["disabled"])
        try:
            # Never remove files outside the known current-user install dir.
            validate_install_directory(app_install_directory())
            notes = uninstall_application()
        except (OSError, ValueError, RuntimeError) as exc:
            self.remove_btn.state(["!disabled"])
            messagebox.showerror("제거 실패", f"게임 라이브러리와 이름 관리자를 종료한 뒤 다시 시도해 주세요.\n\n{exc}", parent=self)
            return
        suffix = "\n".join(x for x in notes if x.startswith("다른 파일"))
        msg = "프로그램 제거가 완료됐습니다.\n\n게임 압축파일, 설치된 게임, 모음집 및 이미지 캐시는 보존했습니다."
        if suffix:
            msg += "\n\n" + suffix
        messagebox.showinfo("제거 완료", msg, parent=self)
        self.destroy()


def _cleanup_temp_copy() -> None:
    """Best-effort cleanup after the staged EXE exits; no user data paths."""
    if not getattr(sys, "frozen", False):
        return
    executable = Path(sys.executable)
    if not executable.parent.name.startswith("PlayDock-Uninstall-"):
        return
    tempdir = executable.parent
    script = (
        "for ($n=0; $n -lt 25; $n++) { Start-Sleep -Milliseconds 350; "
        f"try {{ Remove-Item -LiteralPath '{str(executable).replace(chr(39), chr(39)*2)}' -Force -ErrorAction Stop; break }} catch {{ }} }}; "
        f"Remove-Item -LiteralPath '{str(tempdir).replace(chr(39), chr(39)*2)}' -Force -ErrorAction SilentlyContinue"
    )
    encoded = base64.b64encode(script.encode("utf-16-le")).decode("ascii")
    try:
        subprocess.Popen(["powershell.exe", "-NoProfile", "-NonInteractive", "-WindowStyle", "Hidden",
                          "-EncodedCommand", encoded],
                         stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                         creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    except OSError:
        pass  # An orphaned copy in TEMP is harmless; game data remains safe.


def main() -> int:
    if "--self-test" in sys.argv:
        # No GUI or deletion; sanity-check the packaged EXE.
        assert UNINSTALL_EXE == "PlayDock_Uninstall.exe"
        return 0
    if sys.platform != "win32":
        print("Windows 전용 제거 프로그램입니다.")
        return 1
    if getattr(sys, "frozen", False) and "--worker" not in sys.argv:
        # Stage OUTSIDE the application folder so its installed Uninstall.exe
        # can be removed in the worker process, without a reboot.
        tempdir = Path(tempfile.mkdtemp(prefix="PlayDock-Uninstall-"))
        dest = tempdir / UNINSTALL_EXE
        try:
            shutil.copy2(Path(sys.executable), dest)
            subprocess.Popen([str(dest), "--worker"], cwd=str(tempdir),
                             creationflags=getattr(subprocess, "DETACHED_PROCESS", 0))
            return 0
        except OSError as exc:
            print(f"제거 프로그램 시작 실패: {exc}")
            return 1
    if getattr(sys, "frozen", False) and "--worker" in sys.argv:
        # Reject the worker switch when running from the protected install dir.
        if Path(sys.executable).parent.name.startswith("PlayDock-Uninstall-") is False:
            return 1
    UninstallWizard().mainloop()
    _cleanup_temp_copy()
    return 0


if __name__ == "__main__":
    sys.exit(main())
