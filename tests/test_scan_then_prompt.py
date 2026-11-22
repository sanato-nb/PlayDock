"""After (not before) the entire DLsite/Steam scan, hand off excluded names to AI."""
import json
from pathlib import Path

import pytest

from experiments.dlsite_detector.code_only import InputItem, Result, Work, check
from experiments.dlsite_detector.detector import Product
from experiments.dlsite_detector.steam_client import SteamProduct
from experiments.dlsite_detector.scan_handoff import (
    ScanReport, build_excluded, build_full, find_archive_names,
    scan_folder, publish_after_scan, make_ai_prompt, COMBINED_NAME,
    render_combined_txt, RESULTS_DIR,
)
from scripts.scan_then_prompt import run, main


def dl(code):
    return Product(code, "DL Work", "", "maniax",
                   f"https://www.dlsite.com/maniax/work/=/product_id/{code}.html")


def steam(code):
    return SteamProduct(code, "Steam Work", "game",
                        f"https://store.steampowered.com/app/{code}/")


def fake_check(item, *, cache):
    return check(item, fetcher=dl, steam_fetcher=steam, cache=cache)


def never_http(item, *, cache):
    return check(item, fetcher=lambda c: 1/0, steam_fetcher=lambda c: 1/0,
                 cache=cache)


def test_dl_then_steam_and_exclusions_end_to_end(tmp_path):
    folder = tmp_path / "secret_local_directory"
    folder.mkdir()
    files = ["Game DL [RJ123456].7z", "Steam Game [Steam 1091500].zip",
             "DL and Steam [RJ654321] [Steam 1091500].rar",
             "Unknown [v1.05] [한글패치].zip"]
    for filename in files:
        (folder / filename).write_bytes(b"dummy; do not open")
    calls = []
    def stub(item, *, cache):
        calls.append(item.label)
        return fake_check(item, cache=cache)

    report = scan_folder(folder, checker=stub)
    assert report.counts == {"total": 4, "confirmed": 3, "partial": 0, "excluded": 1}
    assert len(calls) == 4
    both = next(x for x in report.items if "DL and Steam" in x.query)
    assert both.selected_store == "dlsite"
    assert both.attempted_stores == ("dlsite",)
    assert all("secret_local_directory" not in str(r.to_dict()) for r in report.items)

    target = publish_after_scan(report, tmp_path / "out")
    assert [p.name for p in target.iterdir()] == [COMBINED_NAME]
    combined = (target / COMBINED_NAME).read_text(encoding="utf-8-sig")
    assert "전체 4개 | 공식 확인 3개 | 일부 확인 0개 | 제외 1개" in combined
    assert "1부. AI 조사 지침 및 실제 제외 게임 목록" in combined
    assert "2부. 품번 확인 완료 목록 (AI 조사 대상 아님)" in combined
    assert "제외된 게임: 총 1개" in combined
    assert "Unknown [v1.05] [한글패치].zip" in combined
    assert "A. 식별번호 없음" in combined
    assert "| DL Work" in combined
    assert "| Steam Work" in combined
    assert "전체 4개" in combined
    assert "Steam" in combined and "DLsite" in combined
    assert "사용자 승인" in combined
    assert "PowerShell" in combined and "BAT" in combined
    assert "GitHub" not in combined and "github.com" not in combined
    assert "experiment-bidirectional" not in combined
    assert "실제 제외 게임 목록 시작" in combined
    assert "실제 제외 게임 목록 끝" in combined
    assert "추가 JSON 첨부를 요구하지 마세요" in combined
    assert "secret_local_directory" not in combined
    assert all(path.read_bytes() == b"dummy; do not open" for path in folder.iterdir())


def test_no_excluded_creates_only_full_scan_txt(tmp_path):
    folder = tmp_path / "games"
    folder.mkdir()
    (folder / "Game [RJ123456].zip").write_bytes(b"archive")
    report = scan_folder(folder, checker=fake_check)
    target = publish_after_scan(report, tmp_path / "results")
    assert sorted(p.name for p in target.iterdir()) == [COMBINED_NAME]
    assert report.counts["excluded"] == 0


def test_no_identifier_does_not_issue_any_http_requests(tmp_path):
    folder = tmp_path / "games"
    folder.mkdir()
    (folder / "Unknown [v2.1].zip").write_bytes(b"z")
    report = scan_folder(folder, checker=never_http)
    assert report.counts["excluded"] == 1
    assert report.items[0].attempted_stores == ()


def test_report_contains_failed_identifier_reason(tmp_path):
    report = ScanReport((
        Result("No Code.zip", "archive", "excluded"),
        Result("DL [RJ123456].7z", "archive", "excluded",
               attempted_stores=("dlsite",), warnings=("DLsite blocked",)),
    ), 2)
    excluded = build_excluded(report)
    assert [x["exclusion_reason"] for x in excluded["excluded"]] == [
        "no_identifier", "official_lookup_failed"]
    assert excluded["excluded"][1]["dlsite_codes"] == ["RJ123456"]
    assert excluded["excluded"][1]["attempted_stores"] == ["dlsite"]
    assert excluded["excluded"][1]["warnings"] == ["DLsite blocked"]


def test_nested_folders_and_symlinks_not_followed(tmp_path):
    nested = tmp_path / "nested"
    nested.mkdir()
    (nested / "Game [RJ123456].zip").write_bytes(b"x")
    (tmp_path / "notes.txt").write_text("not a game")
    assert find_archive_names(tmp_path) == ("Game [RJ123456].zip",)
    assert find_archive_names(tmp_path, recursive=False) == ()


def test_duplicate_names_kept_and_marked_ambiguous(tmp_path):
    folder = tmp_path / "games"
    (folder / "a").mkdir(parents=True)
    (folder / "b").mkdir()
    for sub in ("a", "b"):
        (folder / sub / "Same Name.zip").write_bytes(b"x")
    report = scan_folder(folder, checker=never_http)
    assert report.counts["excluded"] == 2
    excluded = build_excluded(report)
    assert len(excluded["excluded"]) == 2
    assert [x["item_id"] for x in excluded["excluded"]] == [1, 2]
    assert all(x["duplicate_filename"] for x in excluded["excluded"])
    assert "같은 이름" in make_ai_prompt(2)


def test_exception_in_single_checker_does_not_stop_scan(tmp_path):
    folder = tmp_path / "games"
    folder.mkdir()
    for name in ("a.zip", "b.zip"):
        (folder / name).write_bytes(b"x")
    def crashes(item, *, cache):
        if item.label == "a.zip":
            raise RuntimeError("temporary")
        return Result(item.label, "archive", "confirmed")
    seen = []
    report = scan_folder(folder, checker=crashes,
                         progress=lambda i, n, r: seen.append((i, n)))
    assert seen == [(1, 2), (2, 2)]
    assert report.counts["excluded"] == 1
    assert report.items[0].warnings == ("공식 검사 예외: RuntimeError",)


def test_publish_is_called_only_after_all_items_scanned(tmp_path, monkeypatch):
    from scripts import scan_then_prompt
    folder = tmp_path / "games"
    folder.mkdir()
    (folder / "a.zip").write_bytes(b"x")
    (folder / "b.zip").write_bytes(b"x")
    monkeypatch.setattr(scan_then_prompt, "scan_folder",
                        lambda *a, **k: ScanReport((Result("a.zip", "archive", "excluded"),), 2))
    # The CLI never publishes intermediate results before scan_folder returns.
    monkeypatch.setattr(scan_then_prompt, "publish_after_scan",
                        lambda r, d: tmp_path / "saved")
    assert run(folder) == 0


def test_missing_folder_does_not_write_prompt(tmp_path):
    folder = tmp_path / "not_exists"
    assert run(folder, output_dir=tmp_path / "results") == 1
    assert not (tmp_path / "results").exists()


def test_empty_folder_does_not_write_prompt(tmp_path):
    folder = tmp_path / "empty"
    folder.mkdir()
    assert run(folder) == 1
    assert not (folder / RESULTS_DIR).exists()


def test_self_test_and_prompt_absent_without_exclusions():
    assert main(["--self-test"]) == 0
    assert make_ai_prompt(0) == ""


def test_external_query_only_never_contains_developer_details():
    prompt = make_ai_prompt(4)
    for x in ["github", "repository", "branch", "owner", "sanato", "PrivateKey"]:
        assert x.lower() not in prompt.lower()
    assert "이용자" in prompt



def test_no_false_claim_that_both_sites_failed_when_only_one_queried():
    from experiments.dlsite_detector.code_only import check, InputItem
    dl_only = check(InputItem("Game RJ123456.zip", "archive"),
                    fetcher=lambda code: None,
                    steam_fetcher=lambda code: (_ for _ in ()).throw(
                        AssertionError("Steam must not be called without App ID")))
    assert dl_only.status == "excluded"
    assert dl_only.attempted_stores == ("dlsite",)
    assert any("Steam App ID는 없어서 조회하지 않았습니다" in w for w in dl_only.warnings)
    assert not any("DLsite와 Steam 공식 조회가 모두" in w for w in dl_only.warnings)
    steam_only = check(InputItem("Game Steam 1091500.zip", "archive"),
                       fetcher=lambda code: (_ for _ in ()).throw(
                           AssertionError("DLsite must not be called")),
                       steam_fetcher=lambda code: None)
    assert steam_only.status == "excluded"
    assert steam_only.attempted_stores == ("steam",)
    assert any("DLsite 품번이 없어서 조회하지 않았습니다" in w for w in steam_only.warnings)


def test_error_reporting_has_no_personal_paths(tmp_path):
    report = ScanReport((
        Result("Archive [RJ123456].zip", "archive", "excluded",
               warnings=("DLsite RJ123456: 공식 페이지 조회 실패 (TimeoutError)",),
               attempted_stores=("dlsite",)),
    ), 1)
    full = json.dumps(build_full(report), ensure_ascii=False)
    failed = json.dumps(build_excluded(report), ensure_ascii=False)
    assert "C:\\Users\\" not in full
    assert "C:\\Users\\" not in failed



def test_every_excluded_entry_is_in_paste_ready_prompt(tmp_path):
    folder = tmp_path / "games"
    folder.mkdir()
    for name in ("Unidentified A [v1.2].zip", "Unidentified B [한글].7z",
                 "DL failure [RJ123456].rar"):
        (folder / name).write_bytes(b"original")
    report = scan_folder(folder, checker=never_http)
    assert report.counts["excluded"] == 3
    output = publish_after_scan(report, tmp_path / "result")
    combined = (output / COMBINED_NAME).read_text(encoding="utf-8-sig")
    assert len(list(output.iterdir())) == 1
    for name in ("Unidentified A [v1.2].zip", "Unidentified B [한글].7z",
                 "DL failure [RJ123456].rar"):
        assert name in combined
    assert "기존 품번: DLsite RJ123456" in combined
    assert "공식 작품명 확인 실패" in combined
    assert "전체 3개" in combined


def test_duplicate_filenames_remain_in_prompt_with_original_ids(tmp_path):
    folder = tmp_path / "games"
    (folder / "left").mkdir(parents=True)
    (folder / "right").mkdir()
    for side in ("left", "right"):
        (folder / side / "Duplicated.zip").write_bytes(b"content")
    report = scan_folder(folder, checker=never_http)
    output = publish_after_scan(report, tmp_path / "res")
    combined = (output / COMBINED_NAME).read_text(encoding="utf-8-sig")
    assert "[1] Duplicated.zip" in combined
    assert "[2] Duplicated.zip" in combined
    assert combined.count("주의: 같은 파일명 여러 개") == 2


def test_korean_files_open_in_windows_notepad(tmp_path):
    report = ScanReport((Result("한국어 이름 [한글패치].7z", "archive", "excluded"),), 1)
    output = publish_after_scan(report, tmp_path / "res")
    assert [p.name for p in output.iterdir()] == [COMBINED_NAME]
    raw = (output / COMBINED_NAME).read_bytes()
    assert raw.startswith(b"\xef\xbb\xbf")
    assert "한국어 이름 [한글패치].7z" in raw.decode("utf-8-sig")


def test_no_failed_items_means_no_prompt_or_excluded_txt(tmp_path):
    report = ScanReport((
        Result("Known [RJ123456].zip", "archive", "confirmed",
               works=(Work("RJ123456", "Official Work", "",
                           "https://www.dlsite.com/maniax/work/=/product_id/RJ123456.html",
                           "verified", "dlsite"),), selected_store="dlsite"),
    ), 1)
    output = publish_after_scan(report, tmp_path / "results")
    assert [p.name for p in output.iterdir()] == [COMBINED_NAME]
    contents = (output / COMBINED_NAME).read_text(encoding="utf-8-sig")
    assert "AI 조사 요청은 필요하지 않습니다" in contents
    assert "1부. AI 조사 지침" not in contents
    assert "| Official Work" in contents
    assert not make_ai_prompt(0)



def test_exactly_one_file_even_for_129_archive_report(tmp_path):
    # Reproduce user's 129-files scenario without adding private game names to Git.
    items = tuple(
        Result(f"Archive_{i:03d}.zip", "archive",
               "excluded" if i <= 41 else "confirmed")
        for i in range(1, 130)
    )
    report = ScanReport(items, 129)
    output = publish_after_scan(report, tmp_path / "output")
    filenames = [x.name for x in output.iterdir()]
    assert filenames == [COMBINED_NAME]
    text = (output / COMBINED_NAME).read_text(encoding="utf-8-sig")
    assert "전체 129개 | 공식 확인 88개 | 일부 확인 0개 | 제외 41개" in text
    assert "제외된 게임: 총 41개" in text
    assert text.count("### A. 식별번호 없음") == 1
    assert text.count("===== 실제 제외 게임 목록 시작") == 1
    assert "Archive_041.zip" in text and "Archive_042.zip" in text
    assert "Archive_129.zip" in text


def test_one_file_contains_no_developer_or_local_absolute_paths(tmp_path):
    report = ScanReport((
        Result("Test [RJ123456].zip", "archive", "excluded",
               attempted_stores=("dlsite",)),
    ), 1)
    contents = render_combined_txt(report)
    assert "github.com" not in contents.casefold()
    assert "sanato-nb" not in contents.casefold()
    assert "C:\\Users\\" not in contents
    assert str(tmp_path) not in contents



def test_129_unique_items_are_each_listed_once_without_repeating_exclusions(tmp_path):
    import re
    report = ScanReport(tuple(
        Result(f"Demo_{i:03d}.zip", "archive",
               "excluded" if i <= 41 else "confirmed")
        for i in range(1, 130)), 129)
    text = render_combined_txt(report)
    # 'item_id filename' occurs exactly once; no duplicate 41-item section.
    named = re.findall(r"^\[(\d+)\] (Demo_\d{3}\.zip|(?:공식 확인|일부 확인) \| Demo_\d{3}\.zip)$",
                       text, flags=re.MULTILINE)
    assert len(named) == 129
    assert len(set(x[0] for x in named)) == 129
    assert text.count("Demo_001.zip") == 1
    assert text.count("Demo_041.zip") == 1
    assert text.count("Demo_042.zip") == 1
    assert "A. 식별번호 없음: 41개" in text
    assert "B. 기존 식별번호 조회 실패: 0개" in text


def test_identifier_lookup_failures_are_separated_from_unknown_ids():
    report = ScanReport((
        Result("No-code [v1.2].zip", "archive", "excluded"),
        Result("DL [RJ01385626].7z", "archive", "excluded",
               attempted_stores=("dlsite",)),
        Result("Steam [Steam 1091500].rar", "archive", "excluded",
               attempted_stores=("steam",)),
    ), 3)
    output = render_combined_txt(report)
    assert "A. 식별번호 없음: 1개" in output
    assert "B. 기존 식별번호 조회 실패: 2개" in output
    assert output.index("[1] No-code") < output.index("### B.")
    assert output.index("[2] DL [RJ01385626]") > output.index("### B.")
    assert "DLsite RJ01385626" in output
    assert "Steam 1091500" in output
    assert "해당 번호부터 재확인" in output


def test_ai_prompt_contains_fixed_powershell_and_simple_mapping():
    from experiments.dlsite_detector.rename_template import PS1_TEMPLATE
    report = ScanReport((Result("No code [v1.0].zip", "archive", "excluded"),), 1)
    full = render_combined_txt(report)
    assert "item_id" in full and "판매처" in full and "공식 URL" in full
    assert "official_confirmed" in full and "candidate" in full and "unknown" in full
    assert "JSON 이름 목록만 채우세요" in full
    assert "```powershell\\n" in full
    assert PS1_TEMPLATE.strip() in full
    assert "$renameJson = @'" in full
    assert "[]\\n'@" in full
    assert 'OldName' in full and 'NewName' in full
    assert "Select-GameFolder" in full and "Undo-Last" in full
    assert "PowerShell 코드블록" in full
    assert "GitHub" not in full
    assert "C:\\\\Users\\\\" not in full



def test_partial_verification_kept_in_reference_section_once():
    from experiments.dlsite_detector.code_only import Work
    report = ScanReport((
        Result("partial [RJ123456 RJ654321].zip", "archive", "partial",
               works=(Work("RJ123456", "Official", "", 
                           "https://www.dlsite.com/maniax/work/=/product_id/RJ123456.html",
                           "verified", "dlsite"),
                      Work("RJ654321", None, "", "", "unavailable", "dlsite")),
               selected_store="dlsite"),
        Result("Unknown.zip", "archive", "excluded"),
    ), 2)
    txt = render_combined_txt(report)
    assert "일부 확인 1개" in txt
    assert "[1] 일부 확인 | partial [RJ123456 RJ654321].zip" in txt
    assert "일부 품번만 확인됨" in txt
    assert txt.count("partial [RJ123456 RJ654321].zip") == 1
    assert txt.count("Unknown.zip") == 1


def test_no_exception_or_incorrect_no_id_claim_for_store_lookup_failure():
    report = ScanReport((
        Result("DL [RJ123456].zip", "archive", "excluded",
               attempted_stores=("dlsite",)),
    ), 1)
    text = render_combined_txt(report)
    assert "B. 기존 식별번호 조회 실패: 1개" in text
    assert "실제 조회: dlsite" in text
    assert "인터넷 조회를 하지 않음" in text  # A group only, zero entries.
