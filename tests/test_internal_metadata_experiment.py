"""메타데이터 선택 읽기: 내용 전체 유출/압축풀기 없이 제목 필드만 후보로 사용."""
from __future__ import annotations

import json
import stat
import zipfile

import pytest

from experiments.dlsite_detector.internal_metadata import (
    inspect_metadata, MAX_TOTAL_BYTES, MAX_MEMBER_BYTES,
)
from experiments.dlsite_detector.archive_identity import identify_archive
from experiments.dlsite_detector.pipeline import SearchDecision
from experiments.dlsite_detector.identity_hints import extract_hints
from experiments.dlsite_detector import identify_cli


def make_zip(tmp_path, entries, *, name="Unknown.zip", compression=zipfile.ZIP_STORED):
    archive = tmp_path / name
    with zipfile.ZipFile(archive, "w", compression=compression) as out:
        for path, contents in entries.items():
            if isinstance(contents, zipfile.ZipInfo):
                out.writestr(contents, "Title: Bad Game")
            else:
                out.writestr(path, contents)
    return archive


def missing(query):
    return SearchDecision("lookup_unavailable", query, reason="offline mock")


def verified(query):
    return SearchDecision("internet_candidate", query, proposed_title=query,
                          reason="모의 검증된 검색 후보")


def test_corrected_translation_note_does_not_mean_patch_only():
    for filename in (
        "NOR [한글패치].zip",
        "Night of Revenge [v1.07] [한국어 패치].7z",
        "SummertimeSaga [한국어 패치 Fix2].zip",
    ):
        h = extract_hints(filename)
        assert h.archive_kind == "localized_release_unknown"
        assert "패치 파일로 분류하지 않음" in h.kind_reason
    assert extract_hints("NOR [패치 전용].zip").archive_kind == "patch_candidate"


def test_metadata_finds_rpgmaker_ini_title_without_extracting(tmp_path, monkeypatch):
    path = make_zip(tmp_path, {
        "Game/Game.exe": b"EXE CONTENT",
        "Game/Game.ini": b"[Game]\r\nTitle=Night of Revenge\r\n",
        "Game/README.txt": b"Title: Night of Revenge\n",
    })
    monkeypatch.setattr(zipfile.ZipFile, "extract", lambda *_a, **_k: pytest.fail("extract forbidden"))
    monkeypatch.setattr(zipfile.ZipFile, "extractall", lambda *_a, **_k: pytest.fail("extractall forbidden"))
    before = path.read_bytes()
    r = inspect_metadata(path)
    assert r.state == "ok"
    assert r.title_candidates == ("Night of Revenge",)
    assert any(x.member.endswith("Game.ini") for x in r.evidence)
    assert path.read_bytes() == before


def test_metadata_uses_readme_json_and_renpy_title_fields(tmp_path):
    path = make_zip(tmp_path, {
        "game/README.md": "# Instructions\nGame Title: Midnight Chase\nPassword: 1234",
        "game/metadata.json": json.dumps({
            "title": "Midnight Chase", "api_key": "SECRET_KEY", "password": "private",
            "homepage": "https://localhost/internal"
        }),
        "game/options.rpy": 'define config.name = _("Midnight Chase")\n',
        "random.cfg": b"Title: Ignore This",
    })
    report = inspect_metadata(path)
    assert report.title_candidates == ("Midnight Chase",)
    assert all("SECRET" not in str(x) for x in report.evidence)
    assert not any("private" in str(x) for x in report.evidence)


def test_metadata_rejects_paths_urls_emails_passwords_as_titles(tmp_path):
    path = make_zip(tmp_path, {
        "README.txt": "Game Title: http://example.com\nTitle: C:\\Private\\User\\File\n"
                      "Title: somebody@example.com\nTitle: token=abc\nTitle: Actual Game\n"
    })
    assert inspect_metadata(path).title_candidates == ("Actual Game",)


def test_member_path_traversal_and_symlinks_ignored(tmp_path):
    symlink = zipfile.ZipInfo("Game/README.txt")
    symlink.create_system = 3
    symlink.external_attr = (stat.S_IFLNK | 0o777) << 16
    path = tmp_path / "unsafe.zip"
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("../../README.txt", "Title: Bad Game")
        archive.writestr("C:/README.txt", "Title: Bad Game")
        archive.writestr(symlink, "Title: Bad Game")
        archive.writestr("Game/Game.ini", "[Game]\nTitle=Actual Game\n")
    assert inspect_metadata(path).title_candidates == ("Actual Game",)


def test_bounded_read_skips_large_and_high_ratio_members(tmp_path):
    path = make_zip(tmp_path, {
        "Game/Game.ini": "Title=Small Real Game\n",
        "README.txt": "Title: Bogus Game\n" + "A" * (MAX_MEMBER_BYTES + 100),
    }, compression=zipfile.ZIP_DEFLATED)
    result = inspect_metadata(path)
    assert result.title_candidates == ("Small Real Game",)
    assert result.read_bytes <= MAX_TOTAL_BYTES
    assert result.inspected_files <= 8


def test_7z_does_not_trigger_unsafe_solid_archive_decompression(tmp_path):
    path = tmp_path / "Game.7z"
    path.write_bytes(b"not a valid archive but no content read")
    r = inspect_metadata(path)
    assert r.state == "index_only"
    assert r.read_bytes == 0


def test_metadata_stage_runs_only_when_opted_in_and_prior_search_fails(tmp_path):
    path = make_zip(tmp_path, {
        "data/launcher.exe": b"FAKE EXE",
        "data/game.ini": "[Game]\nTitle=Night of Revenge\n",
    })
    calls = []
    def classify(query):
        calls.append(query)
        return verified(query) if query == "Night of Revenge" else missing(query)

    without = identify_archive(path, classifier=classify)
    assert without.status == "lookup_unavailable"
    assert without.metadata is None
    calls.clear()
    with_metadata = identify_archive(path, classifier=classify, allow_metadata=True)
    assert with_metadata.status == "candidate_found" and with_metadata.stage == 3
    assert with_metadata.proposed_title == "Night of Revenge"
    assert with_metadata.metadata.title_candidates == ("Night of Revenge",)
    assert "Night of Revenge" in calls
    assert with_metadata.to_dict()["metadata"]["state"] == "ok"


def test_metadata_does_not_run_on_confirmed_filename(tmp_path):
    path = make_zip(tmp_path, {"Game/Game.ini": "Title=Another Game"})
    report = identify_archive(
        path, classifier=lambda _: verified("Existing Game"),
        inspector=lambda _: pytest.fail("list must not run"),
        metadata_reader=lambda _: pytest.fail("metadata must not run"),
        allow_metadata=True,
    )
    assert report.stage == 1
    assert report.status == "candidate_found"


def test_metadata_fields_do_not_disclose_raw_readme_to_search(tmp_path):
    path = make_zip(tmp_path, {
        "Game/readme.txt": "Game Title: Example Story\nmy password abc123\n"
                           "API_KEY = abc124\nUSER C:\\Private\n"
    })
    queries = []
    report = identify_archive(
        path, classifier=lambda query: queries.append(query) or missing(query),
        allow_metadata=True,
    )
    assert report.stage == 3
    assert "Example Story" in queries
    assert all("abc123" not in q and "Private" not in q for q in queries)


def test_cli_metadata_optin_offline_does_not_call_search(tmp_path, monkeypatch, capsys):
    path = make_zip(tmp_path, {"Game/Game.ini": "[Game]\nTitle=Sample Game\n"})
    monkeypatch.setattr(identify_cli, "identify_archive",
                        lambda *_a, **_kw: pytest.fail("offline must not query online"))
    assert identify_cli.main([str(path), "--json", "--metadata"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["metadata"]["title_candidates"] == ["Sample Game"]
    assert payload["metadata"]["state"] == "ok"


def test_no_metadata_does_not_run_when_list_gives_one_candidate(tmp_path):
    path = make_zip(tmp_path, {
        "Real Story/Real Story.exe": b"fake",
        "Real Story/Game.ini": "Title=Another Story",
    })
    def classify(query):
        return verified(query) if query == "Real Story" else missing(query)
    r = identify_archive(
        path, classifier=classify, allow_metadata=True,
        metadata_reader=lambda _: pytest.fail("already has index candidate"),
    )
    assert r.status == "candidate_found" and r.stage == 2
