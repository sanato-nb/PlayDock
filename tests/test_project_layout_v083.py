"""PlayDock v0.8.3 repository layout checks without loading Qt."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / 'src' / 'playdock'


def test_source_modules_are_grouped_and_entrypoints_remain_available():
    for folder in ('ui', 'controllers', 'services'):
        assert (APP / folder / '__init__.py').is_file()
        assert not (ROOT / folder).exists()
    assert (APP / 'core.py').is_file()
    assert (APP / 'work_db.py').is_file()
    for entry in ('app.py', 'title_editor.py', 'setup_wizard.py', 'uninstall_wizard.py'):
        assert (ROOT / entry).is_file()
        assert 'src' in (ROOT / entry).read_text(encoding='utf-8')
    assert not (ROOT / 'data').exists()


def test_script_folder_keeps_release_entrypoints_and_manual_workflow():
    assert (ROOT / 'scripts' / 'make_public_release.py').is_file()
    assert (ROOT / 'scripts' / 'Build-Windows-Release.ps1').is_file()
    assert '--paths' in (ROOT / 'scripts' / 'Build-Windows-Release.ps1').read_text(encoding='utf-8-sig')
    workflow = (ROOT / '.github' / 'workflows' / 'build-windows-exe.yml').read_text(encoding='utf-8')
    assert 'workflow_dispatch:' in workflow
    assert '\n  push:' not in workflow
    assert 'scripts/Build-Windows-Release.ps1' in workflow
    for script in ('00_BUILD_WINDOWS_EXE.bat', '01_REPACKAGE_EXISTING_EXES.bat'):
        path = ROOT / 'scripts' / script
        data = path.read_bytes()
        assert data.isascii() and b'\r\n' in data
        assert b'%~dp0..' in data


def test_user_data_is_not_tracked_in_source_tree():
    assert not list(ROOT.rglob('settings.json'))
    assert not list(ROOT.rglob('collections.json'))
    assert not list(ROOT.rglob('playdock.db'))
    gitignore = (ROOT / '.gitignore').read_text(encoding='utf-8')
    for item in ('data/', '*.db', 'public_release/', '.env'):
        assert item in gitignore
