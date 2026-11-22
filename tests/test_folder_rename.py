"""One-folder workflow: no JSON pickers; private mapping + official confirmation."""
import json
from pathlib import Path

import pytest

from experiments.dlsite_detector.folder_rename import (
    DATA_FILENAME, scan_archives, folder_plan, load_local_mapping, rename_verified,
)
from experiments.dlsite_detector.research_handoff import (
    VerifiedSuggestion, undo_last,
)

SCHEMA = "playdock-ai-review-v1"


def data_file(folder: Path):
    names = [
        "BUZAMA 2.7z",
        "Game [v1.0] [한국어].zip",
        "Game DLC1 [v1.0].rar",
        "Unnamed [한국어].zip",
        "Game Double.zip",
    ]
    rows = [
        {"original_filename": names[0], "store":"dlsite","code":"RJ01052720",
         "official_url":"https://www.dlsite.com/maniax/work/=/product_id/RJ01052720.html",
         "verification":"official_confirmed"},
        {"original_filename": names[1], "store":"steam","code":"1091500",
         "official_url":"https://store.steampowered.com/app/1091500/",
         "verification":"official_confirmed"},
        {"original_filename": names[2], "store":"dlsite","code":"RJ654321",
         "official_url":"https://www.dlsite.com/maniax/work/=/product_id/RJ654321.html",
         "verification":"official_confirmed"},
        {"original_filename": names[3], "store":"","code":"","verification":"unknown"},
        {"original_filename": names[4], "store":"dlsite","code":"RJ123456",
         "official_url":"https://www.dlsite.com/maniax/work/=/product_id/RJ123456.html",
         "verification":"candidate"},
    ]
    dest = folder / DATA_FILENAME
    dest.write_text(json.dumps({
        "schema": SCHEMA,
        "excluded": [{"original_filename": n, "exclusion_reason": "no_identifier"}
                     for n in names],
        "results": rows,
    }, ensure_ascii=False), encoding="utf-8")
    return dest, names


def test_same_sidecar_loads_all_without_second_json_selector(tmp_path):
    path, names = data_file(tmp_path)
    rows, warnings = load_local_mapping(path)
    assert not warnings
    assert [r.filename for r in rows] == names
    assert [r.ai_status for r in rows] == [
        "claimed_confirmed", "claimed_confirmed", "identity_ambiguous",
        "unknown", "candidate",
    ]


def test_only_matching_files_in_folder_plan_and_recursive(tmp_path):
    p, names = data_file(tmp_path)
    root = tmp_path / "archives"
    root.mkdir()
    nested = root / "gamefiles"
    nested.mkdir()
    (root / names[0]).write_bytes(b"A")
    (nested / names[1]).write_bytes(b"B")
    (root / names[2]).write_bytes(b"C")
    (root / names[3]).write_bytes(b"D")
    found = scan_archives(root)
    assert names[0] in found and names[1] in found
    rows, _ = load_local_mapping(p)
    plan = folder_plan(root, rows)
    assert [p.status for p in plan] == [
        "ready", "ready", "manual", "manual", "missing",
    ]
    assert plan[0].row.proposed == "BUZAMA 2 [RJ01052720].7z"
    assert plan[1].row.proposed == "Game [v1.0] [한국어] [Steam 1091500].zip"


def test_no_unverified_rename_even_if_ai_says_confirmed(tmp_path):
    path, names = data_file(tmp_path)
    file = tmp_path / names[0]
    file.write_bytes(b"Original archive")
    rows, _ = load_local_mapping(path)
    match = folder_plan(tmp_path, rows)[0]
    suggestion = match.row.suggestion
    with pytest.raises(ValueError):
        rename_verified(match, VerifiedSuggestion(suggestion, False),
                        journal=tmp_path / "log.jsonl")
    assert file.is_file()


def test_approved_rename_and_undo_preserve_file_content(tmp_path):
    path, names = data_file(tmp_path)
    file = tmp_path / names[0]
    file.write_bytes(b"Original archive untouched")
    rows, _ = load_local_mapping(path)
    match = folder_plan(tmp_path, rows)[0]
    proof = VerifiedSuggestion(match.row.suggestion, True,
                               "Official Japanese Title", "https://www.dlsite.com/")
    journal = tmp_path / "private-history.jsonl"
    dest, _ = rename_verified(match, proof, journal=journal)
    assert not file.exists()
    assert dest.name == "BUZAMA 2 [RJ01052720].7z"
    assert dest.read_bytes() == b"Original archive untouched"
    assert undo_last(journal) == (dest, file)
    assert file.read_bytes() == b"Original archive untouched"


def test_mismatched_verification_cannot_rename(tmp_path):
    path, names = data_file(tmp_path)
    file = tmp_path / names[0]
    file.write_bytes(b"File")
    rows, _ = load_local_mapping(path)
    plan = folder_plan(tmp_path, rows)
    wrong_proof = VerifiedSuggestion(plan[1].row.suggestion, True)
    with pytest.raises(ValueError):
        rename_verified(plan[0], wrong_proof, journal=tmp_path / "log.jsonl")
    assert file.exists()


def test_duplicate_filenames_are_skipped(tmp_path):
    path, names = data_file(tmp_path)
    root = tmp_path / "archives"
    (root / "a").mkdir(parents=True)
    (root / "b").mkdir()
    (root / "a" / names[0]).write_bytes(b"A")
    (root / "b" / names[0]).write_bytes(b"B")
    rows, _ = load_local_mapping(path)
    plan = folder_plan(root, rows)
    assert plan[0].status == "duplicate" and plan[0].path is None


def test_existing_destination_will_not_be_overwritten(tmp_path):
    path, names = data_file(tmp_path)
    (tmp_path / names[0]).write_bytes(b"old")
    (tmp_path / "BUZAMA 2 [RJ01052720].7z").write_bytes(b"other")
    rows, _ = load_local_mapping(path)
    match = folder_plan(tmp_path, rows)[0]
    assert match.status == "collision"
    assert (tmp_path / names[0]).read_bytes() == b"old"


def test_private_source_json_not_exposed_on_public_repo():
    source = (Path(__file__).resolve().parents[1] /
              "scripts" / "one_folder_renamer.py").read_text(encoding="utf-8")
    assert "askdirectory" in source
    assert "askopenfilename" not in source
    assert "load_local_mapping(self.mapping_path)" in source
    assert "messagebox.askyesno(" in source
    assert "reverify(" in source
    assert "rename_verified(" in source
    assert "BUZAMA 2 [RJ01052720].7z" not in source


def test_no_arbitrary_source_file_path_on_sidecar(tmp_path):
    path, names = data_file(tmp_path)
    doc = json.loads(path.read_text(encoding="utf-8"))
    doc["excluded"][0]["original_filename"] = "../bad.7z"
    path.write_text(json.dumps(doc), encoding="utf-8")
    rows, errs = load_local_mapping(path)
    assert all(row.filename != "../bad.7z" for row in rows)
