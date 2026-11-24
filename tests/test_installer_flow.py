"""End-to-end setup logic, without showing a Windows UI or installing on the host."""
from pathlib import Path
import json
import queue
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import setup_wizard
import local_storage


def test_setup_copies_exes_and_legacy_collection_to_chosen_program_folder(tmp_path, monkeypatch):
    old = tmp_path / 'old' / 'LocalGameShelf'
    old.mkdir(parents=True)
    archives = tmp_path / 'games' / 'archives'
    games = tmp_path / 'games' / 'installed'
    program = tmp_path / 'programs' / 'LocalGameShelf'
    legacy = tmp_path / 'appdata' / 'LocalGameShelf'
    legacy.mkdir(parents=True)
    (legacy / 'settings.json').write_text(json.dumps({'auto_art': True}), encoding='utf-8')
    (legacy / 'collections.json').write_text(json.dumps({'collections':[{'id':'test','name':'RPG','game_ids':[]}]}), encoding='utf-8')
    originals = []
    for name in ('PlayDock.exe', 'PlayDock_TitleEditor.exe', 'PlayDock_Uninstall.exe'):
        file = tmp_path / name
        file.write_bytes(b'MZ app binary ' + name.encode('utf-8'))
        originals.append(file)
    monkeypatch.setattr(setup_wizard, 'payload_executable', lambda: originals[0])
    monkeypatch.setattr(setup_wizard, 'payload_title_editor', lambda: originals[1])
    monkeypatch.setattr(setup_wizard, 'payload_uninstaller', lambda: originals[2])
    monkeypatch.setattr(setup_wizard, 'legacy_data_dir', lambda: legacy)
    monkeypatch.setattr(setup_wizard, 'app_install_directory', lambda: old)
    registered = []
    monkeypatch.setattr(setup_wizard, 'register_uninstall_entry', lambda folder: registered.append(folder))
    # A Windows build runs these same tests: never create real Start/Desktop links.
    monkeypatch.setattr(setup_wizard, 'create_shortcut', lambda target, link: None)
    monkeypatch.setattr(setup_wizard, 'desktop_directory', lambda: tmp_path / 'fake-desktop')
    class MockWizard:
        install_archive = str(archives)
        install_game_dir = str(games)
        install_program_dir = program
        install_desktop = True
        messages = queue.Queue()
    fake = MockWizard()
    setup_wizard.SetupWizard.install(fake)
    messages = []
    while not fake.messages.empty():
        messages.append(fake.messages.get_nowait())
    assert not [m for m in messages if m[0] == 'error'], messages
    assert messages[-1][0] == 'done'
    assert registered == [program]
    assert all((program/f.name).read_bytes() == f.read_bytes() for f in originals)
    assert local_storage.marker_is_valid(program)
    assert (program/'data'/'collections.json').read_bytes() == (legacy/'collections.json').read_bytes()
    settings = json.loads((program/'data'/'settings.json').read_text(encoding='utf-8'))
    assert settings['archives'] == str(archives)
    assert settings['library'] == str(games)
    assert settings['first_run_complete'] is True
    assert (legacy/'settings.json').exists()  # leave legacy source intact
    assert all((program/'data'/f).is_dir() for f in ('cache','backups','logs'))


def test_installer_rejects_program_folder_inside_games(tmp_path, monkeypatch):
    from install_management import normalize_program_path
    game_root = tmp_path / 'games'
    with __import__('pytest').raises(ValueError):
        normalize_program_path(game_root / 'programs', tmp_path/'archive', game_root)
