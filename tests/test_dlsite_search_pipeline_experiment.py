"""DLsite→인터넷 2단계 판별, 수동 분류, 원본 DB 보존, 이미지 DB 선기록 회귀 테스트.

인터넷·로컬 PlayDock DB·사용자 파일에 접근하지 않는다. 모든 파일은 tmp_path에 생성한다.
"""
from __future__ import annotations

from io import BytesIO
from pathlib import Path
import json
import sqlite3

import pytest
from PIL import Image

from experiments.dlsite_detector.detector import Detection
from experiments.dlsite_detector.pipeline import (
    classify_game, examine_web_results, SearchDecision, WebEvidence,
)
from experiments.dlsite_detector.review_store import ReviewStore
from experiments.dlsite_detector.artwork_staging import ArtworkStaging
from experiments.dlsite_detector import pipeline_cli


def dlsite(status, *, code="RJ01234567", title="테스트 게임"):
    def lookup(_title, *, code="", allow_title_search=False):
        assert allow_title_search
        return Detection(status, _title, code=code or "RJ01234567", work_title=title,
                         work_type="RPG", reason="모의 판정")
    return lookup


def page(site, title="테스트 게임", suffix=""):
    url = {
        "steam": "https://store.steampowered.com/app/1234/test",
        "gog": "https://www.gog.com/en/game/test",
        "itch": "https://a.itch.io/test",
        "moby": "https://www.mobygames.com/game/9999",
        "forum": "https://example.org/forum/test",
    }[site]
    return {"title": title + suffix, "href": url, "body": title + " PC game gameplay review"}


def png(color):
    output = BytesIO()
    Image.new("RGB", (32, 32), color).save(output, format="PNG")
    return output.getvalue()


def test_dlsite_confirmed_game_passes_without_internet():
    result = classify_game(
        "테스트 게임 [RJ01234567]", dlsite_lookup=dlsite("confirmed_game"),
        web_search=lambda _: pytest.fail("DLsite 확인 게임은 인터넷 검색을 하지 않음"))
    assert result.status == "confirmed_game"
    assert result.web_checked is False
    assert result.label.startswith("DLsite 게임 확인")


def test_dlsite_non_game_is_suspected_and_separated_without_internet():
    result = classify_game(
        "음성 작품", dlsite_lookup=dlsite("registered_non_game", title="음성 작품"),
        web_search=lambda _: pytest.fail("DLsite 비게임은 일반 검색을 진행하지 않음"))
    assert result.status == "suspected_non_game"
    assert result.web_checked is False
    assert "추정" in result.label


@pytest.mark.parametrize("status", (
    "registered_type_unknown", "needs_review", "unverified", "lookup_unavailable"))
def test_ambiguous_dlsite_results_go_to_general_internet(status):
    searched = []
    result = classify_game(
        "테스트 게임", dlsite_lookup=dlsite(status),
        web_search=lambda q: searched.append(q) or [page("steam"), page("moby")])
    assert searched == ["테스트 게임"]
    assert result.status == "internet_candidate"
    assert "원문 검증" in result.reason
    assert result.web_checked
    assert len(result.evidence) == 2


def test_web_no_results_becomes_red_unresolved():
    result = classify_game(
        "찾을 수 없는 게임", dlsite_lookup=dlsite("unverified", title="임의 작품"),
        web_search=lambda _: [])
    assert result.status == "lookup_unavailable"
    assert result.web_checked is True
    assert "조회 불가" in result.label
    assert result.proposed_title == ""


def test_web_error_also_goes_to_unresolved():
    result = classify_game(
        "테스트 게임", dlsite_lookup=dlsite("needs_review"),
        web_search=lambda _: (_ for _ in ()).throw(TimeoutError("blocked")))
    assert result.status == "lookup_unavailable"
    assert result.web_checked
    assert "TimeoutError" in result.reason


def test_unrelated_game_or_one_source_cannot_be_auto_confirmed():
    for hits in (
        [page("steam")],
        [page("steam", title="다른 게임"), page("gog", title="다른 게임")],
        [page("forum"), {"title": "테스트 게임", "href": "https://blog.example.org/post", "body": "게임"}],
    ):
        result = classify_game("테스트 게임", dlsite_lookup=dlsite("unverified"),
                               web_search=lambda _, hits=hits: hits)
        assert result.status == "lookup_unavailable"
        assert result.evidence


def test_two_results_from_one_host_not_independent():
    hits = [page("steam"),
            {"title": "테스트 게임 - Steam", "href": "https://store.steampowered.com/app/2000/test",
             "body": "PC game"}]
    result = classify_game("테스트 게임", dlsite_lookup=dlsite("unverified"),
                           web_search=lambda _: hits)
    assert result.status == "lookup_unavailable"


def test_web_evidence_never_trusts_internal_or_insecure_url():
    hits = [
        {"title": "테스트 게임", "href": "http://www.gog.com/game/demo", "body": "game"},
        {"title": "테스트 게임", "href": "https://127.0.0.1/private", "body": "game"},
        {"title": "테스트 게임", "href": "https://localhost/private", "body": "game"},
        {"title": "테스트 게임 - Steam", "href": "https://store.steampowered.com/app/123", "body": "game"},
    ]
    evidence = examine_web_results("테스트 게임", hits)
    assert len(evidence) == 1 and evidence[0].trusted_source


def test_wrong_dlsite_title_does_not_redefine_general_web_query():
    queried = []
    result = classify_game(
        "테스트 게임 [RJ01234567]", dlsite_lookup=dlsite("needs_review", title="완전히 다른 작품"),
        web_search=lambda q: queried.append(q) or [])
    assert queried == ["테스트 게임"]
    assert result.status == "lookup_unavailable"


def test_input_error_does_not_search_web():
    result = classify_game(
        "", dlsite_lookup=dlsite("input_error"),
        web_search=lambda _: pytest.fail("invalid input must not search"))
    assert result.status == "input_error"


def test_db_preserves_original_and_records_before_after_names(tmp_path):
    archive = tmp_path / "Archive Demo.zip"
    archive.write_bytes(b"unchanged archive")
    store = ReviewStore(tmp_path / "test-experiment.db")
    store.add_game("game_01", "원본 이름", archive.name, archive_size=archive.stat().st_size)
    store.add_game("game_01", "다른 입력", "Changed.zip")
    assert store.get_game("game_01")["original_name"] == "원본 이름"
    assert store.get_game("game_01")["original_archive_name"] == archive.name
    change = store.stage_name_change("game_01", "변경한 표시 이름")
    assert store.get_game("game_01")["display_name"] == "원본 이름"
    history = store.name_history("game_01")
    assert history[0]["before_name"] == "원본 이름"
    assert history[0]["after_name"] == "변경한 표시 이름"
    assert history[0]["state"] == "pending"
    store.apply_name_change(change)
    assert store.get_game("game_01")["display_name"] == "변경한 표시 이름"
    restore_id = store.restore_original_name("game_01")
    assert restore_id and store.get_game("game_01")["display_name"] == "원본 이름"
    assert len(store.name_history("game_01")) == 2
    assert archive.read_bytes() == b"unchanged archive"


def test_archive_label_changes_only_db_not_physical_file(tmp_path):
    file = tmp_path / "Original.7z"
    file.write_bytes(b"do not touch")
    store = ReviewStore(tmp_path / "review.db")
    store.add_game("g01", "원본", file.name)
    change = store.stage_name_change("g01", "Renamed.7z", field="archive_label")
    assert store.get_game("g01")["archive_label"] == "Original.7z"
    store.apply_name_change(change)
    assert store.get_game("g01")["archive_label"] == "Renamed.7z"
    assert store.get_game("g01")["original_archive_name"] == "Original.7z"
    assert file.name == "Original.7z" and file.read_bytes() == b"do not touch"
    store.restore_original_name("g01", field="archive_label")
    assert store.get_game("g01")["archive_label"] == "Original.7z"


def test_stale_pending_name_change_blocks_overwrite_and_can_cancel(tmp_path):
    store = ReviewStore(tmp_path / "review.db")
    store.add_game("g01", "원본", "game.zip")
    first = store.stage_name_change("g01", "새 이름")
    with pytest.raises(ValueError, match="처리되지 않은"):
        store.stage_name_change("g01", "또 다른 이름")
    store.cancel_name_change(first)
    with pytest.raises(ValueError):
        store.apply_name_change(first)
    other = store.stage_name_change("g01", "두 번째")
    assert other != first
    with pytest.raises(ValueError):
        store.stage_name_change("g01", "folder/evil", field="archive_label")


def test_status_queues_and_manual_override_survive_auto_refresh(tmp_path):
    db = ReviewStore(tmp_path / "review.db")
    for game_id, title in (("g1", "게임1"), ("g2", "게임2"), ("g3", "게임3")):
        db.add_game(game_id, title, title + ".zip")
    db.save_search_result("g1", SearchDecision("lookup_unavailable", "게임1"))
    db.save_search_result("g2", SearchDecision("suspected_non_game", "게임2"))
    db.save_search_result("g3", SearchDecision("confirmed_game", "게임3"))
    assert [g["game_id"] for g in db.list_unresolved()] == ["g1"]
    assert [g["game_id"] for g in db.list_suspected_non_game()] == ["g2"]
    db.manual_classify("g1", "manual_game", reason="사용자 확인")
    db.manual_classify("g2", "manual_non_game")
    db.save_search_result("g1", SearchDecision(
        "lookup_unavailable", "게임1", evidence=(
            WebEvidence("게임1", "https://example.org", "example.org", True, True, False),
        )))
    g1 = db.get_game("g1")
    assert g1["classification"] == "manual_game"
    assert g1["classification_source"] == "manual"
    assert g1["classification_reason"] == "사용자 확인"
    assert g1["automatic_status"] == "lookup_unavailable"
    assert not db.list_unresolved()
    assert [g["game_id"] for g in db.list_suspected_non_game()] == ["g2"]
    assert len(db.search_history("g1")) == 2
    assert db.search_history("g1")[-1]["evidence"][0]["title"] == "게임1"


def test_image_is_recorded_in_db_before_file_change_then_restored(tmp_path):
    db_path = tmp_path / "review.db"
    root = tmp_path / "preview_cache"
    ReviewStore(db_path).add_game("g1", "원래 이름", "game.zip")
    art = ArtworkStaging(db_path)
    target = root / "g1" / "icon.png"
    target.parent.mkdir(parents=True)
    original = png((255, 0, 0))
    changed = png((0, 0, 255))
    target.write_bytes(original)
    change_id = art.stage_image("g1", "icon", changed, cache_root=root, source="사용자 선택")
    assert target.read_bytes() == original
    assert art.get_change(change_id)["state"] == "pending"
    with sqlite3.connect(db_path) as db:
        before_blob, after_blob = db.execute(
            "SELECT before_image, after_image FROM artwork_changes WHERE id=?", (change_id,)).fetchone()
    assert before_blob == original and after_blob == changed
    art.apply_image(change_id, cache_root=root)
    assert target.read_bytes() == changed
    assert art.get_change(change_id)["state"] == "applied"
    art.restore_image(change_id, cache_root=root)
    assert target.read_bytes() == original
    assert art.get_change(change_id)["state"] == "restored"


def test_new_art_can_be_cancelled_or_removed_by_restore(tmp_path):
    db_path = tmp_path / "review.db"
    root = tmp_path / "cache"
    ReviewStore(db_path).add_game("g1", "원본", "game.zip")
    art = ArtworkStaging(db_path)
    pending = art.stage_image("g1", "hero", png((1, 2, 3)), cache_root=root)
    assert not (root / "g1" / "hero.png").exists()
    art.cancel_image(pending)
    assert not (root / "g1" / "hero.png").exists()
    change = art.stage_image("g1", "hero", png((2, 3, 4)), cache_root=root)
    art.apply_image(change, cache_root=root)
    assert (root / "g1" / "hero.png").is_file()
    art.restore_image(change, cache_root=root)
    assert not (root / "g1" / "hero.png").exists()


def test_image_conflict_blocks_overwrite_without_changing_other_file(tmp_path):
    db_path = tmp_path / "review.db"
    root = tmp_path / "cache"
    ReviewStore(db_path).add_game("g1", "원본", "game.zip")
    art = ArtworkStaging(db_path)
    target = root / "g1" / "icon.png"
    target.parent.mkdir(parents=True)
    target.write_bytes(png((1, 2, 3)))
    request = art.stage_image("g1", "icon", png((2, 3, 4)), cache_root=root)
    external = png((4, 5, 6))
    target.write_bytes(external)
    with pytest.raises(RuntimeError, match="변경"):
        art.apply_image(request, cache_root=root)
    assert target.read_bytes() == external
    assert art.get_change(request)["state"] == "pending"


def test_corrupt_artwork_or_invalid_paths_rejected(tmp_path):
    db_path = tmp_path / "review.db"
    ReviewStore(db_path).add_game("g1", "원본", "game.zip")
    art = ArtworkStaging(db_path)
    with pytest.raises(ValueError):
        art.stage_image("g1", "icon", b"not a PNG", cache_root=tmp_path)
    with pytest.raises(ValueError):
        art.stage_image("../other", "icon", png((1, 2, 3)), cache_root=tmp_path)
    with pytest.raises(ValueError):
        art.stage_image("g1", "other", png((1, 2, 3)), cache_root=tmp_path)


def test_image_crash_recovery_can_finalize_pending_db_state(tmp_path):
    db_path = tmp_path / "review.db"
    root = tmp_path / "cache"
    ReviewStore(db_path).add_game("g1", "원본", "game.zip")
    art = ArtworkStaging(db_path)
    image = png((99, 88, 77))
    change = art.stage_image("g1", "icon", image, cache_root=root)
    target = root / "g1" / "icon.png"
    target.parent.mkdir(parents=True)
    target.write_bytes(image)  # 모의 정전: 파일 반영 후 DB가 아직 pending
    art.apply_image(change, cache_root=root)
    assert art.get_change(change)["state"] == "applied"


def test_manual_cli_queue_and_name_actions(tmp_path, capsys):
    db = tmp_path / "experiment.db"
    store = ReviewStore(db)
    store.add_game("g1", "원본", "archive.zip")
    assert pipeline_cli.main(["--db", str(db), "manual", "--id", "g1",
                              "--status", "manual_non_game"]) == 0
    capsys.readouterr()
    assert pipeline_cli.main(["--db", str(db), "queue", "non-game"]) == 0
    assert json.loads(capsys.readouterr().out)[0]["game_id"] == "g1"
    assert pipeline_cli.main(["--db", str(db), "name-stage", "--id", "g1",
                              "--new", "새 이름"]) == 0
    pending = json.loads(capsys.readouterr().out)["pending_change"]
    assert store.get_game("g1")["display_name"] == "원본"
    assert pipeline_cli.main(["--db", str(db), "name-apply", "--change", str(pending)]) == 0
    capsys.readouterr()
    assert store.get_game("g1")["display_name"] == "새 이름"
    assert pipeline_cli.main(["--db", str(db), "name-restore", "--id", "g1"]) == 0
    capsys.readouterr()
    assert store.get_game("g1")["display_name"] == "원본"


def test_search_pipeline_has_no_core_database_or_qt_imports():
    root = Path(__file__).resolve().parents[1] / "experiments" / "dlsite_detector"
    for name in ("pipeline.py", "review_store.py", "artwork_staging.py", "pipeline_cli.py"):
        source = (root / name).read_text(encoding="utf8")
        for bad in ("from core import", "from ui.", "from controllers.",
                    "from services.", "from database.", "QApplication"):
            assert bad not in source, (name, bad)
