"""Retired game-save backup must not be callable; app data remains safe."""
from pathlib import Path
import ast
import importlib.util
import zipfile

from core import Library
from controllers.game_actions import GameActionControllerMixin
from workers import game_tasks
from services.data_service import backup_data, restore_data
from database.work_repository import WorkDatabase

ROOT = Path(__file__).resolve().parents[2]
RETIRED = {"SaveBackupThread", "create_save_backup", "restore_save_backup",
           "backup_saves", "restore_saves", "start_save_worker",
           "save_worker_finished", "save_worker", "save_backups"}

def test_game_save_feature_has_no_remaining_production_references():
    assert importlib.util.find_spec("services.save_backups") is None
    for name in RETIRED:
        assert not hasattr(GameActionControllerMixin, name), name
        assert not hasattr(game_tasks, name), name
    files = list((ROOT / "src/playdock").rglob("*.py"))
    files += [ROOT / name for name in ("app.py", "title_editor.py", "setup_wizard.py", "uninstall_wizard.py")]
    for path in files:
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"), filename=str(path))):
            names = []
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                names = [node.name]
            elif isinstance(node, ast.Name):
                names = [node.id]
            elif isinstance(node, ast.Attribute):
                names = [node.attr]
            elif isinstance(node, (ast.Import, ast.ImportFrom)):
                names = [a.name.rsplit(".", 1)[-1] for a in node.names]
                if isinstance(node, ast.ImportFrom):
                    names.append((node.module or "").rsplit(".", 1)[-1])
            assert not RETIRED.intersection(names), (path, node.lineno, names)

def test_app_backup_restore_does_not_touch_existing_game_saves(tmp_path):
    store = tmp_path / "data"
    library = Library(store)
    library.save_settings()
    WorkDatabase(store)
    # Existing legacy backup remains on disk, but is not part of app-data export.
    previous = store / "backups" / "saves" / "old.zip"
    previous.parent.mkdir(parents=True)
    with zipfile.ZipFile(previous, "w") as archive:
        archive.writestr("files/slot1.dat", b"legacy save")
    old_bytes = previous.read_bytes()
    game_save = tmp_path / "installed" / "slot1.dat"
    game_save.parent.mkdir()
    game_save.write_bytes(b"current save")
    package = tmp_path / "app-backup.zip"
    assert backup_data(store, [], package) >= 2
    with zipfile.ZipFile(package) as archive:
        names = archive.namelist()
        assert "settings.json" in names
        assert "playdock.db" in names
        assert not any("old.zip" in n or "slot1.dat" in n for n in names)
    restored, safety = restore_data(store, package)
    assert restored >= 2 and safety.is_file()
    assert previous.read_bytes() == old_bytes
    assert game_save.read_bytes() == b"current save"
