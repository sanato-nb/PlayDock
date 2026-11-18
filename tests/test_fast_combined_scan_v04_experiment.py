"""검증판 v0.4: 파일명 + 내부 근거를 함께 수집하고 제한 횟수로 검색."""
from __future__ import annotations

import sys
import types
import zipfile

from experiments.dlsite_detector import pipeline
from experiments.dlsite_detector.archive_identity import identify_archive
from experiments.dlsite_detector.archive_encryption import EncryptionProbe
from experiments.dlsite_detector.archive_inspector import inspect_archive
from experiments.dlsite_detector.internal_metadata import inspect_metadata
from experiments.dlsite_detector.pipeline import SearchDecision


def _zip(tmp_path, name="Lantern Tale.zip", contents=None):
    path = tmp_path / name
    with zipfile.ZipFile(path, "w") as z:
        for member, payload in (contents or {}).items():
            z.writestr(member, payload)
    return path


def test_combine_filename_and_internal_evidence_before_any_online_call(tmp_path):
    path = _zip(tmp_path, contents={
        "Main/Game.ini": "Title=Silver Quest\n",
        "Main/RealGame.exe": b"binary",
        "Main/game/archive.rpa": b"sample",
    })
    scanned = []
    queries = []
    def inspector(p):
        scanned.append("list")
        return inspect_archive(p)
    def metadata(p):
        scanned.append("metadata")
        return inspect_metadata(p)
    def search(q):
        assert scanned == ["list", "metadata"]
        queries.append(q)
        return SearchDecision("lookup_unavailable", q, reason="no match")
    report = identify_archive(
        path, inspector=inspector, metadata_reader=metadata,
        classifier=search, allow_metadata=True, max_search_queries=3,
    )
    assert scanned == ["list", "metadata"]
    assert "Silver Quest" in queries
    assert "Lantern Tale" in queries
    assert len(queries) <= 3
    assert report.execution_order == (1, 3, 4, 5, 2)


def test_fast_mode_skips_duplicate_dlsite_title_web_query(monkeypatch):
    calls = {"dlsite": [], "web": []}
    def fake_dlsite(name, *, code="", allow_title_search=False):
        calls["dlsite"].append((name, code, allow_title_search))
        return pipeline.Detection("unverified", name)
    def fake_web(query):
        calls["web"].append(query)
        return []
    monkeypatch.setattr(pipeline, "detect_dlsite_game", fake_dlsite)
    monkeypatch.setattr(pipeline, "fast_web_search", fake_web)
    decision = pipeline.fast_classify_game("Silver Quest")
    assert decision.status == "lookup_unavailable"
    assert calls["dlsite"] == [("Silver Quest", "", False)]
    assert len(calls["web"]) == 1


def test_confirmed_id_skips_redundant_weak_name_search(tmp_path):
    path = _zip(tmp_path, "Silver Quest [RJ01234567].zip", {
        "Silver Quest/Silver Quest.exe": b"binary",
        "Silver Quest/game/archive.rpa": b"sample",
    })
    called = []
    def search(q):
        called.append(q)
        if q == "RJ01234567":
            return SearchDecision("confirmed_game", q,
                                  proposed_title="Silver Quest",
                                  dlsite_code="RJ01234567")
        return SearchDecision("lookup_unavailable", q)
    report = identify_archive(path, classifier=search, allow_metadata=True,
                              max_search_queries=3)
    assert called == ["RJ01234567"]
    assert report.proposed_title == "Silver Quest"
    assert report.status == "candidate_found"


def test_prechecked_clear_zip_does_not_probe_three_times(tmp_path, monkeypatch):
    from experiments.dlsite_detector import (
        archive_identity, archive_inspector, internal_metadata,
    )
    path = _zip(tmp_path, contents={"Game/Game.ini": "Title=Silver Quest\n"})
    spy = []
    real_probe = archive_identity.probe_archive_encryption
    def checked(path):
        spy.append(path)
        return real_probe(path)
    def forbidden(*args, **kwargs):
        raise AssertionError("duplicate encrypted-header probe")
    monkeypatch.setattr(archive_identity, "probe_archive_encryption", checked)
    monkeypatch.setattr(archive_inspector, "probe_archive_encryption", forbidden)
    monkeypatch.setattr(internal_metadata, "probe_archive_encryption", forbidden)
    report = identify_archive(path, classifier=lambda q: SearchDecision(
        "lookup_unavailable", q), allow_metadata=True, max_search_queries=1)
    assert report.inspection.state == "ok"
    assert report.metadata.state == "ok"
    assert len(spy) == 1


def test_rar_missing_external_backend_returns_partial_instead_of_crash(
    tmp_path, monkeypatch
):
    # RAR 실행 백엔드가 없는 Windows에서도 JSON 결과는 생성돼야 한다.
    path = tmp_path / "Sample.rar"
    path.write_bytes(b"not a real rar - fake backend only")
    class RarCannotExec(Exception):
        pass
    class Member:
        filename = "Game/Game.ini"
        file_size = 20
        compress_size = 12
        flags = 0
        def needs_password(self):
            return False
        def isdir(self):
            return False
    class FakeRar:
        def __init__(self, *_args, **_kwargs): pass
        def __enter__(self): return self
        def __exit__(self, *_args): return False
        def infolist(self): return [Member()]
        def open(self, *_args): raise RarCannotExec("unrar not installed")
    monkeypatch.setitem(
        sys.modules, "rarfile",
        types.SimpleNamespace(RarFile=FakeRar, RAR_FILE_SOLID=0),
    )
    result = inspect_metadata(path, encryption_probe=EncryptionProbe("clear", ""))
    assert result.state == "partial"
    assert "RarCannotExec" in result.reason


def test_fast_classifier_module_is_explicit_and_not_automatic_binding():
    from experiments.dlsite_detector.enhanced_search import fast_enhanced_classify_game
    from experiments.dlsite_detector.identity_verifier import verify_identity
    assert callable(fast_enhanced_classify_game)
    assert verify_identity.__name__ == "verify_identity"
