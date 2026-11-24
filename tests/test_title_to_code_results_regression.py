"""PlayDock 실제 사용자 JSON 결과에서 드러난 검색 문제를 합성 데이터로 회귀 검증.

개인 압축파일 목록·작품명·테스트 원문은 저장소에 포함하지 않는다.
"""
from __future__ import annotations

from experiments.dlsite_detector.detector import Product
from experiments.dlsite_detector.reverse_lookup import Lookup, lookup_title


def product(code, title="作品名（日本語）"):
    return Product(
        code, title, "", "maniax",
        f"https://www.dlsite.com/maniax/work/=/product_id/{code}.html",
    )


def forbidden(*_):
    raise AssertionError("품번이 이미 있으므로 이름 검색을 호출하면 안 됩니다")


def test_archived_name_with_rj_uses_code_html_directly_instead_of_web_search():
    calls = []
    def get(code):
        calls.append(code)
        return product(code)
    result = lookup_title(
        "Korean Translated Name [v1.02] [RJ01234567].zip",
        catalog_search=forbidden, external_search=forbidden,
        engine_search=forbidden, fetcher=get,
    )
    assert calls == ["RJ01234567"]
    assert result.status == "confirmed"
    assert result.matches[0].code == "RJ01234567"
    assert result.matches[0].title == "作品名（日本語）"
    assert result.matches[0].confidence == "filename_code_verified"
    assert not result.providers


def test_code_only_archive_no_longer_returns_invalid():
    result = lookup_title(
        "RJ123456.zip", catalog_search=forbidden,
        external_search=forbidden, engine_search=forbidden,
        fetcher=lambda code: product(code),
    )
    assert result.status == "confirmed"
    assert result.matches[0].code == "RJ123456"


def test_valid_code_but_unreachable_html_keeps_only_explicit_file_claim():
    result = lookup_title(
        "Title [RJ123456].zip", catalog_search=forbidden,
        external_search=forbidden, engine_search=forbidden,
        fetcher=lambda code: None,
    )
    assert result.status == "candidates"
    assert result.matches[0].confidence == "filename_code_only"
    assert result.matches[0].code == "RJ123456"
    assert "검증된 것은 아닙니다" in " ".join(result.warnings)


def test_fetch_error_preserves_code_as_unverified_instead_of_search_error():
    def blocked(_):
        raise OSError("blocked")
    result = lookup_title(
        "Local name [VJ009876].7z", catalog_search=forbidden,
        external_search=forbidden, engine_search=forbidden,
        fetcher=blocked,
    )
    assert result.status == "candidates"
    assert result.matches[0].code == "VJ009876"
    assert result.matches[0].source == "archive_filename"


def test_mismatched_official_code_cannot_override_known_file_code():
    result = lookup_title(
        "Local [RJ123456].rar", catalog_search=forbidden,
        external_search=forbidden, engine_search=forbidden,
        fetcher=lambda code: product("RJ654321"),
    )
    assert result.status == "candidates"
    assert result.matches[0].code == "RJ123456"
    assert result.matches[0].confidence == "filename_code_only"


def test_same_code_repeated_once_and_two_distinct_codes_not_auto_resolved():
    one = lookup_title(
        "Game [RJ123456] [RJ123456].zip", catalog_search=forbidden,
        external_search=forbidden, engine_search=forbidden,
        fetcher=lambda code: product(code),
    )
    assert one.status == "confirmed" and len(one.matches) == 1
    two = lookup_title(
        "Game [RJ123456] [VJ654321].zip", catalog_search=forbidden,
        external_search=forbidden, engine_search=forbidden,
        fetcher=lambda code: product(code),
    )
    assert two.status == "candidates" and len(two.matches) == 2
    assert any("여러 DLsite" in v for v in two.warnings)


def test_short_name_does_not_accept_unrelated_vendor_or_menu_items():
    link = "https://www.dlsite.com/maniax/work/=/product_id/RJ789012.html"
    results = [{"title": "Unrelated Product [NOR]", "url": link}]
    result = lookup_title(
        "NOR [Korean Patch].zip",
        catalog_search=lambda title, category: results if category == "maniax" else [],
        external_search=forbidden, engine_search=forbidden,
        fetcher=lambda code: product(code, title="Unrelated Product [NOR]"),
    )
    assert result.status == "no_candidate"
    assert not result.matches


def test_unrelated_official_url_cannot_claim_title_to_code_confirmed():
    link = "https://www.dlsite.com/maniax/work/=/product_id/RJ789012.html"
    result = lookup_title(
        "A Completely Different Game.zip",
        catalog_search=lambda name, category: ([{"title":"Other Game", "url":link}]
                                               if category=="maniax" else []),
        external_search=forbidden, engine_search=forbidden,
        fetcher=lambda code: product(code, title="Another Title"),
    )
    assert result.status == "no_candidate"
    assert not result.matches


def test_valid_long_name_still_gets_candidate_when_heading_relevant():
    link = "https://www.dlsite.com/maniax/work/=/product_id/RJ123456.html"
    result = lookup_title(
        "Adventure Garden.zip",
        catalog_search=lambda name, category: ([{"title":"Adventure Garden [Studio]", "url":link}]
                                               if category=="maniax" else []),
        external_search=forbidden, engine_search=forbidden,
        fetcher=lambda code: product(code, "Adventure Garden [Studio]"),
    )
    assert result.status == "candidates"
    assert result.matches[0].code == "RJ123456"


def test_official_search_all_blocked_is_unavailable_even_if_bing_empty():
    def fail(*args):
        raise RuntimeError("access blocked")
    result = lookup_title(
        "Garden Adventure",
        catalog_search=fail,
        engine_search=lambda *args: [],
        external_search=fail,
    )
    assert result.status == "unavailable"
    assert len(result.providers) == 8
    assert any("공식 DLsite 검색이 모두 실패" in w for w in result.warnings)
