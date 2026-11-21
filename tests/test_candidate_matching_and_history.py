"""v6 실사용 결과 재발 방지: DLsite 가나 발음과 수동 후보 이력 분리 검증.

개인 실제 압축 목록을 저장소에 복사하지 않고 합성 제목으로 검증한다.
"""
from pathlib import Path
import json

from experiments.dlsite_detector.candidate_history import CandidateHistory
from experiments.dlsite_detector.detector import Product
from experiments.dlsite_detector.kana_match import phonetic_score, romanized_title
from experiments.dlsite_detector.reverse_lookup import Lookup, Match, _match_score, lookup_title


def product(code, title):
    return Product(code, title, "", "maniax",
                   f"https://www.dlsite.com/maniax/work/=/product_id/{code}.html")


def unavailable(*args):
    raise AssertionError("후순위 검색엔진을 불필요하게 호출하면 안 됨")


def test_kana_phonetics_romanize_not_guess_kanji():
    assert "buzama" in romanized_title("ブザマストリーマーズ -侮挫魔3- [サークル]")
    assert "buzama" not in romanized_title("侮挫魔3")
    assert phonetic_score("BUZAMA 3", "ブザマストリーマーズ -侮挫魔3- [サークル]") == 30


def test_kana_phonetic_number_must_match_and_short_words_never_match():
    assert _match_score("BUZAMA 3", "ブザマストリーマーズ -侮挫魔2-") == 0
    assert _match_score("BUZAMA 2", "ブザマストリーマーズ -侮挫魔3-") == 0
    assert _match_score("NOR", "ノール3") == 0
    assert _match_score("REC", "レック3") == 0


def test_phonetic_match_is_only_review_candidate_not_confirmed():
    code = "RJ123456"
    catalog_rows = [
        {"title": "ブザマストリーマーズ -侮挫魔3- [サークル]",
         "url": f"https://www.dlsite.com/maniax/work/=/product_id/{code}.html"},
        {"title": "全く違う作品",
         "url": "https://www.dlsite.com/maniax/work/=/product_id/RJ654321.html"},
    ]
    result = lookup_title(
        "BUZAMA 3.7z",
        catalog_search=lambda q, shop: catalog_rows if shop == "maniax" else [],
        rss_search=unavailable, meta_search=unavailable,
        external_search=unavailable, engine_search=unavailable,
        fetcher=lambda _: product(code, "ブザマストリーマーズ -侮挫魔3- [サークル]"),
    )
    assert result.status == "candidates"
    assert [m.code for m in result.matches] == [code]
    assert result.matches[0].confidence == "official_code"
    assert result.providers[0]["provider"] == "dlsite_maniax"
    assert len(result.catalog_review) == 2
    assert result.catalog_review[0]["match_score"] == 30
    assert result.catalog_review[1]["match_score"] == 0
    assert "제목/별칭" in result.catalog_review[1]["reason"]


def test_catalog_review_is_saved_when_all_items_rejected():
    result = lookup_title(
        "Example Garden",
        catalog_search=lambda q, cat: [{
            "title": "Entirely different name",
            "url": "https://www.dlsite.com/maniax/work/=/product_id/RJ987654.html",
        }] if cat == "maniax" else [],
        rss_search=lambda _: [], meta_search=lambda _: [],
        engine_search=lambda *args: [], external_search=lambda *args: [],
    )
    assert result.status == "no_candidate"
    record = result.to_dict()
    assert record["catalog_review"][0]["code"] == "RJ987654"
    assert record["catalog_review"][0]["match_score"] == 0


def test_history_saves_candidates_and_recovers_only_as_unverified(tmp_path):
    history = CandidateHistory(tmp_path / "history.json")
    prior = Lookup("title_to_code", "Example Garden [v1.0].7z",
                   "candidates",
                   (Match("RJ123456", "Example Garden", "",
                          "maniax", "official_code", "ddgs_meta"),))
    result = history.merge_and_save(prior)
    assert result.matches[0].confidence == "official_code"
    assert history.path.exists()
    reread = CandidateHistory(history.path)
    failed = Lookup("title_to_code", "Example Garden [v1.3].zip", "no_candidate")
    restored = reread.merge_and_save(failed)
    assert restored.status == "candidates"
    assert len(restored.matches) == 1
    assert restored.matches[0].code == "RJ123456"
    assert restored.matches[0].confidence == "history_candidate"
    assert "이번 실행에서는 다시 확인하지 못함" in restored.matches[0].note
    assert restored.catalog_review == ()


def test_history_never_changes_code_present_or_direct_confirmation(tmp_path):
    history = CandidateHistory(tmp_path / "hist.json")
    history.merge_and_save(Lookup("title_to_code", "Garden",
                                  "candidates", (Match("RJ123456","Japanese","",
                                                       "", "official_code","ddgs_meta"),)))
    direct = Lookup("title_to_code", "Garden [RJ654321].zip", "confirmed",
                    (Match("RJ654321", "Garden", "", "", "filename_code_verified",
                           "dlsite_product_html"),))
    assert history.merge_and_save(direct) == direct
    confirmed = Lookup("title_to_code", "Garden.zip", "confirmed",
                       (Match("RJ654321","Garden","","", "exact_title",
                              "dlsite_product_html"),))
    assert history.merge_and_save(confirmed).matches == confirmed.matches


def test_history_can_import_v6_style_results_without_fabricated_confirmation(tmp_path):
    json_file = tmp_path / "previous.json"
    payload = {"mode": "title_to_code", "results": [
        {"query": "Example Garden [v1.0].7z",
         "matches": [{"code": "RJ123456", "confidence": "official_code",
                      "title": "公式名", "url": "",
                      "category": "maniax"}]},
        {"query": "Other [RJ654321].zip",
         "matches": [{"code": "RJ654321", "confidence": "filename_code_verified"}]},
    ]}
    json_file.write_text(json.dumps(payload), encoding="utf-8")
    h = CandidateHistory(tmp_path / "hist.json")
    assert h.import_export(json_file) == (1, 1)
    h2 = CandidateHistory(h.path)
    res = h2.merge_and_save(Lookup("title_to_code", "Example Garden.zip", "no_candidate"))
    assert res.status == "candidates"
    assert res.matches[0].confidence == "history_candidate"
    assert h2.merge_and_save(Lookup("title_to_code", "Other [RJ654321].zip",
                                    "no_candidate")).matches == ()


def test_history_rejects_unrelated_json_and_corrupted_cache(tmp_path):
    source = tmp_path / "wrong.json"
    source.write_text('{"mode":"code_to_title","results":[]}', encoding="utf-8")
    hist = CandidateHistory(tmp_path / "hist.json")
    try:
        hist.import_export(source)
        assert False, "invalid format must be rejected"
    except ValueError:
        pass
    hist.path.write_text("not-json", encoding="utf-8")
    assert CandidateHistory(hist.path).rows == {}


def test_history_does_not_mark_other_website_as_official_url(tmp_path):
    h = CandidateHistory(tmp_path / "hist.json")
    m = Match("RJ123456", "Garden", "https://evil.example/garden",
              "", "search_candidate", "bing_rss")
    h.merge_and_save(Lookup("title_to_code", "Garden.zip", "candidates", (m,)))
    later = CandidateHistory(h.path).merge_and_save(
        Lookup("title_to_code", "Garden.zip", "no_candidate"))
    assert later.matches[0].url == ""
    assert later.matches[0].source == "local_history"
