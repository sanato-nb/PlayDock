"""Safety tests: program uninstall must never remove user archives or data."""
from __future__ import annotations

import base64
from pathlib import Path
import sys
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import install_management as mgr
import setup_wizard


def test_uninstall_only_known_binary_files_preserves_user_files(tmp_path, monkeypatch):
    installed = tmp_path / 'Programs' / 'LocalGameShelf'
    installed.mkdir(parents=True)
    from local_storage import write_install_marker
    write_install_marker(installed)
    for name in mgr.INSTALLED_FILES:
        (installed / name).write_bytes(b'MZplaceholder')
    # Arbitrary user file under the same folder must never be recursively deleted.
    (installed / 'personal.json').write_text('keep')
    settings = tmp_path / 'LocalGameShelf' / 'settings.json'
    settings.parent.mkdir()
    settings.write_text('keep settings')
    archives = tmp_path / 'archives'
    games = tmp_path / 'games'
    archives.mkdir()
    games.mkdir()
    (archives / 'game.7z').write_bytes(b'archive')
    (games / 'Game.exe').write_bytes(b'game exe')

    monkeypatch.setattr(mgr, 'app_install_directory', lambda: installed)
    monkeypatch.setattr(mgr, 'expected_shortcuts', lambda: [])
    called = []
    monkeypatch.setattr(mgr, 'remove_uninstall_entry', lambda: called.append('registry'))
    result = mgr.uninstall_application()
    assert all(not (installed / name).exists() for name in mgr.INSTALLED_FILES)
    assert (installed / 'personal.json').read_text() == 'keep'
    assert settings.read_text() == 'keep settings'
    assert (archives / 'game.7z').read_bytes() == b'archive'
    assert (games / 'Game.exe').read_bytes() == b'game exe'
    assert called == ['registry']
    assert len(result) == 5  # three binaries + marker + preserved-folder note


def test_uninstall_removes_empty_program_folder(tmp_path, monkeypatch):
    folder = tmp_path / 'Programs' / 'LocalGameShelf'
    folder.mkdir(parents=True)
    from local_storage import write_install_marker
    write_install_marker(folder)
    (folder / mgr.MAIN_EXE).write_bytes(b'MZ')
    monkeypatch.setattr(mgr, 'app_install_directory', lambda: folder)
    monkeypatch.setattr(mgr, 'expected_shortcuts', lambda: [])
    monkeypatch.setattr(mgr, 'remove_uninstall_entry', lambda: None)
    mgr.uninstall_application()
    assert not folder.exists()


def test_uninstall_never_uses_arbitrary_path(tmp_path, monkeypatch):
    correct = tmp_path / 'Programs' / 'LocalGameShelf'
    bad = tmp_path / 'ImportantFiles'
    correct.mkdir(parents=True)
    bad.mkdir()
    (bad / mgr.MAIN_EXE).write_bytes(b'MZ')
    monkeypatch.setattr(mgr, 'app_install_directory', lambda: correct)
    with pytest.raises(ValueError):
        mgr.validate_install_directory(bad)
    assert (bad / mgr.MAIN_EXE).exists()


def test_uninstall_fails_if_unexpected_directory_has_exe_name(tmp_path, monkeypatch):
    folder = tmp_path / 'Programs' / 'LocalGameShelf'
    folder.mkdir(parents=True)
    from local_storage import write_install_marker
    write_install_marker(folder)
    (folder / mgr.MAIN_EXE).mkdir()
    monkeypatch.setattr(mgr, 'app_install_directory', lambda: folder)
    monkeypatch.setattr(mgr, 'expected_shortcuts', lambda: [])
    called = []
    monkeypatch.setattr(mgr, 'remove_uninstall_entry', lambda: called.append(True))
    with pytest.raises(OSError):
        mgr.uninstall_application()
    assert not called


def test_uninstall_registry_path_and_values_are_current_user():
    assert mgr.REGISTRY_KEY.startswith(r'Software\Microsoft\Windows\CurrentVersion\Uninstall')
    assert setup_wizard.UNINSTALL_EXE == mgr.UNINSTALL_EXE
    assert 'register_uninstall_entry(program)' in Path(setup_wizard.__file__).read_text(encoding='utf-8')
    assert mgr.UNINSTALL_EXE in mgr.INSTALLED_FILES


def test_shortcut_protection_against_retargeted_shortcuts(tmp_path, monkeypatch):
    shortcut = tmp_path / 'Local Game Shelf.lnk'
    shortcut.write_text('fake-shortcut')
    intended_exe = tmp_path / mgr.MAIN_EXE
    monkeypatch.setattr(mgr, '_run_powershell', lambda script: base64.b64encode('C:\\NotOurApp\\other.exe'.encode('utf-16-le')).decode())
    assert mgr.shortcut_points_to(shortcut, intended_exe) is False
    monkeypatch.setattr(mgr, '_run_powershell', lambda script: base64.b64encode(str(intended_exe).encode('utf-16-le')).decode())
    assert mgr.shortcut_points_to(shortcut, intended_exe) is True


def test_build_script_includes_uninstaller_exe():
    root = Path(__file__).resolve().parents[1]
    ps = (root / 'Build-Windows-Release.ps1').read_text(encoding='utf-8-sig')
    cmd = (root / 'build_setup_windows.bat').read_text(encoding='utf-8')
    assert "Run-PyInstaller 'PlayDock_Uninstall'" in ps
    assert "'--add-binary','dist\\PlayDock_Uninstall.exe;payload'" in ps
    assert '--add-binary "dist\\PlayDock_Uninstall.exe;payload"' in cmd


def test_registry_registration_targets_app_uninstaller_in_hkcu(tmp_path, monkeypatch):
    import types
    root = tmp_path / 'Programs' / 'LocalGameShelf'
    root.mkdir(parents=True)
    (root / mgr.UNINSTALL_EXE).write_bytes(b'MZ')
    monkeypatch.setattr(mgr, 'app_install_directory', lambda: root)
    monkeypatch.setattr(mgr.sys, 'platform', 'win32')
    saved = {}
    class FakeKey:
        def __enter__(self):
            return self
        def __exit__(self, *args):
            return False
    def create_key(hive, path, reserved, access):
        assert hive == 'HKCU'
        assert path == mgr.REGISTRY_KEY
        assert access == 2
        return FakeKey()
    def set_value(key, name, reserved, kind, value):
        saved[name] = value
    fake = types.SimpleNamespace(
        HKEY_CURRENT_USER='HKCU', KEY_SET_VALUE=2, REG_SZ=1, REG_DWORD=4,
        CreateKeyEx=create_key, SetValueEx=set_value,
    )
    monkeypatch.setitem(sys.modules, 'winreg', fake)
    mgr.register_uninstall_entry()
    assert saved['DisplayName'] == 'PlayDock'
    assert saved['UninstallString'] == f'"{root / mgr.UNINSTALL_EXE}"'
    assert saved['InstallLocation'] == str(root)
    assert saved['NoModify'] == 1
    assert saved['NoRepair'] == 1
