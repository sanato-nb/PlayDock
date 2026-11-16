"""DLsite 판별 실험: 실제 인터넷을 사용하지 않는 경계/오분류 회귀 검사."""
from __future__ import annotations

from io import BytesIO
from pathlib import Path
from urllib.error import HTTPError
import json

import pytest

from experiments.dlsite_detector import (
    Product, Detection, LookupUnavailable, detect_dlsite_game,
    parse_product, fetch_product, extract_code, normalized_title,
    product_page_candidate,
)
from experiments.dlsite_detector import cli


GAME_CODE = "RJ01234567"
VOICE_CODE = "RJ01234568"
OTHER_CODE = "RJ01234569"


def product(code=GAME_CODE, title="테스트 게임", work_type="RPG", category="maniax"):
    return Product(
        code, title, work_type, category,
        f"https://www.dlsite.com/{category}/work/=/product_id/{code}.html",
    )


def record(code=GAME_CODE, title="테스트 게임", work_type="RPG"):
    return {"workno": code, "work_name": title, "work_type": work_type}


class Response(BytesIO):
    status = 200

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()


def test_extract_code_and_normalize_preserve_sequel_numbers():
    assert extract_code("C:\\Games\\테스트 게임 [RJ01234567] [v1.20].zip") == GAME_CODE
    assert extract_code("rj01234567") == GAME_CODE
    assert extract_code("XRJ01234567") == ""
    assert normalized_title("C:\\Games\\테스트 게임 [RJ01234567] [v1.20].zip") == normalized_title("테스트 게임")
    assert normalized_title("Demo 2 [v1.3]") != normalized_title("Demo 3")
    assert normalized_title("Game - Extra") != normalized_title("Game 2")
    assert normalized_title("Ｇａｍｅ １") == normalized_title("Game 1")


def test_parse_product_supports_list_keyed_and_data_wrappers():
    expected = product()
    raws = [
        [record()],
        {GAME_CODE: {"work_name": "테스트 게임", "work_type": "RPG"}},
        {"data": {"products": [record()]}},
    ]
    for raw in raws:
        assert parse_product(raw, GAME_CODE, "maniax") == expected


def test_product_parser_rejects_different_code_or_missing_identity():
    assert parse_product([record(OTHER_CODE, "완전히 다른 작품")], GAME_CODE, "maniax") is None
    assert parse_product({"work_name": "코드 없는 유사 작품", "work_type": "RPG"}, GAME_CODE, "maniax") is None
    assert parse_product({GAME_CODE: record(OTHER_CODE, "불일치")}, GAME_CODE, "maniax") is None
    assert parse_product([{"workno": GAME_CODE, "work_name": "***", "work_type": "RPG"}], GAME_CODE, "maniax") is None
    with pytest.raises(ValueError):
        parse_product(record(), "invalid-code", "maniax")
    with pytest.raises(ValueError):
        parse_product(record(), GAME_CODE, "outside")


def test_fetch_product_uses_only_allowed_code_and_work_category():
    seen = []
    def opener(request, *, timeout):
        seen.append((request.full_url, timeout))
        assert request.full_url.startswith("https://www.dlsite.com/maniax/api/=/product.json?")
        assert "workno=RJ01234567" in request.full_url
        return Response(json.dumps({GAME_CODE: record()}, ensure_ascii=False).encode())
    found = fetch_product(GAME_CODE, opener=opener, categories=("maniax",))
    assert found == product()
    assert len(seen) == 1
    with pytest.raises(ValueError):
        fetch_product("invalid", opener=opener)
    with pytest.raises(ValueError):
        fetch_product(GAME_CODE, opener=opener, categories=("localhost",))


def test_404_or_unmatched_response_are_not_proof_of_non_registration():
    def missing(request, *, timeout):
        raise HTTPError(request.full_url, 404, "not found", {}, None)
    assert fetch_product(GAME_CODE, opener=missing, categories=("maniax",)) is None
    def unmatched(request, *, timeout):
        return Response(json.dumps([record(OTHER_CODE)]).encode())
    assert fetch_product(GAME_CODE, opener=unmatched, categories=("maniax",)) is None
    result = detect_dlsite_game(GAME_CODE, fetcher=lambda _: None)
    assert result.status == "unverified"
    assert "미등록이라는 뜻은 아닙니다" in result.reason


def test_403_429_and_broken_json_are_lookup_unavailable_not_negative():
    def forbidden(request, *, timeout):
        raise HTTPError(request.full_url, 403, "forbidden", {}, None)
    with pytest.raises(LookupUnavailable):
        fetch_product(GAME_CODE, opener=forbidden, categories=("maniax",))
    def busy(request, *, timeout):
        raise HTTPError(request.full_url, 429, "slow", {}, None)
    with pytest.raises(LookupUnavailable):
        fetch_product(GAME_CODE, opener=busy, categories=("maniax",))
    def bad_json(request, *, timeout):
        return Response(b"<html>restricted</html>")
    with pytest.raises(LookupUnavailable):
        fetch_product(GAME_CODE, opener=bad_json, categories=("maniax",))
    result = detect_dlsite_game(GAME_CODE, fetcher=lambda _: (_ for _ in ()).throw(LookupUnavailable("blocked")))
    assert result.status == "lookup_unavailable"


def test_confirmed_game_requires_real_product_code_and_game_work_type():
    game = detect_dlsite_game("테스트 게임 [RJ01234567].zip", fetcher=lambda _: product())
    assert game.status == "confirmed_game"
    assert game.work_type == "RPG"
    assert game.title_match is True
    assert game.page_url.endswith(f"{GAME_CODE}.html")
    assert game.code_origin == "filename_code"
    assert game.label == "DLsite 등록 게임 확인"
    assert game.to_dict()["label"] == game.label


def test_code_only_query_can_confirm_dlsite_work_type():
    result = detect_dlsite_game(GAME_CODE, fetcher=lambda _: product())
    assert result.status == "confirmed_game"
    assert result.title_match is None
    assert result.code == GAME_CODE


def test_non_game_codes_do_not_become_dlsite_games():
    for form in ("SOU", "ICG", "MNG", "SCM", "MOV"):
        actual = detect_dlsite_game(
            "테스트 게임", code=VOICE_CODE,
            fetcher=lambda _: product(VOICE_CODE, "음성 작품", form),
        )
        assert actual.status == "registered_non_game", form
        assert actual.code == VOICE_CODE


def test_unknown_work_type_is_not_claimed_to_be_a_game():
    for form in ("", "ETC", "MYSTERY"):
        result = detect_dlsite_game("테스트 게임", code=GAME_CODE,
                                    fetcher=lambda _: product(work_type=form))
        assert result.status == "registered_type_unknown", form


def test_code_of_other_game_is_marked_for_manual_review():
    item = detect_dlsite_game(
        "다른 게임 [RJ01234567].zip", fetcher=lambda _: product(),
    )
    assert item.status == "needs_review"
    assert item.title_match is False
    assert item.code == GAME_CODE
    wrong = detect_dlsite_game("테스트 게임", code=GAME_CODE,
                               fetcher=lambda _: product(OTHER_CODE))
    assert wrong.status == "unverified"


def test_title_search_only_uses_official_https_product_links():
    yes = f"https://www.dlsite.com/maniax/work/=/product_id/{GAME_CODE}.html"
    assert product_page_candidate(yes) == (GAME_CODE, "maniax")
    for raw in (
        f"https://fake-dlsite.com/maniax/work/=/product_id/{GAME_CODE}.html",
        f"http://www.dlsite.com/maniax/work/=/product_id/{GAME_CODE}.html",
        f"https://www.dlsite.com.evil.org/maniax/work/=/product_id/{GAME_CODE}.html",
        f"https://user:pass@www.dlsite.com/maniax/work/=/product_id/{GAME_CODE}.html",
        "https://www.dlsite.com/maniax/",
        f"https://example.org/?url={yes}",
    ):
        assert product_page_candidate(raw) is None


def test_no_code_title_search_verifies_original_product_json():
    searched = []
    official_link = f"https://www.dlsite.com/maniax/work/=/product_id/{GAME_CODE}.html"
    def searcher(value):
        searched.append(value)
        return [{"title": "비공식 검색 결과", "href": official_link}]
    def fetcher(code):
        assert code == GAME_CODE
        return product()
    outcome = detect_dlsite_game("C:\\Private\\테스트 게임.zip",
                                 allow_title_search=True, searcher=searcher, fetcher=fetcher)
    assert searched == ["테스트 게임"]
    assert outcome.status == "confirmed_game"
    assert outcome.code_origin == "title_search"
    assert outcome.title_match is True


def test_title_search_does_not_auto_assign_a_similar_but_different_game():
    official_link = f"https://www.dlsite.com/home/work/=/product_id/{GAME_CODE}.html"
    result = detect_dlsite_game(
        "테스트 게임 2", allow_title_search=True,
        searcher=lambda _: [{"href": official_link}],
        fetcher=lambda _: product(),
    )
    assert result.status == "needs_review"
    assert result.title_match is False


def test_ambiguous_title_candidates_are_not_auto_assigned():
    links = [
        {"href": f"https://www.dlsite.com/home/work/=/product_id/{code}.html"}
        for code in (GAME_CODE, OTHER_CODE)
    ]
    result = detect_dlsite_game(
        "테스트 게임", allow_title_search=True, searcher=lambda _: links,
        fetcher=lambda code: product(code=code),
    )
    assert result.status == "needs_review"
    assert result.possible_codes == (GAME_CODE, OTHER_CODE)


def test_no_search_evidence_does_not_mean_not_on_dlsite():
    result = detect_dlsite_game("출처 미확인 게임", allow_title_search=True,
                                searcher=lambda _: [], fetcher=lambda _: pytest.fail("no code"))
    assert result.status == "unverified"
    result2 = detect_dlsite_game("코드 없는 게임", allow_title_search=False,
                                 searcher=lambda _: pytest.fail("do not search"))
    assert result2.status == "unverified"
    blocked = detect_dlsite_game("다른 게임", allow_title_search=True,
                                 searcher=lambda _: (_ for _ in ()).throw(TimeoutError()))
    assert blocked.status == "lookup_unavailable"


def test_invalid_code_and_empty_input_do_not_trigger_network():
    def forbidden(*_):
        pytest.fail("should not make HTTP requests")
    assert detect_dlsite_game("", fetcher=forbidden).status == "input_error"
    assert detect_dlsite_game("테스트 게임", code="RJbad", fetcher=forbidden).status == "input_error"
    assert detect_dlsite_game("게임 이름", allow_title_search=False, fetcher=forbidden).status == "unverified"


def test_cli_offline_default_makes_no_requests(monkeypatch, capsys):
    monkeypatch.setattr(cli, "detect_dlsite_game", lambda *_a, **_kw: pytest.fail("network must not run"))
    exit_code = cli.main(["테스트 게임 [RJ01234567]", "--json"])
    payload = json.loads(capsys.readouterr().out)
    assert exit_code == 1
    assert payload["status"] == "unverified"
    assert payload["code"] == GAME_CODE
    assert "오프라인" in payload["reason"]


def test_standalone_module_imports_no_playdock_or_ui_components():
    source = (Path(__file__).resolve().parents[1] / "experiments" / "dlsite_detector" / "detector.py").read_text(encoding="utf-8")
    for forbidden in (
        "from core import", "from services.", "from ui.", "from controllers.",
        "from database.", "QApplication", "QWidget", "update_meta(",
        "save_json(", "open('", 'open("',
    ):
        assert forbidden not in source
