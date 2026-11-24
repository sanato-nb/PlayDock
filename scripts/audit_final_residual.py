"""Final read-only source audit against the exact pre-optimization Git revision."""
from __future__ import annotations

import argparse
import ast
import json
from pathlib import Path
import subprocess
import sys
from audit_source import ROOT, ENTRYPOINTS, git, module_name

BASELINE = "af10566aeb5a066ac5ee9beb9565823b73895002"
RETIRED_MODULES = {
    "collection_board", "dark_selector", "online_art_dialog", "work_db_dialog",
    "ui.artwork_dialog", "services.artwork_workers", "save_backups",
    "services.save_backups",
}
RETIRED_SYMBOLS = {
    "SettingsDialog", "settings_dialog", "generate_ai_art", "IMAGE_URL",
    "SaveBackupThread", "create_save_backup", "restore_save_backup",
    "backup_saves", "restore_saves", "start_save_worker", "save_worker_finished",
    "save_worker", "save_backups",
}
RETIRED_ENDPOINTS = ("/v1/images/generations", "openrouter.ai/api/v1/images",
                     "responseModalities")
COMPATIBILITY = {
    "src/playdock/core.py": "public compatibility imports for existing callers",
    "src/playdock/work_db.py": "official DB compatibility import path",
    "src/playdock/ai_providers.py": "optional legacy text editor and stored credential compatibility",
    "src/playdock/services/settings_service.py": "folder and legacy provider preferences",
}
def production(path):
    return path.startswith("src/playdock/") or path in ENTRYPOINTS

def run_inventory(ref, out):
    subprocess.run([sys.executable, str(ROOT/"scripts/audit_source.py"), "--ref", ref,
                    "--out", str(out)], check=True)
    return json.loads((out/"inventory.json").read_text(encoding="utf-8"))

def tree(inv):
    return {r["path"]:r["sha"] for r in inv["tracked"]}

def metrics(inv):
    files=[r for p,r in inv["files"].items() if p.startswith("src/playdock/")]
    entry=[r for p,r in inv["files"].items() if p in ENTRYPOINTS]
    clones=[g for g in inv["duplicate_body_candidates"]
            if sum(production(x["path"]) for x in g)>=2]
    return {"tracked":len(inv["tracked"]), "python":inv["python_count"],
            "parsed":inv["parsed_count"], "core_files":len(files),
            "core_lines":sum(r["lines"] for r in files),
            "core_bytes":sum(r["bytes"] for r in files),
            "entry_lines":sum(r["lines"] for r in entry),
            "entry_bytes":sum(r["bytes"] for r in entry),
            "unused_import_candidates":sum(len(r["unused_import_candidates"]) for r in files),
            "direct_experiment_edges":len(inv["experiment_edges"]),
            "reachable_experiment_modules":len(inv["reachable_experiments"]),
            "duplicate_groups_all":len(inv["duplicate_body_candidates"]),
            "duplicate_groups_with_multiple_production_members":len(clones)}

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--out",type=Path,required=True)
    a=ap.parse_args()
    out=a.out.resolve()
    before=run_inventory(BASELINE,out/"before")
    after=run_inventory("HEAD",out/"after")
    old,new=tree(before),tree(after)
    manifest=json.loads((ROOT/"docs/ui_reference/source_manifest.json").read_text(encoding="utf-8"))
    ui={r["path"]:r["sha"] for r in manifest["files"]}
    ui_changes=[p for p,sha in ui.items() if new.get(p)!=sha]
    experiment_changes=[p for p in sorted(old.keys()|new.keys())
                        if p.startswith("experiments/") and old.get(p)!=new.get(p)]
    retired_files=[p for p in new if p.startswith("src/playdock/") and p.endswith(".py")
                   and module_name(p) in RETIRED_MODULES]
    findings=[]
    for path in sorted(p for p in after["files"] if production(p)):
        parsed=ast.parse(git("show",f'{after["baseline"]}:{path}').decode("utf-8-sig"),filename=path)
        for node in ast.walk(parsed):
            names=set()
            if isinstance(node,(ast.FunctionDef,ast.AsyncFunctionDef,ast.ClassDef)):
                names.add(node.name)
            elif isinstance(node,ast.Name):
                names.add(node.id)
            elif isinstance(node,ast.Attribute):
                names.add(node.attr)
            elif isinstance(node,(ast.Import,ast.ImportFrom)):
                names.update(a.name for a in node.names)
                if isinstance(node,ast.ImportFrom):
                    m=node.module or ""
                    names.add(m)
                    names.update(m+"."+a.name for a in node.names)
                for module in names:
                    normalized=module.removeprefix("playdock.")
                    if normalized in RETIRED_MODULES:
                        findings.append({"path":path,"line":node.lineno,"retired_import":module})
            hit=RETIRED_SYMBOLS & names
            if isinstance(node,(ast.FunctionDef,ast.AsyncFunctionDef,ast.Import,ast.ImportFrom)) and "image_bytes" in names:
                hit.add("image_bytes")
            if isinstance(node,ast.Call) and (
                getattr(node.func,"id",None)=="image_bytes" or getattr(node.func,"attr",None)=="image_bytes"):
                hit.add("image_bytes")
            if hit:
                findings.append({"path":path,"line":node.lineno,"retired_symbols":sorted(hit)})
            if isinstance(node,ast.Constant) and isinstance(node.value,str):
                for endpoint in RETIRED_ENDPOINTS:
                    if endpoint in node.value:
                        findings.append({"path":path,"line":node.lineno,"retired_endpoint":endpoint})
    duplicates=[]
    for group in after["duplicate_body_candidates"]:
        prod=[x for x in group if production(x["path"])]
        duplicates.append({"members":group,"production_members":len(prod),
                           "review":("multiple production implementations: inspect before changing"
                                     if len(prod)>1 else "test/experiment parity or independent research; preserve")})
    candidates=[]
    unreachable=[]
    for path,r in after["files"].items():
        if not production(path):
            continue
        for c in r["unused_import_candidates"]:
            candidates.append({"path":path,**c,"review":COMPATIBILITY.get(path,
                "UI protected: do not change automatically" if path in ui else "manual caller and build reference review")})
        if path.startswith("src/playdock/") and not r["entrypoint_reachable"] and not path.endswith("/__init__.py"):
            unreachable.append({"path":path,"incoming":r["incoming"],"review":"static candidate, not proof of dead code"})
    report={"baseline":before["baseline"],"head":after["baseline"],"before":metrics(before),"after":metrics(after),
            "retired_files":retired_files,"retired_findings":findings,
            "ui_protected":len(ui),"ui_changes":ui_changes,
            "experiment_files":sum(p.startswith("experiments/") for p in new),
            "experiment_changes":experiment_changes,
            "remaining_unused_import_candidates":candidates,
            "remaining_unreachable_candidates":unreachable,
            "duplicate_review":duplicates,"compatibility_preserved":COMPATIBILITY,
            "limits":"Static candidates are not confirmed unused. No automated deletion. Protected UI, historical data format and independent experiments remain intact."}
    (out/"final_residual.json").write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8")
    print("FINAL_RESIDUAL_METRICS",json.dumps({"before":report["before"],"after":report["after"]},ensure_ascii=False))
    print("FINAL_RESIDUAL_FINDINGS",json.dumps({"retired_files":retired_files,"retired_findings":findings,
          "ui_changes":ui_changes,"experiment_changes":experiment_changes,"unreachable":unreachable,
          "duplicates":duplicates},ensure_ascii=False))
    assert not retired_files and not findings, "Removed functionality detected"
    assert not ui_changes and not experiment_changes, "Protected source changed"
    assert not after["experiment_edges"] and not after["reachable_experiments"], "Production depends on experiments"
    print("FINAL_RESIDUAL_AUDIT_VERIFIED")

if __name__=="__main__":
    main()
