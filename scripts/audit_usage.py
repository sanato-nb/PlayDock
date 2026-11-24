"""Cross-check stage 1-A candidates against tracked source, tests, build and docs."""
from __future__ import annotations
import argparse
import ast
import collections
import hashlib
import json
import re
from pathlib import Path
from audit_source import git

FOCUS = {
    "collection_board.py": ["collection_board", "CollectionBoard"],
    "dark_selector.py": ["dark_selector", "DarkMenuSelect"],
    "online_art_dialog.py": ["online_art_dialog", "OnlineArtworkDialog"],
    "ui/artwork_dialog.py": ["ui.artwork_dialog", "artwork_dialog.py", "OnlineArtworkDialog"],
    "services/artwork_workers.py": ["artwork_workers", "ArtworkSearchThread", "ArtworkDownloadThread"],
    "work_db_dialog.py": ["work_db_dialog", "WorkPreviewDialog", "WorkLookupThread"],
    "AI provider and settings": ["ai_providers", "SettingsDialog", "settings_dialog", "get_secret", "set_secret", "generate_ai_art", "ai_game_title", "translate_work_title", "TitleWorker"],
    "legacy title editor": ["open_title_editor", "open_selected_name_settings", "open_bulk_name_settings", "TitleEditor", "TitleEditorActionsMixin"],
    "legacy image search": ["open_online_artwork", "search_images", "online_artwork", "open_artwork_library", "refresh_local_art"],
    "official collection": ["collect_library_information", "CatalogCollector", "code_only", "IdentityArtworkThread", "open_official_name_settings"],
}
BUILD_EXT = {".bat", ".ps1", ".yml", ".yaml", ".spec", ".toml", ".cfg", ".ini", ".txt"}
ENTRY = {"app.py", "title_editor.py", "title_editor_entry.py", "setup_wizard.py", "uninstall_wizard.py"}


def kind(path):
    if path.startswith("tests/") or path == "refactor_test_support.py":
        return "test"
    if path.startswith("experiments/"):
        return "experiment"
    if path.startswith(".github/") or (path.startswith("scripts/") and Path(path).suffix in BUILD_EXT) or path == "requirements.txt":
        return "build"
    if path.startswith("scripts/"):
        return "script"
    if path.startswith("src/playdock/") or path in ENTRY:
        return "production"
    return "documentation"


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--inventory", type=Path, required=True)
    p.add_argument("--out", type=Path, required=True)
    a = p.parse_args()
    inv = json.loads(a.inventory.read_text(encoding="utf-8"))
    ref = inv["baseline"]
    sources, errors = {}, []
    for item in inv["tracked"]:
        path = item["path"]
        if Path(path).suffix.lower() not in BUILD_EXT | {".py", ".md", ".json", ".rst"}:
            continue
        raw = git("show", f"{ref}:{path}")
        sha = hashlib.sha1(f"blob {len(raw)}\0".encode() + raw).hexdigest()
        if sha != item["sha"]:
            errors.append(path + ": SHA mismatch")
            continue
        try:
            sources[path] = raw.decode("utf-8-sig").splitlines()
        except UnicodeError:
            # Legacy Windows scripts may use CP949. Record an undecodable file rather than omit it.
            try:
                sources[path] = raw.decode("cp949").splitlines()
            except UnicodeError:
                errors.append(path + ": decode failed")
    evidence = {}
    for label, tokens in FOCUS.items():
        hits = []
        pats = [re.compile(r"(?<![\w])" + re.escape(t) + r"(?![\w])") for t in tokens]
        for path, lines in sources.items():
            for i, line in enumerate(lines, 1):
                found = [t for t, pat in zip(tokens, pats) if pat.search(line)]
                if found:
                    hits.append(dict(path=path, line=i, kind=kind(path), tokens=found, text=line.strip()[:300]))
        evidence[label] = hits
    import_review = []
    for path, record in inv["files"].items():
        if not path.startswith("src/playdock/"):
            continue
        for candidate in record["unused_import_candidates"]:
            name = candidate["name"]
            pat = re.compile(r"(?<![\w])" + re.escape(name) + r"(?![\w])")
            hits = [dict(path=p, line=i, kind=kind(p), text=line.strip()[:200])
                    for p, lines in sources.items() if p != path
                    for i, line in enumerate(lines, 1) if pat.search(line)]
            import_review.append(dict(path=path, **candidate, external_mentions=hits))
    callbacks = []
    for path, lines in sources.items():
        if kind(path) != "production" or not path.endswith(".py"):
            continue
        root = ast.parse("\n".join(lines), filename=path)
        for node in ast.walk(root):
            if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
                continue
            if node.func.attr not in {"connect", "addAction", "action_button", "addMenu"}:
                continue
            if not node.args:
                continue
            callbacks.append(dict(path=path, line=node.lineno, call=ast.unparse(node)[:500]))
    out = dict(baseline=ref, checked_text_files=len(sources), errors=errors,
               focus=evidence, unused_import_review=import_review, callback_sites=callbacks,
               duplicate_groups=inv["duplicate_body_candidates"],
               limitations=["Text mentions can be unrelated, negative assertions or documentation; not call proof.",
                            "Callback sites are syntax evidence; runtime probes exercise selected menu routes.",
                            "No candidate is automatically deleted."])
    a.out.mkdir(parents=True, exist_ok=True)
    (a.out/"usage_evidence.json").write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    lines = ["# 1-B 참조 교차 검증", f"기준: {ref}", f"텍스트 파일 {len(sources)}개, 오류 {len(errors)}개",
             f"미사용 import 후보 교차 검색: {len(import_review)}건",
             f"UI 콜백 연결 구문: {len(callbacks)}개", "",
             "| 검토 대상 | 본체 | 테스트 | 빌드 | 실험 | 스크립트 | 문서 |", "|---|---:|---:|---:|---:|---:|---:|"]
    for label,hits in evidence.items():
        counts = collections.Counter(x["kind"] for x in hits)
        lines.append("| " + label + " | " + " | ".join(str(counts[k]) for k in ("production","test","build","experiment","script","documentation")) + " |")
    lines.extend(["", "동일 함수 본문 후보:", *["- " + "; ".join(f"{x['path']}:{x['line']} {x['function']}" for x in g) for g in out["duplicate_groups"]], "", "모든 수치는 참조 행 수이며 실제 실행 횟수가 아니다."])
    (a.out/"usage_summary_KO.md").write_text("\n".join(lines)+"\n", encoding="utf-8")
    print("\n".join(lines))
    if errors or len(import_review) != 97:
        raise SystemExit(1)
    print("USAGE_AUDIT_COMPLETE")

if __name__ == "__main__":
    main()
