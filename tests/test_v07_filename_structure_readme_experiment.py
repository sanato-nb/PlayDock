"""v0.7 기본 판독: 내부 구조·목록 중심, README 명시 필드만 제한적으로 읽기."""
from __future__ import annotations

import hashlib
import zipfile

from experiments.dlsite_detector.archive_identity import identify_archive
from experiments.dlsite_detector.archive_inspector import inspect_archive
from experiments.dlsite_detector.internal_metadata import inspect_readme_metadata
from experiments.dlsite_detector.pipeline import SearchDecision
from experiments.dlsite_detector.search_plan import build_search_plan


def make_zip(tmp_path, name, files):
    path = tmp_path / name
    with zipfile.ZipFile(path, "w") as arc:
        for member, content in files.items():
            arc.writestr(member, content)
    return path


def test_member_names_without_reading_engine_settings(tmp_path, monkeypatch):
    archive = make_zip(tmp_path, "Sea of Paper.zip", {
        "PaperSea/PaperSea.exe": b"fake exe",
        "PaperSea/PaperSea_Data/app.info": b"Studio\nHidden Secret Project\n",
        "PaperSea/game.ini": b"Title=Other Secret Title\n",
        "PaperSea/data/System.json": b'{"gameTitle": "Private Title"}',
        "PaperSea/package.json": b'{"window":{"title":"Another"}}',
        "PaperSea/README.txt": b"Game Title: Sea of Paper\nPassword: Do Not Use\n",
    })
    before = hashlib.sha256(archive.read_bytes()).hexdigest()
    opened = []
    actual_open = zipfile.ZipFile.open

    def guarded_open(self, member, *a, **kw):
        path = str(member)
        opened.append(path)
        assert path.lower().endswith("readme.txt")
        return actual_open(self, member, *a, **kw)

    monkeypatch.setattr(zipfile.ZipFile, "open", guarded_open)
    queries = []

    def classifier(q):
        assert opened == ["PaperSea/README.txt"]
        queries.append(q)
        return SearchDecision("lookup_unavailable", q, search_state="not_found")

    result = identify_archive(archive, classifier=classifier, allow_metadata=True,
                              max_search_queries=3)
    assert "Sea of Paper" in queries
    assert result.metadata.title_candidates == ("Sea of Paper",)
    assert "PaperSea" in result.inspection.title_candidates
    assert all("Secret" not in q and "Private" not in q for q in queries)
    assert hashlib.sha256(archive.read_bytes()).hexdigest() == before


def test_missing_readme_does_not_read_any_member(tmp_path, monkeypatch):
    archive = make_zip(tmp_path, "Hidden Isle.zip", {
        "HiddenIsle/HiddenIsle.exe": b"x",
        "HiddenIsle/game.json": b'{"gameTitle":"DoNotRead"}',
    })
    monkeypatch.setattr(zipfile.ZipFile, "open",
                        lambda *a, **kw: (_ for _ in ()).throw(
                            AssertionError("index only: no member read")))
    report = identify_archive(
        archive, classifier=lambda q: SearchDecision("lookup_unavailable", q),
        allow_metadata=True,
    )
    assert report.metadata.inspected_files == 0
    assert report.metadata.read_bytes == 0
    assert report.inspection.state == "ok"


def test_filename_query_survives_code_priority_and_official_early_hit(tmp_path):
    archive = make_zip(tmp_path, "Summer Island.zip", {
        "RJ09999991/game.pak": b"x",
        "RJ09999992/plugin.dll": b"x",
        "RJ09999993/sound.dll": b"x",
        "Summer Island/Summer Island.exe": b"x",
    })
    plan = build_search_plan(archive.name, inspect_archive(archive), None,
                             max_queries=3)
    assert len(plan) == 3
    assert any(h.query == "Summer Island" for h in plan)
    observed = []

    def classifier(q):
        observed.append(q)
        if q == "RJ09999991":
            return SearchDecision("confirmed_game", q, proposed_title="Summer Island",
                                  dlsite_code="RJ09999991")
        return SearchDecision("lookup_unavailable", q, search_state="not_found")

    identify_archive(archive, classifier=classifier,
                     allow_metadata=True, max_search_queries=3)
    assert "Summer Island" in observed


def test_readme_labeled_fields_only_and_legacy_reader_is_explicit(tmp_path):
    from experiments.dlsite_detector.internal_metadata import inspect_metadata
    archive = make_zip(tmp_path, "Space Lantern.zip", {
        "Space Lantern/game.ini": b"Title=Unwanted INI Title",
        "Space Lantern/README.md": (
            "Game Title: Space Lantern\n품번: RJ09999990\n"
            "Password: hidden-secret\nRandom rumor: Outer Galaxy"
        ).encode("utf-8"),
    })
    basic = inspect_readme_metadata(archive)
    assert basic.title_candidates == ("Space Lantern",)
    assert basic.product_codes == ("RJ09999990",)
    assert all("hidden-secret" not in e.candidate_title
               for e in basic.evidence)
    legacy = inspect_metadata(archive)
    assert "Unwanted INI Title" in legacy.title_candidates



def test_windows_self_test_matches_v07_readme_only_policy():
    from scripts.game_identity_tester import self_test
    assert self_test() == 0
