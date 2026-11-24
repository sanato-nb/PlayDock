"""Verify retired UI modules and preservation of all other production sources."""
from __future__ import annotations
import ast
import json
from pathlib import Path
from audit_source import git, module_name
from audit_import_cleanup import tree, source

BASELINE = "3814e2360f2638f5a56b318f444f50fb47a6dc52"
RETIRED = {
    "src/playdock/" + p for p in (
        "collection_board.py", "dark_selector.py", "online_art_dialog.py",
        "work_db_dialog.py", "ui/artwork_dialog.py", "services/artwork_workers.py",
    )
}

def main():
    before, after = tree(BASELINE), tree("HEAD")
    deleted = set(before) - set(after)
    changed = {p for p in before.keys() & after.keys() if before[p] != after[p]}
    production = {p for p in before if p.startswith("src/playdock/") or p in {
        "app.py", "title_editor.py", "title_editor_entry.py", "setup_wizard.py",
        "uninstall_wizard.py", "requirements.txt"}}
    assert deleted == RETIRED, (deleted, RETIRED)
    assert not (changed & production), changed & production
    assert not any(p.startswith("experiments/") for p in changed | deleted)
    names = {module_name(p) for p in RETIRED}
    names |= {"playdock." + n for n in names}
    findings = []
    for path in sorted(after):
        if not path.endswith(".py") or path.startswith("docs/"):
            continue
        parsed = ast.parse(source("HEAD", path), filename=path)
        for node in ast.walk(parsed):
            modules = []
            if isinstance(node, ast.Import):
                modules = [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom):
                module = node.module or ""
                modules = [module]
                modules += [module + "." + a.name for a in node.names]
            for m in modules:
                if m in names:
                    findings.append(dict(path=path,line=node.lineno,module=m))
    # Direct imports in nested test subprocess source are checked by tests.
    out = Path("audit_output")
    out.mkdir(exist_ok=True)
    report = dict(baseline=BASELINE,head=git("rev-parse","HEAD").decode().strip(),
                  removed=[dict(path=p,sha=before[p],lines=len(source(BASELINE,p).splitlines()))
                           for p in sorted(deleted)],
                  preserved_production_files=len(production-RETIRED),
                  changed_production_files=sorted(changed&production),
                  direct_retired_imports=findings,
                  modified_existing_files=sorted(changed))
    (out/"legacy_ui_cleanup.json").write_text(json.dumps(report,indent=2),encoding="utf-8")
    print("REMOVED_FILES",len(deleted))
    print("REMOVED_LINES",sum(r["lines"] for r in report["removed"]))
    for r in report["removed"]: print("REMOVED",r)
    print("PRESERVED_PRODUCTION_FILES",report["preserved_production_files"])
    print("RETIRED_IMPORT_REFERENCES",len(findings))
    assert not findings, findings
    print("LEGACY_UI_CLEANUP_VERIFIED")

if __name__ == "__main__":
    main()
