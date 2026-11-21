"""사용자가 선택한 압축파일 이름을 검색기에 안전하게 넘기는 회귀 검사."""
from __future__ import annotations

from unittest.mock import Mock, patch

import pytest

from experiments.dlsite_detector.archive_input import (
    ARCHIVE_SUFFIXES, MAX_BATCH, SearchInput, archive_name, batch_inputs,
    extract_one_code, folder_archive_names, run_lookup, selected_archives,
)
from experiments.dlsite_detector.reverse_lookup import Lookup, Match
from scripts.lookup_window import LookupWindow


@pytest.mark.parametrize("path,expected", [
    (r"C:\\Games\\Star Game [RJ123456].zip", "Star Game [RJ123456].zip"),
    ("/home/user/another game.7z", "another game.7z"),
    (r"D:\\library\\게임A.RAR", "게임A.RAR"),
    ("Z:/folder/one.zip", "one.zip"),
    ("/tmp/private/one.txt", ""),
    ("/tmp/private/one.zip.exe", ""),
    ("", ""),
    ("/tmp/.zip", ""),
])
def test_only_archive_basenames_are_kept(path, expected):
    assert archive_name(path) == expected


def test_multi_file_input_keeps_only_allowed_suffixes():
    selected = selected_archives([
        r"C:\\Private\\First [RJ123456].ZIP",
        r"C:\\Private\\Game Two.7z",
        r"C:\\Private\\Third.rar",
        r"C:\\Private\\do-not-search.txt",
    ])
    assert selected == ("First [RJ123456].ZIP", "Game Two.7z", "Third.rar")
    assert all("Private" not in name for name in selected)


def test_folder_selection_never_opens_archive_contents(tmp_path, monkeypatch):
    (tmp_path / "A.zip").write_bytes(b"not-actually-a-zip")
    (tmp_path / "B.7z").write_bytes(b"not-actually-a-7z")
    (tmp_path / "C.rar").write_bytes(b"not-actually-a-rar")
    (tmp_path / "D.txt").write_bytes(b"not-a-game")
    sub = tmp_path / "sub"
    sub.mkdir()
    (sub / "ignored.zip").write_bytes(b"not-read")
    # If file bytes were read here, this test would fail.
    with patch("pathlib.Path.open", side_effect=AssertionError("archive opened")):
        names = folder_archive_names(str(tmp_path))
    assert names == ("A.zip", "B.7z", "C.rar")


def test_batch_includes_manual_and_selected_files_keeps_order():
    items = batch_inputs("Manual Game\nRJ123456\n", [
        r"C:\\Games\\First.zip", r"D:\\Games\\Second [RJ7654321].rar",
    ])
    assert [i.label for i in items] == [
        "Manual Game", "RJ123456", "First.zip", "Second [RJ7654321].rar",
    ]
    assert [i.origin for i in items] == ["manual", "manual", "archive", "archive"]


def test_batch_supports_129_archives_and_has_explicit_limit():
    items = batch_inputs("", [f"Game {i}.zip" for i in range(129)])
    assert len(items) == 129
    with pytest.raises(ValueError, match="최대"):
        batch_inputs("", [f"Game {i}.zip" for i in range(MAX_BATCH + 1)])


def test_code_extractor_takes_one_code_only():
    assert extract_one_code("Work [rj123456].7z") == ("RJ123456", "")
    assert extract_one_code("Game [RJ123456] [RJ123456].zip") == ("RJ123456", "")
    code, warning = extract_one_code("Game With No Code.zip")
    assert code == "" and "없습니다" in warning
    code, warning = extract_one_code("Game [RJ123456] [RJ654321].rar")
    assert code == "" and "여러" in warning


def test_archive_file_title_to_code_result_maps_original_filename():
    seen = []
    def fake_title_lookup(value):
        seen.append(value)
        return Lookup("title_to_code", "Cleaned Game", "candidates")
    result = run_lookup(SearchInput("Game Name [v1.0].zip", "archive", "Game Name [v1.0].zip"),
                        "title_to_code", title_lookup=fake_title_lookup)
    assert seen == ["Game Name [v1.0].zip"]
    assert result.query == "Game Name [v1.0].zip"
    assert result.input_origin == "archive"


def test_archive_code_to_name_extracts_rj_and_preserves_filename():
    seen = []
    def fake_code_lookup(value):
        seen.append(value)
        return Lookup("code_to_title", value, "confirmed")
    result = run_lookup(SearchInput("Name [RJ123456].zip", "archive", "Name [RJ123456].zip"),
                        "code_to_title", code_lookup=fake_code_lookup)
    assert seen == ["RJ123456"]
    assert result.query == "Name [RJ123456].zip"
    assert result.status == "confirmed"
    assert result.input_origin == "archive"
    assert result.to_dict()["input_origin"] == "archive"


def test_archive_without_code_is_invalid_no_web_call():
    def forbidden(_):
        raise AssertionError("must not perform search without an ID")
    result = run_lookup(SearchInput("No ID.zip", "archive", "No ID.zip"),
                        "code_to_title", code_lookup=forbidden)
    assert result.status == "invalid"
    assert "품번" in result.warnings[0]


def test_manual_code_still_works_as_before():
    result = run_lookup(SearchInput("RJ123456", "manual", "RJ123456"),
                        "code_to_title", code_lookup=lambda value: Lookup(
                            "code_to_title", value, "confirmed"))
    assert result.status == "confirmed"
    assert result.input_origin == "manual"


def test_picker_button_uses_multi_file_dialog():
    fake = Mock()
    fake.busy = False
    with patch("scripts.lookup_window.filedialog.askopenfilenames",
               return_value=(r"C:\\GameDir\\A.zip", r"C:\\GameDir\\B.rar")) as dlg:
        LookupWindow.choose_archives(fake)
    dlg.assert_called_once()
    fake._append_files.assert_called_once_with(("A.zip", "B.rar"))


def test_folder_picker_only_sends_archive_names(tmp_path):
    (tmp_path / "A.zip").write_bytes(b"abc")
    (tmp_path / "B.exe").write_bytes(b"abc")
    fake = Mock()
    fake.busy = False
    with patch("scripts.lookup_window.filedialog.askdirectory", return_value=str(tmp_path)):
        LookupWindow.choose_folder(fake)
    fake._append_files.assert_called_once_with(("A.zip",))
