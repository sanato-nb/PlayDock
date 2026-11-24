"""Validate 3-B relocation, function integrity and obsolete references."""
from __future__ import annotations
import ast
import json
import re
from pathlib import Path
from audit_import_cleanup import tree, source
from audit_source import git

BASELINE = "1c3fe1567eefadabb83039cf3491e075a3ed8e2a"
ROOT = "src/playdock/"
MOVES = {
    "local_storage":"storage/local", "setup_paths":"storage/setup_paths",
    "game_collections":"storage/collections", "collection_board_model":"models/collection_board",
    "library_tree":"models/library_tree", "game_codes":"models/game_codes",
    "game_icons":"ui/widgets/game_icons", "launch_approval":"services/launch_approval",
    "launch_options":"services/launch_options", "save_backups":"services/save_backups",
    "simple_title_edit":"services/simple_title_edit", "bulk_title_edit":"services/bulk_title_edit",
    "localized_titles":"services/localized_titles",
}

def normalize(s):
    for old, path in MOVES.items():
        new = path.replace("/", ".")
        s = re.sub(r"\bfrom "+old+r" import\b", "from "+new+" import", s)
        s = re.sub(r"^(\s*)import "+old+r"(?: as (\w+))?\s*$",
                   lambda m: m[1]+"from "+new.rsplit(".",1)[0]+" import "+new.rsplit(".",1)[1]+" as "+(m[2] or old),
                   s, flags=re.M)
    return ast.dump(ast.parse(s), include_attributes=False)

def main():
    before, after = tree(BASELINE), tree("HEAD")
    paths = {ROOT+old+".py":ROOT+new+".py" for old,new in MOVES.items()}
    assert set(before)-set(after) == set(paths), set(before)-set(after)
    for p,q in paths.items():
        assert normalize(source(BASELINE,p)) == ast.dump(ast.parse(source("HEAD",q)),include_attributes=False), (p,q)
    protected = {p for p in before if p.startswith((ROOT,"experiments/")) or
                 p in {"app.py","title_editor.py","title_editor_entry.py","setup_wizard.py",
                       "uninstall_wizard.py","requirements.txt"}}
    changes = {p for p in protected-set(paths) if before[p] != after.get(p)}
    for p in sorted(changes):
        assert p.endswith(".py") and not p.startswith("experiments/"), p
        assert normalize(source(BASELINE,p)) == ast.dump(ast.parse(source("HEAD",p)),include_attributes=False), p
    findings = []
    for p in sorted(after):
        if p.startswith("scripts/audit_") or p.startswith("docs/"):
            continue
        if p.endswith(".py"):
            raw=source("HEAD",p)
            parsed=ast.parse(raw,filename=p)
            for node in ast.walk(parsed):
                if isinstance(node,ast.ImportFrom) and (node.module or "") in MOVES:
                    findings.append(dict(path=p,line=node.lineno,ref=node.module))
                if isinstance(node,ast.Import):
                    for a in node.names:
                        if a.name in MOVES:
                            findings.append(dict(path=p,line=node.lineno,ref=a.name))
        elif p.endswith((".ps1",".bat",".yml",".yaml",".spec")):
            raw=source("HEAD",p)
        else:
            continue
        for i,line in enumerate(raw.splitlines(),1):
            for old in MOVES:
                if ROOT+old+".py" in line.replace("\\","/") or re.search(r"\bfrom "+old+r" import\b",line):
                    findings.append(dict(path=p,line=i,ref=line.strip()))
                if re.search(r"--hidden-import(?:['\"]?,\s*['\"]| +)"+old+r"\b",line):
                    findings.append(dict(path=p,line=i,ref=line.strip()))
    report = dict(baseline=BASELINE,head=git("rev-parse","HEAD").decode().strip(),
                  moved=[dict(old=p,new=q,old_sha=before[p],new_sha=after[q],ast_preserved=True)
                         for p,q in paths.items()],
                  changed_callers=sorted(changes),stale_references=findings,
                  unchanged_protected=len(protected-set(paths)-changes))
    out=Path("audit_output")
    out.mkdir(exist_ok=True)
    (out/"module_relocation.json").write_text(json.dumps(report,indent=2),encoding="utf-8")
    print(json.dumps(report,indent=2))
    assert not findings, findings
    print("MODULE_RELOCATION_VERIFIED")

if __name__ == "__main__":
    main()
