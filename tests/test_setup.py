import base64
from io import BytesIO
from pathlib import Path
import sys
import pytest
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from setup_paths import normalize_paths, save_folder_settings
from core import Library
import artwork


def test_first_run_wizard_saves_both_paths_and_preserves_existing_values(tmp_path):
    archive = tmp_path / "not_existing_archive_folder"
    game = tmp_path / "not_existing_game_folder"
    settings = tmp_path / "settings.json"
    settings.write_text('{"auto_art":true,"other_setting":42}', encoding="utf-8")
    a, g = save_folder_settings(str(archive), str(game), store_path=settings)
    assert (a, g) == (archive, game)
    assert archive.is_dir() and game.is_dir()
    from core import load_json
    config = load_json(settings)
    assert config["first_run_complete"] is True
    assert config["archives"] == str(archive)
    assert config["library"] == str(game)
    assert config["other_setting"] == 42
    assert config["auto_art"] is False


def test_same_path_rejected(tmp_path):
    with pytest.raises(ValueError):
        normalize_paths(str(tmp_path / "game"), str(tmp_path / "game"))


def test_drive_root_rejected(tmp_path):
    with pytest.raises(ValueError):
        normalize_paths(str(tmp_path.anchor), str(tmp_path / "game"))


def test_existing_file_not_used_as_directory(tmp_path):
    file = tmp_path / "somefile"
    file.write_text("hello")
    with pytest.raises(ValueError):
        normalize_paths(str(file), str(tmp_path / "game"))


def test_no_steam_api_key_supported():
    with pytest.raises(ValueError):
        artwork.get_secret("steamgrid")


def test_ai_image_result_cached_without_steam_api(tmp_path, monkeypatch):
    root = tmp_path / "games"
    root.mkdir()
    archives = tmp_path / "archives"
    archives.mkdir()
    lib = Library(tmp_path / "data")
    lib.change_root(root)
    lib.change_archive_root(archives)
    from core import Game
    game = Game("sample", "Some Game", root)
    img = Image.new("RGB", (192, 128), (60, 120, 200))
    buf = BytesIO()
    img.save(buf, format="PNG")
    image_text = base64.b64encode(buf.getvalue()).decode("ascii")
    calls = []

    def mock_api(url, key, payload, max_bytes=None):
        calls.append((url, payload))
        assert key == "test_key"
        return {"data": [{"b64_json": image_text}]}

    monkeypatch.setattr(artwork, "request_json", mock_api)
    message = artwork.generate_ai_art(lib, game, "test_key")
    assert len(calls) == 2
    assert all("openai.com" in url for url, _ in calls)
    assert (lib.art_dir(game) / "hero.png").is_file()
    assert (lib.art_dir(game) / "icon.png").is_file()
    with Image.open(lib.art_dir(game) / "hero.png") as hero:
        assert hero.size == (1600, 520)
    assert "AI" in message
