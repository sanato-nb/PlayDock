"""품번 전용 검색의 핵심 계약: 품번 없으면 인터넷 요청 0, 잘못된 작품번호 거절."""
import json

import pytest

from experiments.dlsite_detector.code_only import (
    InputItem, Work, archive_name, selected_archives,
    folder_archives, inputs, codes_in, check,
)
from experiments.dlsite_detector.detector import Product


def product(code: str, *, returned_code=None) -> Product:
    return Product(returned_code or code, "Example Work", "", "maniax",
                   f"https://www.dlsite.com/maniax/work/=/product_id/{code}.html")


def never(*args):
    raise AssertionError("품번이 없으면 사이트를 절대 조회하면 안 됨")


@pytest.mark.parametrize("name", [
    "My Game.zip", "Game Title [v1.2].7z", "구글 검색 작품.rar",
    "random 12345678.zip", "only[123456].zip", "RJ12345.zip",
])
def test_no_code_never_uses_internet(name):
    result = check(InputItem(name, "archive"), fetcher=never)
    assert result.status == "excluded"
    assert not result.works
    assert "없어 제외" in result.warnings[0]


def test_code_found_verifies_official_title_only():
    calls = []
    def fetch(code):
        calls.append(code)
        return product(code)
    result = check(InputItem("Game Title [RJ01234567] [v1.0].7z", "archive"),
                   fetcher=fetch)
    assert calls == ["RJ01234567"]
    assert result.status == "confirmed"
    assert result.works[0].title == "Example Work"
    assert result.works[0].url.endswith("RJ01234567.html")
    assert result.works[0].status == "verified"
    assert result.input_origin == "archive"


def test_multiple_codes_fetch_individually_without_guessing():
    calls = []
    def fetch(code):
        calls.append(code)
        return product(code)
    result = check(InputItem("Game [RJ123456] + DLC [RJ654321].zip", "archive"),
                   fetcher=fetch)
    assert calls == ["RJ123456", "RJ654321"]
    assert result.status == "confirmed"
    assert [w.code for w in result.works] == calls


def test_duplicate_code_across_archive_inputs_is_cached():
    calls = []
    def fetch(code):
        calls.append(code)
        return product(code)
    cache = {}
    first = check(InputItem("Game [RJ123456].zip", "archive"),
                  fetcher=fetch, cache=cache)
    next_ = check(InputItem("Game (2) RJ123456.7z", "archive"),
                  fetcher=fetch, cache=cache)
    assert calls == ["RJ123456"]
    assert first.works == next_.works


def test_wrong_official_code_not_verified():
    result = check(InputItem("RJ123456", "manual"),
                   fetcher=lambda code: product(code, returned_code="RJ654321"))
    assert result.status == "excluded"
    assert result.works[0].title == ""


def test_fetch_exception_cannot_be_claimed_not_registered():
    result = check(InputItem("RJ123456", "manual"),
                   fetcher=lambda code: 1 / 0)
    assert result.status == "excluded"
    assert result.works[0].status == "unavailable"
    assert any("ZeroDivisionError" in x for x in result.warnings)
    assert any("미등록 판정은 아닙니다" in x for x in result.warnings)


def test_partial_multiple_codes_are_distinct():
    result = check(InputItem("RJ123456, RJ654321", "manual"),
                   fetcher=lambda c: product(c) if c == "RJ123456" else None)
    assert result.status == "partial"
    assert [r.status for r in result.works] == ["verified", "unavailable"]


def test_directory_list_only_top_level_not_archive_contents(tmp_path):
    (tmp_path / "Game [RJ123456].zip").write_bytes(b"")
    (tmp_path / "other.txt").write_text("RJ654321", encoding="utf-8")
    nested = tmp_path / "nested"
    nested.mkdir()
    (nested / "Hidden [RJ654321].7z").write_bytes(b"")
    assert folder_archives(str(tmp_path)) == ("Game [RJ123456].zip",)
    assert selected_archives([
        r"C:\Users\Private\Game [RJ123456].zip",
        "/tmp/Other [BJ123456].rar", "/tmp/no.txt",
    ]) == ("Game [RJ123456].zip", "Other [BJ123456].rar")


def test_extracted_codes_are_exact_with_casefold_and_dedup():
    assert codes_in("RJ123456 - rj123456 - BJ01234567 - VJ123456 - EJ123456") == (
        "RJ123456", "BJ01234567", "VJ123456", "EJ123456")
    assert codes_in("RJ12345 RJ123456789 A_RJ123456abc") == ()


def test_inputs_preserve_filename_and_limit_and_no_absolute_paths():
    rows = inputs("RJ123456\nRJ654321", [r"C:\Users\Secret\title [RJ987654].zip"])
    assert len(rows) == 3
    assert rows[2].label == "title [RJ987654].zip"
    assert "Secret" not in str(rows)
    with pytest.raises(ValueError):
        inputs("\n".join("RJ123456" for _ in range(1001)), [])


def test_json_structure_is_file_based_and_serializable():
    result = check(InputItem("foo [RJ123456].zip", "archive"),
                   fetcher=lambda code: product(code))
    data = json.loads(json.dumps(result.to_dict(), ensure_ascii=False))
    assert data["query"] == "foo [RJ123456].zip"
    assert data["works"][0]["code"] == "RJ123456"


def test_reject_non_official_product_url():
    result = check(InputItem("RJ123456", "manual"),
                   fetcher=lambda code: Product(code, "Fake", "", "maniax",
                           "https://fake.example/work/=/product_id/RJ123456.html"))
    assert result.status == "excluded"


def test_static_ui_does_not_import_legacy_title_search():
    from pathlib import Path
    source = Path(__file__).resolve().parents[1] / "scripts" / "code_only_window.py"
    text = source.read_text(encoding="utf-8")
    assert "lookup_title(" not in text
    assert "search_bing_rss" not in text
    assert "search_meta_no_key" not in text
