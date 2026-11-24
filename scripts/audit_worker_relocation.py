"""3-A: prove worker relocation preserves exact file bytes and caller logic."""
from __future__ import annotations
import ast
import json
import re
from pathlib import Path
from audit_import_cleanup import tree, source
from audit_source import git

BASELINE = "6182f8c03e4a6d5923b77f6ded5d5c5d5cd90db8"
MOVES = {"workers": "game_tasks", "catalog_collection_worker": "catalog_collection",
         "identity_artwork_worker": "identity_artwork", "title_workers": "title",
         "work_lookup_worker": "work_lookup"}
ROOT = "src/playdock/"
CALLERS = {"app.py", "title_editor.py", ROOT+"controllers/catalog_collection.py",
           ROOT+"controllers/game_actions.py", ROOT+"controllers/metadata.py",
           ROOT+"controllers/title_editor.py", ROOT+"ui/dialogs/title.py",
           ROOT+"ui/work_info_dialog.py"}

def main():
    before, after = tree(BASELINE), tree("HEAD")
    paths = {ROOT+"services/"+old+".py":ROOT+"workers/"+new+".py"
             for old,new in MOVES.items()}
    assert set(before)-set(after) == set(paths), set(before)-set(after)
    assert all(before[p] == after[q] for p,q in paths.items()), "Worker bytes changed"
    protected = {p for p in before if p.startswith((ROOT,"experiments/")) or
                 p in {"app.py","title_editor.py","title_editor_entry.py",
                       "setup_wizard.py","uninstall_wizard.py","requirements.txt"}}
    changed = {p for p in protected-set(paths) if before[p] != after.get(p)}
    assert changed == CALLERS, changed
    for p in sorted(changed):
        expected = source(BASELINE,p)
        for old,new in MOVES.items():
            expected = re.sub(r"\bservices\."+re.escape(old)+r"\b", "workers."+new, expected)
        assert expected == source("HEAD",p), p
    findings = []
    for p in sorted(after):
        if not p.endswith(".py") or p.startswith("scripts/audit_"):
            continue
        raw = source("HEAD",p)
        ast.parse(raw,filename=p)
        for n,line in enumerate(raw.splitlines(),1):
            for old in MOVES:
                if (re.search(r"\bservices\."+re.escape(old)+r"\b",line)
                    or re.search(r"\bfrom services import "+re.escape(old)+r"\b",line)
                    or "services/"+old+".py" in line):
                    findings.append(dict(path=p,line=n,text=line.strip()))
    for p in sorted(after):
        if not p.startswith((".github/workflows/","scripts/")) or not p.endswith((".yml",".yaml",".ps1",".bat",".spec")):
            continue
        for n,line in enumerate(source("HEAD",p).splitlines(),1):
            for old in MOVES:
                if "services/"+old+".py" in line or "services."+old in line:
                    findings.append(dict(path=p,line=n,text=line.strip()))
    service_threads = []
    for p in sorted(after):
        if p.startswith(ROOT+"services/") and p.endswith(".py"):
            for node in ast.walk(ast.parse(source("HEAD",p))):
                if isinstance(node, ast.ClassDef) and any(ast.unparse(b).split(".")[-1]=="QThread" for b in node.bases):
                    service_threads.append((p,node.name))
    report = dict(baseline=BASELINE, head=git("rev-parse","HEAD").decode().strip(),
                  moves=[dict(old=p,new=q,sha=before[p]) for p,q in paths.items()],
                  callers=sorted(changed), stale_references=findings, service_threads=service_threads)
    out=Path("audit_output")
    out.mkdir(exist_ok=True)
    (out/"workers_relocation.json").write_text(json.dumps(report,indent=2),encoding="utf-8")
    print(json.dumps(report,indent=2))
    assert not findings, findings
    assert not service_threads, service_threads
    print("WORKER_RELOCATION_VERIFIED")

if __name__ == "__main__":
    main()
