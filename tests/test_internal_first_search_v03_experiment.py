"""압축 안 증거를 먼저 모으는 검색 0.3버전 통합 회귀 검사.

실제 사용자 파일명/경로를 저장하지 않는 완전 합성 압축 샘플만 사용한다.
"""
from __future__ import annotations

from dataclasses import replace
import json
import zipfile

from experiments.dlsite_detector.archive_identity import identify_archive
from experiments.dlsite_detector.archive_inspector import inspect_archive
from experiments.dlsite_detector.identity_verifier import verify_identity
from experiments.dlsite_detector.internal_metadata import inspect_metadata
from experiments.dlsite_detector.pipeline import SearchDecision
from experiments.dlsite_detector.search_plan import build_search_plan


def game_zip(tmp_path, name="Local Story.zip", rows=None):
    path = tmp_path / name
    with zipfile.ZipFile(path, "w") as zf:
        for member, data in (rows or {}).items():
            zf.writestr(member, data)
    return path


def missing(query):
    return SearchDecision("lookup_unavailable", query, reason="정체 찾지 못함")


def official(query):
    return SearchDecision(
        "confirmed_game", query,
        proposed_title="Solar Chamber", dlsite_code="RJ01234567",
    )


def test_internal_index_and_metadata_are_collected_before_first_online_query(tmp_path):
    path=game_zip(tmp_path, rows={
        "Solar Chamber/Solar Chamber.exe": b"test binary",
        "Solar Chamber/Solar Chamber_Data/globalgamemanagers": b"game data",
        "Solar Chamber/Solar Chamber_Data/app.info": "Studio Name\nSolar Chamber\n",
        "Solar Chamber/steam_appid.txt": "123456\n",
    })
    visited=[]
    def index(p):
        visited.append("list")
        return inspect_archive(p)
    def metadata(p):
        visited.append("metadata")
        return inspect_metadata(p)
    def classifier(query):
        assert visited[:2] == ["list", "metadata"]
        visited.append("internet:" + query)
        return missing(query)
    r=identify_archive(path, classifier=classifier, inspector=index,
                       metadata_reader=metadata, allow_metadata=True)
    assert visited[:2] == ["list", "metadata"]
    assert visited[2].startswith("internet:")
    assert r.execution_order == (1,3,4,5,2)
    assert r.completed_steps == (1,2,3,4,5)
    assert path.read_bytes() == path.read_bytes()


def test_codes_before_titles_and_duplicate_code_queried_once(tmp_path):
    path=game_zip(tmp_path, name="Cosmic Story [RJ01234567].zip",rows={
        "RJ01234567/Game.ini": "Title=Cosmic Story\nWork_No=RJ01234567\n",
        "RJ01234567/Cosmic Story.exe": b"sample",
    })
    index=inspect_archive(path)
    metadata=inspect_metadata(path)
    plan=build_search_plan(path.name,index,metadata)
    assert plan[0].query=="RJ01234567"
    assert sum(v.query=="RJ01234567" for v in plan)==1
    assert "Cosmic Story" in [v.query for v in plan]
    assert plan[0].stage == 3


def test_helper_translator_and_common_folders_are_not_external_game_queries(tmp_path):
    path=game_zip(tmp_path, rows={
        "Common/BepInEx/plugins/XUnity.AutoTranslator/Translators/FullNET/ezTransXP.ExtProtocol.exe": b"x",
        "Common/notification_helper.exe": b"x",
        "Common/locales/ko.pak": b"x",
        "Common/swiftshader/libEGL.dll": b"x",
        "Moonfall/Moonfall.exe": b"game",
        "Moonfall/Moonfall_Data/boot.config": b"config",
    })
    index=inspect_archive(path)
    assert "Moonfall" in index.title_candidates
    assert not any("notification" in value.casefold() for value in index.title_candidates)
    plan=build_search_plan(path.name,index,None)
    queries=[x.query.casefold() for x in plan]
    assert "moonfall" in queries
    assert all("locales" not in q and "eztransxp" not in q
               and "notification" not in q and "swiftshader" not in q
               for q in queries)


def test_simple_korean_named_exe_can_be_review_candidate_without_web_result(tmp_path):
    path=game_zip(tmp_path,name="별빛의 전설 [v1.0].zip", rows={
        "별빛의 전설.exe": b"test",
        "package.nw": b"fake nw package",
        "notification_helper.exe": b"helper",
    })
    r=identify_archive(path,classifier=missing,allow_metadata=True)
    ver=verify_identity(r)
    assert r.status=="lookup_unavailable"
    assert "별빛의 전설" in ver.candidate_titles
    assert ver.verdict=="needs_review"
    assert ver.package_assessment=="game_payload_candidate"
    assert not ver.automatic_binding_allowed


def test_unity_default_project_name_is_not_a_conflict(tmp_path):
    path=game_zip(tmp_path,name="Solar Chamber [RJ01234567].zip",rows={
        "Solar Chamber.exe": b"test",
        "Solar Chamber_Data/app.info": "Studio Name\nNTR Game\n",
        "Solar Chamber_Data/globalgamemanagers": b"game",
    })
    def external(query):
        return official(query) if query=="RJ01234567" else missing(query)
    r=identify_archive(path,classifier=external,allow_metadata=True,metadata_reader=inspect_metadata)
    assert r.metadata.title_candidates == ()
    assert any(e.kind=="project_name" and e.strength=="weak"
               for e in r.metadata.evidence)
    assert verify_identity(r).verdict != "conflict"


def test_official_bilingual_title_and_short_native_title_are_not_conflict(tmp_path):
    path=game_zip(tmp_path,name="세나 이야기 [RJ01234567].zip",rows={
        "PROJECT/Game.exe": b"test",
        "PROJECT/Game_Data/app.info": "Studio\n星のセナ\n",
        "PROJECT/Game_Data/globalgamemanagers": b"game",
    })
    def external(query):
        return SearchDecision(
            "confirmed_game", query, dlsite_code="RJ01234567",
            proposed_title="星のセナ - Star Sena -",
        ) if query=="RJ01234567" else missing(query)
    report=identify_archive(path,classifier=external,allow_metadata=True,metadata_reader=inspect_metadata)
    ver=verify_identity(report)
    assert ver.verdict in {"likely_candidate","needs_review"}
    assert ver.verdict != "conflict"
    assert ver.comparison[0].strong_title_matches == ("星のセナ",)


def test_different_same_platform_id_is_still_hard_conflict(tmp_path):
    path=game_zip(tmp_path,name="Solar Chamber [RJ01234567].zip",rows={
        "Game/Game.ini": "Title=Solar Chamber\nWork_No=RJ01234568\n",
        "Game/Game.exe": b"test",
    })
    def official_for_code(query):
        if query=="RJ01234567":
            return official(query)
        return missing(query)
    r=identify_archive(path,classifier=official_for_code,allow_metadata=True,metadata_reader=inspect_metadata)
    ver=verify_identity(r)
    assert ver.verdict=="conflict"
    assert "same_platform_official_id_conflict" in ver.matched_rules


def test_search_runtime_error_is_not_no_game_verdict(tmp_path):
    path=game_zip(tmp_path,name="Local Story.zip",rows={
        "Local Story/Local Story.exe": b"sample",
    })
    def blocked(_query):
        raise RuntimeError("network temporarily unavailable")
    report=identify_archive(path,classifier=blocked,allow_metadata=False)
    verify=verify_identity(report)
    assert verify.verdict=="needs_review"
    assert "Local Story" in verify.candidate_titles
    assert report.to_dict()["search_errors"]
    assert any("검색 서비스 오류" in text for text in verify.limitations)


def test_no_external_search_before_local_probes_for_encrypted_archive(tmp_path):
    import zipfile
    path=tmp_path/"Encrypted Story.zip"
    with zipfile.ZipFile(path,"w") as zf:
        zf.writestr("Game/Secret.exe", b"safe")
    # zipfile has no encrypted writer. Use a legacy ZIP member bit flag mutation
    # on local test data: fake the encrypted flag in both headers.
    raw=bytearray(path.read_bytes())
    idx=raw.index(b"PK\x03\x04")
    flags=int.from_bytes(raw[idx+6:idx+8],"little") | 1
    raw[idx+6:idx+8]=flags.to_bytes(2,"little")
    idx=raw.index(b"PK\x01\x02")
    flags=int.from_bytes(raw[idx+8:idx+10],"little") | 1
    raw[idx+8:idx+10]=flags.to_bytes(2,"little")
    path.write_bytes(raw)
    called=[]
    def classifier(q):
        called.append(q)
        return missing(q)
    report=identify_archive(
        path,classifier=classifier,
        inspector=lambda *_: (_ for _ in ()).throw(
            AssertionError("encrypted archive must not inspect members")),
        metadata_reader=lambda *_: (_ for _ in ()).throw(
            AssertionError("encrypted archive must not inspect metadata")),
        allow_metadata=True,
    )
    assert len(called)==1
    assert called[0]=="Encrypted Story"
    assert report.status=="unclassifiable"
    assert report.execution_order==(1,3,2)
