"""캐시·백업·모음집의 UI/Controller/Service 분리 회귀 검사."""
import ast
import json
from pathlib import Path
from types import SimpleNamespace

from cache_management import image_stats as old_stats, recycle_images as old_recycle
from data_management import backup_data as old_backup, _data_paths
from services.cache_service import CacheService, image_stats, recycle_images
from services.data_service import backup_data, inspect_backup
from controllers.data_manager import DataManagementController
from storage.collections import CollectionStore


ROOT = Path(__file__).resolve().parents[1]


def test_legacy_facades_use_real_service_functions():
    assert old_stats is image_stats
    assert old_recycle is recycle_images
    assert old_backup is backup_data
    assert callable(_data_paths)


def test_cache_service_only_recycles_known_images_and_keeps_metadata(tmp_path):
    cache = tmp_path / "cache"
    folder = cache / ("a" * 22)
    folder.mkdir(parents=True)
    (folder / "meta.json").write_text('{"title":"keep"}', encoding="utf-8")
    (folder / "hero.png").write_bytes(b"hero")
    (folder / "icon.png").write_bytes(b"icon")
    (cache / "outside").mkdir()
    (cache / "outside" / "hero.png").write_bytes(b"outside")
    service = CacheService(cache)
    assert service.image_stats().files == 2
    moved = []
    def fake_recycle(raw_path):
        path = Path(raw_path)
        moved.append(path.name)
        path.unlink()
    result = service.recycle_images(recycle=fake_recycle)
    assert result.files == 2
    assert set(moved) == {"hero.png", "icon.png"}
    assert (folder / "meta.json").is_file()
    assert (cache / "outside" / "hero.png").read_bytes() == b"outside"


def test_controller_manages_collection_actions_without_changing_game_files(tmp_path):
    store = tmp_path / "data"
    store.mkdir()
    archive = tmp_path / "game.zip"
    archive.write_bytes(b"unchanged")
    calls = []
    owner = SimpleNamespace(
        library=SimpleNamespace(store=store, cache=store / "cache"),
        collections=CollectionStore(store), games=[],
        reload=lambda: calls.append("reload"),
        refresh_all_data=lambda: calls.append("refresh_all_data"),
    )
    actions = DataManagementController(owner)
    actions.create_collection("RPG")
    collection = actions.list_collections()[0]
    actions.rename_collection(collection["id"], "모음집")
    assert actions.list_collections()[0]["name"] == "모음집"
    actions.delete_collection(collection["id"])
    assert actions.list_collections() == []
    assert calls == ["reload", "reload", "reload"]
    assert archive.read_bytes() == b"unchanged"


def test_backup_controller_preserves_files_and_calls_reload_only_after_restore(tmp_path):
    store = tmp_path / "data"
    store.mkdir()
    (store / "settings.json").write_text('{"library":"original"}', encoding="utf-8")
    calls = []
    owner = SimpleNamespace(
        library=SimpleNamespace(store=store, cache=store / "cache"),
        collections=CollectionStore(store), games=[],
        reload=lambda: calls.append("reload"),
        refresh_all_data=lambda: calls.append("refresh_all_data"),
    )
    actions = DataManagementController(owner)
    archive = tmp_path / "backup.zip"
    assert actions.export_backup(archive) >= 1
    assert "settings.json" in actions.inspect_backup(archive)
    (store / "settings.json").write_text('{"library":"modified"}', encoding="utf-8")
    restored, safety = actions.restore_backup(archive)
    assert restored >= 1 and safety.is_file()
    assert json.loads((store / "settings.json").read_text(encoding="utf-8"))["library"] == "original"
    assert calls == ["refresh_all_data"]


def test_data_dialog_uses_injected_actions_not_direct_file_service_calls():
    source = "\n".join((ROOT / "src/playdock/ui/dialogs" / name).read_text(encoding="utf-8") for name in ("data_manager.py", "cache_manager.py"))
    ast.parse(source)
    assert "self.actions = parent.data_actions" in source
    assert "self.actions.export_backup(target)" in source
    assert "self.actions.restore_backup(Path(selected))" in source
    assert "self.actions.recycle_images(ids)" in source
    for direct in ("from data_management import", "from cache_management import"):
        assert direct not in source
