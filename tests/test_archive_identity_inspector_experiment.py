"""압축파일을 풀지 않고 내부 디렉터리 목록으로 게임 식별 단서만 찾는 실험 검사."""
from __future__ import annotations

import json
import sys
import types
import zipfile

import pytest

from experiments.dlsite_detector import archive_inspector as inspector


def make_zip(path, names):
    with zipfile.ZipFile(path, "w") as z:
        for name in names:
            z.writestr(name, b"dummy-content")
    return path


def test_zip_list_evidence_without_reading_any_member(tmp_path, monkeypatch):
    archive = make_zip(tmp_path / "사용자 파일.zip", [
        "찾아야할 게임/찾아야할 게임.exe",
        "찾아야할 게임/찾아야할 게임_Data/globalgamemanagers",
        "찾아야할 게임/docs/readme.txt",
        "찾아야할 게임/RJ01081508.txt",
    ])
    original = archive.read_bytes()
    monkeypatch.setattr(zipfile.ZipFile, "extract", lambda *_a, **_k: pytest.fail("extract forbidden"))
    monkeypatch.setattr(zipfile.ZipFile, "extractall", lambda *_a, **_k: pytest.fail("extractall forbidden"))
    monkeypatch.setattr(zipfile.ZipFile, "open", lambda *_a, **_k: pytest.fail("member read forbidden"))
    result = inspector.inspect_archive(archive)
    assert result.format == "zip"
    assert result.state == "ok"
    assert result.member_count == 4
    assert result.total_uncompressed_bytes == 4 * len(b"dummy-content")
    assert "찾아야할 게임" in result.title_candidates
    assert "RJ01081508" in result.product_codes
    assert "Unity" in result.engine_hints
    assert any("EXE" in row.reason for row in result.evidence)
    assert archive.read_bytes() == original
    assert result.to_dict()["archive_name"] == "사용자 파일.zip"


def test_generic_launchers_do_not_become_game_name(tmp_path):
    archive = make_zip(tmp_path / "unknown.zip", [
        "game.exe", "launcher.exe", "UnityCrashHandler64.exe",
        "Data/file.bin", "Setup.exe", "nw.exe",
    ])
    result = inspector.inspect_archive(archive)
    assert result.title_candidates == ()
    assert result.product_codes == ()


def test_renpy_rpgmaker_and_godot_are_engine_hints_only(tmp_path):
    archive = make_zip(tmp_path / "Game.zip", [
        "Project/renpy/common/00library.rpy",
        "Project/game/archive.rpa",
        "Project/Game.rgss3a",
        "Project/data.pck",
    ])
    result = inspector.inspect_archive(archive)
    assert "Ren'Py" in result.engine_hints
    assert "RPG Maker" in result.engine_hints
    assert "Godot (추정)" in result.engine_hints
    assert "확정하지 않았습니다" in result.reason


def test_traversal_unsafe_names_ignored(tmp_path):
    archive = make_zip(tmp_path / "unsafe.zip", [
        "../../RJ99999999.exe",
        "C:\\secrets\\RJ11111111.exe",
        "/tmp/RJ33333333.exe",
        "safe/RJ01081508.txt",
    ])
    result = inspector.inspect_archive(archive)
    assert result.state == "partial"
    assert result.listed_count == 1
    assert result.product_codes == ("RJ01081508",)
    assert all("RJ999" not in e.path for e in result.evidence)


def test_member_limit_stops_scanning_without_extracting(tmp_path, monkeypatch):
    archive = make_zip(tmp_path / "many.zip", ["one/a.exe", "two/b.exe", "three/c.exe"])
    monkeypatch.setattr(inspector, "MAX_MEMBERS", 2)
    result = inspector.inspect_archive(archive)
    assert result.state == "limit_exceeded"
    assert result.listed_count == 2
    assert "항목 제한" in result.reason


def test_corrupt_and_missing_archive_do_not_raise(tmp_path):
    broken = tmp_path / "broken.zip"
    broken.write_bytes(b"not zip data")
    assert inspector.inspect_archive(broken).state == "unavailable"
    assert inspector.inspect_archive(tmp_path / "missing.7z").state == "unavailable"
    assert inspector.inspect_archive(tmp_path / "installer.exe").state == "unsupported"


def test_7z_archive_uses_metadata_list_only(tmp_path, monkeypatch):
    archive = tmp_path / "demo.7z"
    archive.write_bytes(b"dummy")
    class Seven:
        def __init__(self, _path, mode):
            assert mode == "r"
        def __enter__(self):
            return self
        def __exit__(self, *_):
            return False
        def needs_password(self):
            return False
        def list(self):
            return [
                types.SimpleNamespace(filename="My Demo/My Demo.exe",
                                      uncompressed=321, is_directory=False),
                types.SimpleNamespace(filename="My Demo/game/archive.rpa",
                                      uncompressed=987, is_directory=False),
            ]
        def extract(self, **_):
            pytest.fail("7z extraction forbidden")
        def extractall(self, **_):
            pytest.fail("7z extraction forbidden")
    monkeypatch.setitem(sys.modules, "py7zr", types.SimpleNamespace(SevenZipFile=Seven))
    result = inspector.inspect_archive(archive)
    assert result.member_count == 2
    assert result.total_uncompressed_bytes == 1308
    assert "My Demo" in result.title_candidates
    assert "Ren'Py" in result.engine_hints


def test_rar_archive_uses_metadata_list_only(tmp_path, monkeypatch):
    archive = tmp_path / "demo.rar"
    archive.write_bytes(b"dummy")
    class Rar:
        def __init__(self, _path):
            pass
        def __enter__(self):
            return self
        def __exit__(self, *_):
            return False
        def needs_password(self):
            return False
        def infolist(self):
            return [
                types.SimpleNamespace(filename="Example/Example.exe",
                                      file_size=200, isdir=lambda: False),
                types.SimpleNamespace(filename="Example/README.txt",
                                      file_size=20, isdir=lambda: False),
            ]
        def open(self, *_):
            pytest.fail("RAR payload read forbidden")
    monkeypatch.setitem(sys.modules, "rarfile", types.SimpleNamespace(RarFile=Rar))
    result = inspector.inspect_archive(archive)
    assert result.state == "ok"
    assert result.member_count == 2
    assert "Example" in result.title_candidates


def test_encrypted_header_is_reported_as_password_required(tmp_path, monkeypatch):
    archive = tmp_path / "encrypted.7z"
    archive.write_bytes(b"dummy")
    class Seven:
        def __init__(self, *_a, **_kw):
            raise RuntimeError("password required")
    monkeypatch.setitem(sys.modules, "py7zr", types.SimpleNamespace(SevenZipFile=Seven))
    result = inspector.inspect_archive(archive)
    assert result.state == "encrypted"
    assert result.encrypted is True
    assert result.evidence == ()


def test_no_internet_no_database_no_content_extraction():
    import inspect
    source = inspect.getsource(inspector)
    forbidden = ("from core import", "from services.", "from ui.", "from database.",
                 "ddgs", "urlopen(", "extractall(", "zf.extract(", "rf.open(",
                 "zf.open(", "sqlite3", "write_bytes(", "read_bytes(")
    for word in forbidden:
        assert word not in source, word
