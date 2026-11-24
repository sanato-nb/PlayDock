"""No PySide6 required: the launch-approval policy is independent of the GUI."""
from pathlib import Path
import sys
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from services.launch_approval import (
    APPROVED_EXE_KEY, executable_identity, needs_launch_confirmation,
    launch_approval_changes, executable_selection_changes,
)
from core import Library, Game


def game_env(tmp_path):
    root = tmp_path / 'installed' / 'demo'
    root.mkdir(parents=True)
    exe = root / 'Game.exe'
    exe.write_bytes(b'MZ')
    alt = root / 'Other.exe'
    alt.write_bytes(b'MZ')
    lib = Library(tmp_path / 'config')
    game = Game('demo', 'demo', root.parent, folder=root)
    return lib, game, exe, alt


def test_confirmation_only_on_first_launch(tmp_path):
    lib, game, exe, _ = game_env(tmp_path)
    assert needs_launch_confirmation(lib.meta(game), game.folder, exe)
    lib.update_meta(game, **launch_approval_changes(game.folder, exe))
    assert not needs_launch_confirmation(lib.meta(game), game.folder, exe)
    assert not needs_launch_confirmation(Library(lib.store).meta(game), game.folder, exe)


def test_changing_exe_requests_confirmation_again(tmp_path):
    lib, game, exe, alt = game_env(tmp_path)
    lib.update_meta(game, executable='Game.exe', **launch_approval_changes(game.folder, exe))
    changes = executable_selection_changes(game.folder, 'Other.exe', lib.meta(game))
    assert changes['executable'] == 'Other.exe'
    assert changes[APPROVED_EXE_KEY] is None
    lib.update_meta(game, **changes)
    assert needs_launch_confirmation(lib.meta(game), game.folder, alt)
    lib.update_meta(game, **launch_approval_changes(game.folder, alt))
    assert not needs_launch_confirmation(lib.meta(game), game.folder, alt)


def test_reselecting_same_exe_preserves_approval(tmp_path):
    lib, game, exe, _ = game_env(tmp_path)
    meta = lib.update_meta(game, executable='Game.exe', **launch_approval_changes(game.folder, exe))
    changes = executable_selection_changes(game.folder, 'Game.exe', meta)
    assert APPROVED_EXE_KEY not in changes


def test_paths_are_normalized_per_installation(tmp_path):
    _, game, exe, _ = game_env(tmp_path)
    assert executable_identity(game.folder, exe) == 'game.exe'
    assert executable_identity(game.folder, game.folder / './Game.exe') == 'game.exe'


def test_executable_outside_game_folder_cannot_be_approved(tmp_path):
    _, game, _, _ = game_env(tmp_path)
    outside = tmp_path / 'outside.exe'
    outside.write_bytes(b'MZ')
    with pytest.raises(ValueError):
        launch_approval_changes(game.folder, outside)
    with pytest.raises(ValueError):
        executable_selection_changes(game.folder, str(outside), {})


def test_non_executable_cannot_be_approved(tmp_path):
    _, game, _, _ = game_env(tmp_path)
    doc = game.folder / 'readme.txt'
    doc.write_text('hi', encoding='utf-8')
    with pytest.raises(ValueError):
        needs_launch_confirmation({}, game.folder, doc)
