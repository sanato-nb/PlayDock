"""Windows one-file installer with three user-selected locations.

Program EXEs and local application data are colocated in a writable install
folder. Game archives and installed games remain in separate chosen folders.
"""
from __future__ import annotations

import base64
import json
import os
from pathlib import Path
import queue
import shutil
import subprocess
import sys
import tempfile
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from setup_paths import proposed_paths, normalize_paths, save_folder_settings, config_path
from native_caption import darken_tk_root
from install_management import (UNINSTALL_EXE, app_install_directory, register_uninstall_entry,
                                normalize_program_path, same_path, shortcut_points_to, LEGACY_BINARIES)
from local_storage import (legacy_data_dir, program_store, migrate_legacy_data,
                           write_install_marker, marker_is_valid, LEGACY_INSTALL_MARKER, LEGACY_MARKER_ID)

APP = "PlayDock"
EXE = "PlayDock.exe"
TITLE_EXE = "PlayDock_TitleEditor.exe"


def installed_executable(program: Path | None = None) -> Path:
    return (Path(program) if program is not None else app_install_directory()) / EXE


def payload_executable() -> Path:
    root = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
    options = [root / "payload" / EXE, root / EXE, root / "dist" / EXE]
    for path in options:
        if path.is_file():
            return path
    raise FileNotFoundError(
        "앱 실행 파일을 찾을 수 없습니다. 먼저 build_setup_windows.bat을 이용해 Setup.exe를 빌드하세요."
    )


def installed_title_editor(program: Path | None = None) -> Path:
    return installed_executable(program).with_name(TITLE_EXE)


def payload_title_editor() -> Path:
    root = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
    for path in (root / "payload" / TITLE_EXE, root / TITLE_EXE, root / "dist" / TITLE_EXE):
        if path.is_file():
            return path
    raise FileNotFoundError(
        "이름 관리자 실행 파일을 찾을 수 없습니다. 두 EXE를 포함해 Setup.exe를 다시 빌드하세요."
    )




def installed_uninstaller(program: Path | None = None) -> Path:
    return (Path(program) if program is not None else app_install_directory()) / UNINSTALL_EXE


def payload_uninstaller() -> Path:
    root = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
    for path in (root / "payload" / UNINSTALL_EXE, root / UNINSTALL_EXE, root / "dist" / UNINSTALL_EXE):
        if path.is_file():
            return path
    raise FileNotFoundError("제거 프로그램 EXE를 찾지 못했습니다. 새 릴리스 패키지를 다시 빌드하세요.")


def existing_or_default() -> tuple[str, str]:
    archive, game = proposed_paths()
    candidates = [program_store(app_install_directory()) / 'settings.json', config_path()]
    for settings in candidates:
        try:
            data = json.loads(settings.read_text(encoding='utf-8'))
            if isinstance(data, dict):
                archive = Path(data.get('archives') or archive)
                game = Path(data.get('library') or game)
                break
        except (OSError, ValueError, TypeError):
            continue
    return str(archive), str(game)


def desktop_directory() -> Path:
    """Use the user's Windows Desktop known-folder (including OneDrive redirects)."""
    if sys.platform == 'win32':
        try:
            import ctypes
            buf = ctypes.create_unicode_buffer(32768)
            if ctypes.windll.shell32.SHGetFolderPathW(None, 0x0010, None, 0, buf) == 0 and buf.value:
                return Path(buf.value)
        except (AttributeError, OSError, ValueError):
            pass
    return Path(os.getenv('USERPROFILE', str(Path.home()))) / 'Desktop'


def create_shortcut(target: Path, link: Path) -> None:
    """Create a real .lnk using the Windows Shell COM object, not a .url shortcut."""
    def ps_literal(value: str) -> str:
        return "'" + value.replace("'", "''") + "'"
    script = (
        "$ws = New-Object -ComObject WScript.Shell; "
        f"$s = $ws.CreateShortcut({ps_literal(str(link))}); "
        f"$s.TargetPath = {ps_literal(str(target))}; "
        f"$s.WorkingDirectory = {ps_literal(str(target.parent))}; "
        "$s.Description = 'PlayDock'; "
        "$s.Save()"
    )
    code = base64.b64encode(script.encode("utf-16-le")).decode("ascii")
    link.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(["powershell.exe", "-NoProfile", "-NonInteractive", "-EncodedCommand", code],
                   stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, timeout=35, check=True)


class SetupWizard(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("PlayDock 설치 마법사")
        icon_root = Path(getattr(sys, '_MEIPASS', Path(__file__).resolve().parent))
        icon = icon_root / 'assets' / 'playdock.ico'
        if icon.is_file():
            try:
                self.iconbitmap(str(icon))
            except tk.TclError:
                pass
        self.geometry("820x660")
        self.minsize(760, 620)
        self.configure(bg="#eff3f7")
        self.resizable(True, True)
        self.messages: queue.Queue[tuple[str, str]] = queue.Queue()
        self.archive_var, self.game_var = (tk.StringVar(value=x) for x in existing_or_default())
        self.program_var = tk.StringVar(value=str(app_install_directory()))
        self.page = 0
        self.installed = False
        self.desktop_shortcut = tk.BooleanVar(value=True)
        self.launch_after = tk.BooleanVar(value=True)
        self.shortcut_warning = ""
        self.style = ttk.Style(self)
        if "vista" in self.style.theme_names():
            self.style.theme_use("vista")
        self.style.configure("Wizard.Horizontal.TProgressbar", thickness=14)
        self.make_layout()
        self.protocol("WM_DELETE_WINDOW", self.close)
        self.after(120, self.poll)
        self.render()
        # Tk creates its decorated Windows HWND after idle/show.
        self.after(0, lambda: darken_tk_root(self))

    def make_layout(self):
        header = tk.Frame(self, bg="#16283c", height=95)
        header.pack(fill="x")
        header.pack_propagate(False)
        tk.Label(header, text="◈   PLAYDOCK", font=("Segoe UI", 19, "bold"),
                 fg="white", bg="#16283c").pack(anchor="w", padx=35, pady=(16, 0))
        tk.Label(header, text="Windows 게임 라이브러리 설치 마법사", font=("Malgun Gothic", 10),
                 fg="#afc7db", bg="#16283c").pack(anchor="w", padx=37, pady=(0, 5))
        # Pack the fixed footer first: with Tk's packer, placing an expanding
        # body first can push the Next/Install buttons offscreen on Windows.
        bottom = tk.Frame(self, bg="#e4eaf0", height=70)
        bottom.pack(fill="x", side="bottom")
        bottom.pack_propagate(False)
        self.cancel_btn = ttk.Button(bottom, text="취소", command=self.close)
        self.next_btn = ttk.Button(bottom, text="다음 >", command=self.advance)
        self.back_btn = ttk.Button(bottom, text="< 이전", command=self.back)
        self.cancel_btn.pack(side="right", padx=(0, 25), pady=18)
        self.next_btn.pack(side="right", padx=8, pady=18)
        self.back_btn.pack(side="right", padx=8, pady=18)
        self.body = tk.Frame(self, bg="#eff3f7")
        self.body.pack(fill="both", expand=True, padx=36, pady=25)

    def title_text(self, title, description):
        tk.Label(self.body, text=title, bg="#eff3f7", fg="#172a3b",
                 font=("Malgun Gothic", 16, "bold")).pack(anchor="w", pady=(0, 12))
        tk.Label(self.body, text=description, bg="#eff3f7", fg="#4d6071",
                 justify="left", font=("Malgun Gothic", 10), wraplength=640).pack(anchor="w", pady=(0, 20))

    def folder_entry(self, caption: str, var: tk.StringVar):
        tk.Label(self.body, text=caption, bg="#eff3f7", fg="#193650",
                 font=("Malgun Gothic", 11, "bold")).pack(anchor="w", pady=(6, 5))
        line = tk.Frame(self.body, bg="#eff3f7")
        line.pack(fill="x", pady=(0, 18))
        ttk.Entry(line, textvariable=var).pack(side="left", fill="x", expand=True, ipady=5)
        ttk.Button(line, text="찾아보기...", command=lambda v=var: self.choose(v)).pack(side="left", padx=(12, 0))

    def choose(self, var: tk.StringVar):
        directory = Path(var.get()).expanduser()
        while not directory.is_dir() and directory != directory.parent:
            directory = directory.parent
        choice = filedialog.askdirectory(parent=self, title="폴더 선택", initialdir=str(directory))
        if choice:
            var.set(choice)

    def render(self):
        for child in self.body.winfo_children():
            child.destroy()
        if self.page == 0:
            self.title_text("PlayDock 설치", "게임 압축파일과 설치된 게임을 스팀 스타일로 관리하는 프로그램입니다.")
            for txt in ("● ZIP / 7z 게임을 설치 버튼으로 압축 해제",
                        "● 설치된 게임의 EXE 실행과 이미지 캐시 관리",
                        "● 별도 게임 이름 관리 프로그램 함께 설치",
                        "● 프로그램 폴더 하나에 설정·모음집·캐시를 함께 저장",
                        "● 기존 게임이나 압축파일은 삭제·이동하지 않음"):
                tk.Label(self.body, text=txt, bg="#eff3f7", fg="#274861",
                         font=("Malgun Gothic", 11)).pack(anchor="w", pady=8)
            self.back_btn.state(["disabled"])
            self.next_btn.config(text="다음 >")
        elif self.page == 1:
            self.title_text("설치 위치 선택", "프로그램과 데이터는 한 폴더에 저장됩니다. 게임 파일은 별도 위치에 보관합니다.\n폴더가 없으면 설치할 때 생성합니다.")
            self.folder_entry("① 프로그램 설치 위치 (실행 파일 + data 폴더)", self.program_var)
            self.folder_entry("② 게임 압축파일 폴더 (.zip / .7z)", self.archive_var)
            self.folder_entry("③ 설치된 게임 폴더 (압축 해제 대상)", self.game_var)
            tk.Checkbutton(self.body, text="바탕화면에 바로가기 만들기", variable=self.desktop_shortcut,
                           bg="#eff3f7", activebackground="#eff3f7", fg="#18364d",
                           font=("Malgun Gothic", 10)).pack(anchor="w", pady=(0, 12))
            tk.Label(self.body, text="기존 AppData 모음집·캐시를 복사합니다. 원본 게임 파일은 유지됩니다.",
                     bg="#eff3f7", fg="#637789", font=("Malgun Gothic", 9)).pack(anchor="w")
            self.back_btn.state(["!disabled"])
            self.next_btn.config(text="설치")
        elif self.page == 2:
            self.title_text("설치 중", "프로그램 파일을 설치하고 기존 데이터를 이전하고 있어요.")
            self.status = tk.Label(self.body, text="준비 중...", bg="#eff3f7", fg="#244d69",
                                   font=("Malgun Gothic", 11))
            self.status.pack(anchor="w", pady=(20, 16))
            self.bar = ttk.Progressbar(self.body, maximum=100, mode="indeterminate",
                                       style="Wizard.Horizontal.TProgressbar")
            self.bar.pack(fill="x")
            self.bar.start(12)
            self.back_btn.state(["disabled"])
            self.next_btn.state(["disabled"])
            self.cancel_btn.state(["disabled"])
        else:
            self.title_text("설치 완료!", "PlayDock가 설치되었고 게임 폴더 설정이 저장됐습니다.")
            for label, value in (("프로그램 폴더:", self.program_var.get()),
                                 ("앱 데이터:", str(program_store(Path(self.program_var.get())))),
                                 ("압축파일 폴더:", self.archive_var.get()),
                                 ("게임 설치 폴더:", self.game_var.get())):
                tk.Label(self.body, text=label, bg="#eff3f7", fg="#223d55",
                         font=("Malgun Gothic", 10, "bold")).pack(anchor="w", pady=(10, 1))
                tk.Label(self.body, text=value, bg="#eff3f7", fg="#576a7b",
                         font=("Malgun Gothic", 9), wraplength=660).pack(anchor="w")
            tk.Checkbutton(self.body, text="설치 완료 후 프로그램 실행", variable=self.launch_after,
                           bg="#eff3f7", activebackground="#eff3f7", fg="#18364d",
                           font=("Malgun Gothic", 10)).pack(anchor="w", pady=(15, 0))
            if self.shortcut_warning:
                tk.Label(self.body, text=self.shortcut_warning, bg="#eff3f7", fg="#9a4b27",
                         font=("Malgun Gothic", 9), wraplength=650).pack(anchor="w", pady=6)
            self.back_btn.state(["disabled"])
            self.cancel_btn.config(text="닫기", state="normal")
            self.next_btn.config(text="완료", state="normal")

    def advance(self):
        if self.page == 0:
            self.page = 1
            self.render()
        elif self.page == 1:
            try:
                archive_path, game_path = normalize_paths(self.archive_var.get(), self.game_var.get())
                normalize_program_path(self.program_var.get(), archive_path, game_path)
                payload_executable()
                payload_title_editor()
                payload_uninstaller()
            except Exception as exc:
                messagebox.showerror("설치 준비 실패", str(exc), parent=self)
                return
            # Capture Tk variables on the GUI thread: touching StringVar/BooleanVar
            # from a worker raises 'main thread is not in main loop' in frozen apps.
            self.install_archive = self.archive_var.get()
            self.install_game_dir = self.game_var.get()
            self.install_program_dir = normalize_program_path(self.program_var.get(), archive_path, game_path)
            self.install_desktop = bool(self.desktop_shortcut.get())
            self.page = 2
            self.render()
            threading.Thread(target=self.install, daemon=True).start()
        elif self.page == 3:
            if self.launch_after.get():
                try:
                    subprocess.Popen([str(installed_executable(self.install_program_dir))], cwd=str(self.install_program_dir),
                                     creationflags=getattr(subprocess, "DETACHED_PROCESS", 0))
                except OSError as exc:
                    messagebox.showwarning("프로그램 실행 오류", f"설치는 완료됐지만 바로 실행하지 못했어요.\n{exc}", parent=self)
            self.destroy()

    def install(self):
        tmp = None
        try:
            archive_path, game_path = normalize_paths(self.install_archive, self.install_game_dir)
            program = normalize_program_path(self.install_program_dir, archive_path, game_path)
            previous = app_install_directory()
            old_install_at_target = (program / LEGACY_INSTALL_MARKER).is_file() and marker_is_valid(program)
            program.mkdir(parents=True, exist_ok=True)
            # Check writability before copying any file. Avoid protected dirs.
            with tempfile.NamedTemporaryFile(prefix='.lgs-write-test-', dir=program, delete=True):
                pass
            executable = installed_executable(program)
            tmp = executable.with_name('PlayDock.new.exe')
            self.messages.put(('progress', '게임 라이브러리 설치 중...'))
            shutil.copy2(payload_executable(), tmp)
            os.replace(tmp, executable)
            editor = installed_title_editor(program)
            tmp = editor.with_name('PlayDock_TitleEditor.new.exe')
            self.messages.put(('progress', '게임 이름 관리자 설치 중...'))
            shutil.copy2(payload_title_editor(), tmp)
            os.replace(tmp, editor)
            uninstaller = installed_uninstaller(program)
            tmp = uninstaller.with_name('PlayDock_Uninstall.new.exe')
            self.messages.put(('progress', '제거 프로그램 설치 중...'))
            shutil.copy2(payload_uninstaller(), tmp)
            os.replace(tmp, uninstaller)
            self.messages.put(('progress', '기존 모음집과 캐시 이전 중...'))
            destination = program_store(program)
            sources = []
            if not same_path(previous, program) and marker_is_valid(previous):
                sources.append(program_store(previous))
            sources.append(legacy_data_dir())
            migrated = migrate_legacy_data(destination, sources)
            for directory in ('cache', 'backups', 'logs'):
                (destination / directory).mkdir(parents=True, exist_ok=True)
            # Save the game folder choices inside the installed program's data.
            save_folder_settings(self.install_archive, self.install_game_dir,
                                 store_path=destination / 'settings.json')
            write_install_marker(program)
            self.messages.put(('progress', '시작 메뉴와 바탕화면 바로가기 생성 중...'))
            if sys.platform == 'win32':
                try:
                    start_menu = (Path(os.getenv('APPDATA', '')) / 'Microsoft' / 'Windows' /
                                  'Start Menu' / 'Programs' / 'PlayDock.lnk')
                    create_shortcut(executable, start_menu)
                    create_shortcut(editor, start_menu.with_name('PlayDock 이름 관리자.lnk'))
                    create_shortcut(uninstaller, start_menu.with_name('PlayDock 제거.lnk'))
                except Exception as exc:
                    self.messages.put(('shortcut_error', f'시작 메뉴 바로가기를 생성하지 못했습니다: {exc}'))
                if self.install_desktop:
                    try:
                        desktop = desktop_directory() / 'PlayDock.lnk'
                        create_shortcut(executable, desktop)
                        create_shortcut(editor, desktop.with_name('PlayDock 이름 관리자.lnk'))
                    except Exception as exc:
                        self.messages.put(('shortcut_error', f'바탕화면 바로가기를 생성하지 못했습니다: {exc}'))
            register_uninstall_entry(program)
            # Remove obsolete *program binaries and shortcuts only* after a verified
            # in-place upgrade. The data/ directory and game folders are untouched.
            if old_install_at_target:
                for old_name in LEGACY_BINARIES:
                    old_exe = program / old_name
                    if old_exe.is_file() and not old_exe.is_symlink():
                        try:
                            old_exe.unlink()
                        except OSError:
                            self.messages.put(('shortcut_error', '예전 실행 파일이 사용 중이라 남아 있습니다. 종료 후 정리할 수 있습니다.'))
                try:
                    old_marker = program / LEGACY_INSTALL_MARKER
                    old_data = json.loads(old_marker.read_text(encoding='utf-8'))
                    if (old_data.get('id') == LEGACY_MARKER_ID and old_data.get('data_directory') == 'data'):
                        old_marker.unlink()
                except (OSError, ValueError, AttributeError):
                    pass
                if sys.platform == 'win32':
                    old_shortcuts = [
                        (Path(os.getenv('APPDATA', '')) / 'Microsoft' / 'Windows' / 'Start Menu' / 'Programs' / f'Local Game Shelf{suffix}.lnk', program / exe)
                        for suffix, exe in (('', LEGACY_BINARIES[0]), (' 이름 관리자', LEGACY_BINARIES[1]), (' 제거', LEGACY_BINARIES[2]))
                    ] + [
                        (desktop_directory() / f'Local Game Shelf{suffix}.lnk', program / exe)
                        for suffix, exe in (('', LEGACY_BINARIES[0]), (' 이름 관리자', LEGACY_BINARIES[1]))
                    ]
                    for old_link, old_target in old_shortcuts:
                        if shortcut_points_to(old_link, old_target):
                            old_link.unlink(missing_ok=True)
            if not same_path(previous, program) and previous.is_dir():
                self.messages.put(('shortcut_error', '설치 경로를 변경했습니다. 이전 프로그램 폴더는 안전을 위해 자동 삭제하지 않았습니다.'))
            self.messages.put(('done', f"이전된 데이터 {migrated['copied']}개"))
        except Exception as exc:
            self.messages.put(('error', str(exc)))
        finally:
            if tmp is not None:
                tmp.unlink(missing_ok=True)

    def poll(self):
        try:
            while True:
                kind, text = self.messages.get_nowait()
                if kind == "progress":
                    if self.page == 2:
                        self.status.configure(text=text)
                elif kind == "shortcut_error":
                    self.shortcut_warning = text
                elif kind == "done":
                    if self.page == 2:
                        self.bar.stop()
                    self.installed = True
                    self.page = 3
                    self.render()
                elif kind == "error":
                    if self.page == 2:
                        self.bar.stop()
                    self.page = 1
                    self.render()
                    self.cancel_btn.state(["!disabled"])
                    messagebox.showerror("설치 실패", text, parent=self)
        except queue.Empty:
            pass
        self.after(120, self.poll)

    def back(self):
        if self.page == 1:
            self.page = 0
            self.render()

    def close(self):
        if self.page == 2:
            return
        self.destroy()


if __name__ == "__main__":
    if sys.platform != "win32":
        print("Windows 전용 설치 마법사입니다.")
        sys.exit(1)
    if '--self-test' in sys.argv:
        # No dialogs / files modified; check that PyInstaller actually embedded
        # the full application EXE before distributing the installer.
        binary = payload_executable()
        editor = payload_title_editor()
        uninstaller = payload_uninstaller()
        if any(p.stat().st_size < 100_000 for p in (binary, editor, uninstaller)):
            raise RuntimeError('설치 프로그램에 본체, 이름 관리자, 제거 프로그램 EXE가 모두 포함되어야 합니다.')
        sys.exit(0)
    SetupWizard().mainloop()
