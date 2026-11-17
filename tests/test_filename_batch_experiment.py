"""PowerShell ls 목록 일괄 검사 CLI의 오프라인·개인정보 보호 검증."""
from __future__ import annotations

import json
import zipfile

from experiments.dlsite_detector import filename_batch as batch


EXAMPLE = """Windows PowerShell 5.1
Mode LastWriteTime Length Name
-a----      2025-11-29   오전 1:52       83208768 6월의 너와 나 [한국어].7z
-a----      2026-07-14   오후 11:25      728133329 Craft to Exile 2 [Server v1.1.3].zip
-a----      2026-01-03   오전 3:12     1853748345 Eliminator 카에데씨 [v1.2] [RJ209760·Steam 1122
                                                  040].7z
-a----      2025-11-29   오전 12:32     3708641822 도나도나 같이 나쁜 짓을 하자 (Donha Donha) [v1.01] [VJ013965].
                                                  zip
-a----      2026-11-13   오전 12:31      482040745 PASEC [v2.2566].zip
-a----      2026-06-09   오후 2:00      667374376 Spooky Milk Life [Steam 1621540].7z
PS C:\\Users\\Test> 
"""


def test_parse_listing_recovers_wrapped_multilingual_filenames():
    data = batch.parse_powershell_listing(EXAMPLE)
    assert len(data) == 6
    assert data[2].original_filename == "Eliminator 카에데씨 [v1.2] [RJ209760·Steam 1122040].7z"
    assert data[3].original_filename.endswith("[VJ013965].zip")
    assert data[3].file_size == 3708641822


def test_exclusion_is_exact_and_keeps_other_files():
    rows = batch.parse_powershell_listing(EXAMPLE)
    summary, items = batch.analyze_listing(
        rows, excluded=("Craft to Exile 2 [Server v1.1.3].zip",))
    assert summary["input_files"] == 6
    assert summary["excluded_files"] == 1
    assert summary["analyzed_files"] == 5
    assert all("Craft to Exile 2" not in item["original_filename"] for item in items)
    assert summary["steam_id_files"] == 2
    assert summary["dlsite_code_files"] == 2


def test_filename_only_processing_is_explicitly_not_identity_verification():
    rows = batch.parse_powershell_listing(EXAMPLE)
    _, items = batch.analyze_listing(rows)
    assert "online_status" not in items[0]
    assert "search_title" in items[0]
    assert items[2]["steam_app_ids"] == ["1122040"]
    assert items[2]["dlsite_codes"] == ["RJ209760"]


def test_cli_offline_mode_never_calls_online_and_csv_json_explicit(tmp_path, monkeypatch, capsys):
    original = tmp_path / "powershell-list.txt"
    original.write_text(EXAMPLE, encoding="utf-8")
    before = original.read_bytes()
    monkeypatch.setattr(batch.time, "sleep", lambda *_: (_ for _ in ()).throw(
        AssertionError("offline never pauses or runs network")))
    csv_path, json_path = tmp_path / "out.csv", tmp_path / "out.json"
    assert batch.main([str(original),
                       "--exclude", "Craft to Exile 2 [Server v1.1.3].zip",
                       "--csv", str(csv_path), "--json-output", str(json_path)]) == 0
    assert original.read_bytes() == before
    assert json.loads(capsys.readouterr().out)["analyzed_files"] == 5
    assert json.loads(json_path.read_text(encoding="utf-8"))["summary"]["analyzed_files"] == 5
    assert "original_filename" in csv_path.read_text(encoding="utf-8-sig")


def test_search_title_cleanup_handles_distribution_memos_not_subtitles():
    from experiments.dlsite_detector.search_terms import cleaned_search_title
    examples = {
        "Demo [번역 수정1] [RJ01081508].zip": "Demo",
        "Demo [손번역 수정2·노모] [RJ01081508].zip": "Demo",
        "Demo [beta 1.0.1].zip": "Demo",
        "Demo [v2 Fix].zip": "Demo",
        "Demo [2025-11-20].zip": "Demo",
        "Demo [한국어 패치 Fix2].zip": "Demo",
        "RJ01081508 [250418].zip": "",
        "RJ01081508 [공식 한국어 v1.3.1].zip": "",
        "Demo [Rebirth].zip": "Demo [Rebirth]",
        "Game 2 [Rebirth].zip": "Game 2 [Rebirth]",
    }
    for filename, expected in examples.items():
        assert cleaned_search_title(filename) == expected, filename


def test_code_only_with_distribution_notes_still_routes_to_direct_code_lookup():
    rows = batch.parse_powershell_listing(
        "-a----      2026-11-17   오후 1:05      123456789 RJ01081508 [번역].zip\\n"
    )
    summary, records = batch.analyze_listing(rows)
    assert summary["analyzed_files"] == 1
    assert records[0]["search_title"] == ""
    assert records[0]["dlsite_codes"] == ["RJ01081508"]
    assert records[0]["offline_status"] == "direct_id_lookup"
