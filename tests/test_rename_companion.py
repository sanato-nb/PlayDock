"""Standalone rename handoff must preserve all excluded rows, not just found codes."""
import csv
import json
from pathlib import Path
import pytest

from experiments.dlsite_detector.rename_companion import (
    load_exclusions, load_review, manual_rows, write_manual_csv,
)
from experiments.dlsite_detector.research_handoff import (
    safe_rename, undo_last, proposed_filename,
)

SCHEMA = "playdock-ai-review-v1"


def write(path, obj):
    path.write_text(json.dumps(obj, ensure_ascii=False), encoding="utf-8")
    return path


def fixture(tmp_path):
    names = [
        "6월의 너와 나 [한국어].7z",
        "Candidate Game [v2.0].zip",
        "Unknown [한글].rar",
        "Bad Code.7z",
    ]
    scan = write(tmp_path / "scan.json", {
        "program": "PlayDock DLsite → Steam Code Checker",
        "results": [{"query": name, "input_origin": "archive",
                     "status": "excluded", "attempted_stores": []} for name in names]
        + [{"query": "Confirmed [RJ123456].zip", "status": "confirmed"}]
    })
    good_url = "https://www.dlsite.com/maniax/work/=/product_id/RJ01081508.html"
    ai = write(tmp_path / "ai.json", {"schema": SCHEMA, "results": [
        {"original_filename": names[0], "store": "dlsite",
         "code": "RJ01081508", "official_url": good_url,
         "verification": "official_confirmed", "note": "번역명 별칭 확인"},
        {"original_filename": names[1], "store": "steam",
         "code": "1091500", "official_url": "https://store.steampowered.com/app/1091500/",
         "verification": "candidate", "note": "동명이인 가능성"},
        {"original_filename": names[2], "store": "", "code": "",
         "official_url": "", "verification": "unknown", "note": "찾지 못함"},
        {"original_filename": names[3], "store": "steam", "code": "1091500",
         "official_url": "https://fake.example/app/1091500/",
         "verification": "official_confirmed"},
    ]})
    return scan, ai, names


def test_scan_and_ai_json_merge_all_excluded_without_dropping_unknown(tmp_path):
    scan, ai, names = fixture(tmp_path)
    rows, errors = load_review(scan, ai)
    assert len(rows) == 4
    assert [r.filename for r in rows] == names
    assert [r.ai_status for r in rows] == [
        "claimed_confirmed", "candidate", "unknown", "invalid"]
    assert len(errors) == 1
    assert rows[0].proposed == "6월의 너와 나 [한국어] [RJ01081508].7z"
    assert rows[1].proposed == "Candidate Game [v2.0] [Steam 1091500].zip"
    assert rows[2].proposed == names[2]
    assert rows[3].proposed == names[3]
    # 'official_confirmed' AI label does not equal real official verification.
    assert len(manual_rows(rows)) == 4


def test_manual_list_after_official_recheck(tmp_path):
    scan, ai, names = fixture(tmp_path)
    rows, _ = load_review(scan, ai)
    pending = manual_rows(rows, {names[0]})
    assert len(pending) == 3
    csv_file = tmp_path / "manual.csv"
    assert write_manual_csv(csv_file, rows, {names[0]}) == 3
    with csv_file.open(encoding="utf-8-sig", newline="") as file:
        record = list(csv.reader(file))
    assert len(record) == 4
    assert all(x[0] != names[0] for x in record[1:])
    assert any("공식" in x[5] for x in record[1:])


def test_same_handling_with_excluded_research_json(tmp_path):
    scan, ai, names = fixture(tmp_path)
    scan2 = write(tmp_path / "excluded.json", {
        "schema": SCHEMA, "task": "research_excluded_identifiers",
        "excluded": [{"original_filename": name, "exclusion_reason": "no_identifier"}
                     for name in names]
    })
    rows, errors = load_review(scan2, ai)
    assert [r.filename for r in rows] == names
    assert len(errors) == 1


def test_research_filename_with_path_injection_is_ignored(tmp_path):
    scan, ai, names = fixture(tmp_path)
    scan2 = write(tmp_path / "excluded.json", {
        "schema": SCHEMA,
        "excluded": [
            {"original_filename": "../escape.zip", "exclusion_reason": "no_identifier"},
            {"original_filename": r"C:\Users\X\escape.zip", "exclusion_reason": "no_identifier"},
            {"original_filename": names[0], "exclusion_reason": "no_identifier"},
        ],
    })
    assert [x["original_filename"] for x in load_exclusions(scan2)] == [names[0]]


def test_read_wrong_schema_fails(tmp_path):
    scan, ai, names = fixture(tmp_path)
    write(ai, {"schema": "not-playdock", "results": []})
    with pytest.raises(ValueError):
        load_review(scan, ai)


def test_old_scan_json_without_excluded_fails(tmp_path):
    scan, ai, names = fixture(tmp_path)
    write(scan, {"results": [{"status": "confirmed", "query": "a.zip"}]})
    with pytest.raises(ValueError):
        load_review(scan, ai)


def test_manual_csv_does_not_contain_local_folders(tmp_path):
    scan, ai, names = fixture(tmp_path)
    rows, _ = load_review(scan, ai)
    dest = tmp_path / "pending.csv"
    write_manual_csv(dest, rows)
    contents = dest.read_text(encoding="utf-8-sig")
    assert str(tmp_path) not in contents


def test_archive_rename_and_undo_only_changes_name(tmp_path):
    file = tmp_path / "Game [v1.0].zip"
    file.write_bytes(b"not actually a zip -- no contents should be touched")
    changed, _ = safe_rename(file, proposed_filename(file.name, "dlsite", "RJ123456"),
                             tmp_path / "history" / "rename.jsonl")
    assert changed.read_bytes() == b"not actually a zip -- no contents should be touched"
    assert changed.name == "Game [v1.0] [RJ123456].zip"
    undo_last(tmp_path / "history" / "rename.jsonl")
    assert file.read_bytes() == b"not actually a zip -- no contents should be touched"


def test_source_buttons_are_not_automatic_apply(tmp_path):
    source = (Path(__file__).resolve().parents[1] / "scripts" /
              "standalone_renamer_window.py").read_text(encoding="utf-8")
    assert 'messagebox.askyesno(' in source
    assert "self.verified" in source
    assert "write_manual_csv" in source
    assert "safe_rename(" in source
    assert "if __name__ == \"__main__\":" in source



@pytest.mark.parametrize("old", [
    "Universe Treasure [v2.5] [DLC1·노모].7z",
    "Sister Fantasy [DLC 2.0.1] [한국어].7z",
    "Fate Empire of Dirt [v1.12] + Made in Heaven [v1.03].7z",
])
def test_dlc_and_multi_product_claims_require_manual_review(tmp_path, old):
    from experiments.dlsite_detector.rename_companion import requires_manual_identity_check
    assert requires_manual_identity_check(old)
    scan = write(tmp_path / "exclude.json", {
        "schema": SCHEMA,
        "excluded": [{"original_filename": old, "exclusion_reason": "no_identifier"}]
    })
    ai = write(tmp_path / "ai.json", {
        "schema": SCHEMA,
        "results": [{"original_filename": old, "store": "dlsite", "code": "RJ123456",
                     "official_url": "https://www.dlsite.com/maniax/work/=/product_id/RJ123456.html",
                     "verification": "official_confirmed"}]
    })
    rows, errors = load_review(scan, ai)
    assert not errors
    assert rows[0].ai_status == "identity_ambiguous"
    assert "수동 확인" in rows[0].note


def test_regular_archive_not_blocked_as_dlc():
    from experiments.dlsite_detector.rename_companion import requires_manual_identity_check
    assert not requires_manual_identity_check("BUZAMA 2 [v1.2].7z")
    assert not requires_manual_identity_check("Treasure Hunter Claire [Korean].zip")
