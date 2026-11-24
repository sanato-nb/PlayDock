"""Per-user Windows installation and uninstall registry helpers.

Application binaries live ONLY under %LOCALAPPDATA%/Programs/PlayDock.
User archives, extracted games, settings, saves and artwork are never touched.
"""
from __future__ import annotations

import base64
import binascii
import os
from pathlib import Path
from storage.local import (INSTALL_MARKER, LEGACY_INSTALL_MARKER, LEGACY_MARKER_ID,
                           marker_is_valid)
import subprocess
import sys

DISPLAY_NAME = "PlayDock"
VERSION = "0.8.0"
MAIN_EXE = "PlayDock.exe"
EDITOR_EXE = "PlayDock_TitleEditor.exe"
UNINSTALL_EXE = "PlayDock_Uninstall.exe"
INSTALLED_FILES = (MAIN_EXE, EDITOR_EXE, UNINSTALL_EXE)
REGISTRY_KEY = r"Software\Microsoft\Windows\CurrentVersion\Uninstall\PlayDock"
LEGACY_REGISTRY_KEY = r"Software\Microsoft\Windows\CurrentVersion\Uninstall\LocalGameShelf"
LEGACY_DISPLAY_NAME = "Local Game Shelf"
LEGACY_BINARIES = ("LocalGameShelf.exe", "LocalGameShelf_TitleEditor.exe", "LocalGameShelf_Uninstall.exe")


def legacy_program_directory() -> Path:
    local = Path(os.getenv('LOCALAPPDATA') or (Path.home() / 'AppData' / 'Local'))
    return local / 'Programs' / 'LocalGameShelf'


def default_program_directory() -> Path:
    return legacy_program_directory().with_name('PlayDock')


def _registered_location(key_name: str, allowed_name: str) -> Path | None:
    """Read ONLY a matching HKCU uninstall entry with a known installation marker."""
    if sys.platform != 'win32':
        return None
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_name) as key:
            name = winreg.QueryValueEx(key, 'DisplayName')[0]
            value = winreg.QueryValueEx(key, 'InstallLocation')[0]
        if name != allowed_name or not isinstance(value, str) or not value:
            return None
        path = Path(value).absolute()
        if marker_is_valid(path) or same_path(path, legacy_program_directory()):
            return path
    except (OSError, AttributeError, ValueError):
        pass
    return None


def registered_install_directory() -> Path | None:
    """Prefer PlayDock registration, then a verified older Local Game Shelf install."""
    return (_registered_location(REGISTRY_KEY, DISPLAY_NAME)
            or _registered_location(LEGACY_REGISTRY_KEY, LEGACY_DISPLAY_NAME))


def app_install_directory() -> Path:
    registered = registered_install_directory()
    if registered is not None:
        return registered
    legacy = legacy_program_directory()
    if legacy.is_dir() and (marker_is_valid(legacy) or (legacy / LEGACY_BINARIES[0]).is_file()):
        return legacy
    return default_program_directory()


def same_path(a: Path, b: Path) -> bool:
    return os.path.normcase(os.path.abspath(a)).casefold() == os.path.normcase(os.path.abspath(b)).casefold()


def normalize_program_path(program: Path | str, archive: Path, games: Path) -> Path:
    """Require a distinct, writable user folder; never overlap game folders."""
    if not str(program).strip():
        raise ValueError("프로그램 설치 폴더를 선택해 주세요.")
    path = Path(os.path.expandvars(os.path.expanduser(str(program)))).absolute()
    if path == Path(path.anchor):
        raise ValueError('프로그램 설치 위치는 드라이브 루트가 아닌 별도 폴더여야 합니다.')
    system_root = Path(os.environ.get('WINDIR', r'C:\Windows')).absolute()
    protected = [system_root]
    for env in ('ProgramFiles', 'ProgramFiles(x86)'):
        if os.environ.get(env):
            protected.append(Path(os.environ[env]).absolute())
    for unsafe in protected:
        if same_path(path, unsafe) or unsafe in path.parents:
            raise ValueError('Windows 또는 Program Files 아래에는 설치하지 마세요.')
    for folder in (archive, games):
        other = Path(folder).absolute()
        if same_path(path, other) or path in other.parents or other in path.parents:
            raise ValueError('프로그램 폴더와 게임 폴더는 서로 독립된 위치여야 합니다.')
    if path.exists() and not path.is_dir():
        raise ValueError('프로그램 설치 위치가 폴더가 아닙니다.')
    ancestor = path
    while True:
        if ancestor.is_symlink() or (hasattr(ancestor, 'is_junction') and ancestor.is_junction()):
            raise ValueError('프로그램 설치 경로에 링크 또는 정션이 있어 설치하지 않습니다.')
        if ancestor == ancestor.parent:
            break
        ancestor = ancestor.parent
    return path


def desktop_directory() -> Path:
    if sys.platform == "win32":
        try:
            import ctypes
            buf = ctypes.create_unicode_buffer(32768)
            if ctypes.windll.shell32.SHGetFolderPathW(None, 0x0010, None, 0, buf) == 0 and buf.value:
                return Path(buf.value)
        except (AttributeError, OSError, ValueError):
            pass
    return Path(os.getenv("USERPROFILE", str(Path.home()))) / "Desktop"


def expected_shortcuts() -> list[tuple[Path, Path]]:
    start = (Path(os.getenv("APPDATA") or (Path.home() / "AppData" / "Roaming"))
             / "Microsoft" / "Windows" / "Start Menu" / "Programs")
    dest = app_install_directory()
    return [
        (start / "PlayDock.lnk", dest / MAIN_EXE),
        (start / "PlayDock 이름 관리자.lnk", dest / EDITOR_EXE),
        (start / "PlayDock 제거.lnk", dest / UNINSTALL_EXE),
        (desktop_directory() / "PlayDock.lnk", dest / MAIN_EXE),
        (desktop_directory() / "PlayDock 이름 관리자.lnk", dest / EDITOR_EXE),
    ]


def register_uninstall_entry(program: Path | None = None) -> None:
    """Register the app in Settings > Apps and Programs and Features (current user)."""
    if sys.platform != "win32":
        raise RuntimeError("Windows에서만 제거 프로그램을 등록할 수 있습니다.")
    import winreg
    directory = Path(program) if program is not None else app_install_directory()
    uninstaller = directory / UNINSTALL_EXE
    if not uninstaller.is_file():
        raise FileNotFoundError(f"제거 프로그램이 설치되지 않았습니다: {uninstaller}")
    entries = {
        "DisplayName": DISPLAY_NAME,
        "DisplayVersion": VERSION,
        "Publisher": "PlayDock",
        "InstallLocation": str(directory),
        "DisplayIcon": f'"{directory / MAIN_EXE}",0',
        "UninstallString": f'"{uninstaller}"',
    }
    with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, REGISTRY_KEY, 0, winreg.KEY_SET_VALUE) as key:
        for name, value in entries.items():
            winreg.SetValueEx(key, name, 0, winreg.REG_SZ, value)
        winreg.SetValueEx(key, "NoModify", 0, winreg.REG_DWORD, 1)
        winreg.SetValueEx(key, "NoRepair", 0, winreg.REG_DWORD, 1)
    # Upgrade a genuine legacy registration without leaving a duplicate app entry.
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, LEGACY_REGISTRY_KEY) as key:
            old_name = winreg.QueryValueEx(key, 'DisplayName')[0]
            old_dir = winreg.QueryValueEx(key, 'InstallLocation')[0]
        if (old_name == LEGACY_DISPLAY_NAME and isinstance(old_dir, str)
                and same_path(Path(old_dir), directory)):
            winreg.DeleteKey(winreg.HKEY_CURRENT_USER, LEGACY_REGISTRY_KEY)
    except (OSError, ValueError, AttributeError):
        pass


def remove_uninstall_entry() -> None:
    """Remove only our own HKCU entry, and only when it targets our install."""
    if sys.platform != "win32":
        return
    import winreg
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, REGISTRY_KEY, 0, winreg.KEY_READ) as key:
            location = winreg.QueryValueEx(key, "InstallLocation")[0]
            name = winreg.QueryValueEx(key, "DisplayName")[0]
    except FileNotFoundError:
        return
    if name != DISPLAY_NAME or os.path.normcase(os.path.abspath(location)) != os.path.normcase(os.path.abspath(app_install_directory())):
        raise RuntimeError("등록된 제거 항목의 경로가 달라 삭제하지 않았습니다.")
    winreg.DeleteKey(winreg.HKEY_CURRENT_USER, REGISTRY_KEY)


def validate_install_directory(folder: Path) -> Path:
    """Allow only the current registered install, and reject redirected roots."""
    expected = app_install_directory()
    actual = Path(folder)
    if not same_path(actual, expected):
        raise ValueError('지정된 프로그램 설치 경로가 등록된 경로와 다릅니다.')
    if actual.is_symlink() or (hasattr(actual, 'is_junction') and actual.is_junction()):
        raise ValueError('설치 폴더가 링크 또는 정션이어서 제거를 중단했습니다.')
    if actual.exists() and not actual.is_dir():
        raise ValueError('설치 경로가 폴더가 아닙니다.')
    # New installations have a marker; legacy releases used a fixed directory.
    if not same_path(actual, legacy_program_directory()) and not marker_is_valid(actual):
        raise ValueError('프로그램 설치 표식이 없어 제거를 중단했습니다.')
    return actual


def _ps_literal(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def _run_powershell(script: str) -> str:
    code = base64.b64encode(script.encode("utf-16-le")).decode("ascii")
    result = subprocess.run(
        ["powershell.exe", "-NoProfile", "-NonInteractive", "-EncodedCommand", code],
        capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=20,
    )
    if result.returncode:
        raise OSError("Windows 바로가기 확인에 실패했습니다.")
    return result.stdout.strip()


def shortcut_points_to(link: Path, exe: Path) -> bool:
    """Do not remove a user shortcut if it was repointed to another program."""
    if not link.is_file():
        return False
    try:
        query = ("$ws = New-Object -ComObject WScript.Shell; "
                 f"$item = $ws.CreateShortcut({_ps_literal(str(link))}); "
                 "[Console]::Out.Write([Convert]::ToBase64String([Text.Encoding]::Unicode.GetBytes($item.TargetPath)))")
        encoded_target = _run_powershell(query)
        target = base64.b64decode(encoded_target, validate=True).decode("utf-16-le")
        return os.path.normcase(os.path.abspath(target)).casefold() == os.path.normcase(os.path.abspath(exe)).casefold()
    except (OSError, subprocess.TimeoutExpired, ValueError, UnicodeError, binascii.Error):
        return False


def ensure_apps_closed() -> None:
    """Avoid partially removing the installation while either app is running."""
    if sys.platform != "win32":
        return
    for exe_name in (MAIN_EXE, EDITOR_EXE):
        try:
            result = subprocess.run(["tasklist.exe", "/FI", f"IMAGENAME eq {exe_name}",
                                     "/FO", "CSV", "/NH"], capture_output=True,
                                    text=True, errors="replace", timeout=10)
            if result.returncode == 0 and f'"{exe_name.lower()}"' in result.stdout.lower():
                raise PermissionError(f"{exe_name} 프로그램을 종료한 뒤 제거해 주세요.")
        except (FileNotFoundError, subprocess.TimeoutExpired):
            # File locks are still enforced by unlink() on Windows.
            pass


def uninstall_application() -> list[str]:
    """Uninstall allowlisted binaries only; preserve ALL user data and unknown files.

    The running uninstaller must be a staged copy in TEMP, not the original
    installed EXE. Any PermissionError (e.g. running app) aborts registration
    removal so the user can close the app and retry.
    """
    folder = validate_install_directory(app_install_directory())
    ensure_apps_closed()
    notes = []
    if folder.exists():
        for filename in INSTALLED_FILES:
            file = folder / filename
            if file.is_symlink() or file.is_file():
                file.unlink()
                notes.append(filename)
            elif file.exists():
                raise OSError(f"예상하지 못한 항목이어서 삭제하지 않았습니다: {file}")
    for link, target in expected_shortcuts():
        if shortcut_points_to(link, target):
            link.unlink()
    remove_uninstall_entry()
    # Remove the marker LAST: registry and shortcut validation need it to find
    # the custom install path, while data/ remains untouched.
    for marker_name, expected_id in ((INSTALL_MARKER, 'playdock-installed-v1'),
                                     (LEGACY_INSTALL_MARKER, LEGACY_MARKER_ID)):
        marker = folder / marker_name
        if marker.is_file() and not marker.is_symlink():
            try:
                import json
                content = json.loads(marker.read_text(encoding='utf-8'))
            except (OSError, ValueError):
                continue
            if isinstance(content, dict) and content.get('id') == expected_id and content.get('data_directory') == 'data':
                marker.unlink()
                notes.append(marker_name)
    if folder.exists():
        try:
            folder.rmdir()   # Remove ONLY if empty; never recursive delete
        except OSError:
            notes.append("다른 파일이 남은 프로그램 폴더는 보존했습니다.")
    return notes
