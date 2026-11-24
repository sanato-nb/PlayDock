"""Verify dialog declarations are relocated without behavioral changes."""
import ast
import collections
import json
from pathlib import Path
from audit_import_cleanup import tree, source
from audit_source import git

BASELINE = "0b65c68c678d85c418d0d77895676101cc874709"
ROOT = "src/playdock/ui/dialogs/"
OLD = ("common", "library", "title")
NEW = ("common","file_dialog","caption","folder_settings","collection_settings",
       "cache_manager","data_manager","library","title_preview","title")

def declarations(ref, names):
    rows = collections.defaultdict(list)
    for name in names:
        path = ROOT+name+".py"
        for node in ast.parse(source(ref,path)).body:
            if isinstance(node,(ast.ClassDef,ast.FunctionDef,ast.AsyncFunctionDef)):
                rows[node.name].append((path,ast.dump(node,include_attributes=False)))
    return rows

def main():
    old,new=declarations(BASELINE,OLD),declarations("HEAD",NEW)
    assert set(old)==set(new),(set(old)-set(new),set(new)-set(old))
    assert all(len(old[k])==len(new[k])==1 and old[k][0][1]==new[k][0][1] for k in old)
    before,after=tree(BASELINE),tree("HEAD")
    assert not set(before)-set(after)
    assert all(before[p]==after[p] for p in before if p.startswith(("experiments/","src/playdock/services/","src/playdock/storage/","src/playdock/models/","src/playdock/database/","src/playdock/workers/")))
    # Detect legacy imports of moved declarations, including test subprocess strings.
    destinations={k:new[k][0][0] for k in new}
    stale=[]
    for p in after:
        if not p.endswith(".py") or p.startswith("scripts/audit_"):
            continue
        for n in ast.walk(ast.parse(source("HEAD",p),filename=p)):
            if isinstance(n,ast.ImportFrom) and (n.module or "").startswith("ui.dialogs."):
                for a in n.names:
                    if a.name in destinations and n.module.replace(".","/")+".py" != destinations[a.name].removeprefix("src/playdock/"):
                        stale.append([p,n.lineno,n.module,a.name])
    report=dict(baseline=BASELINE,head=git("rev-parse","HEAD").decode().strip(),
        declarations=[dict(name=k,old=old[k][0][0],new=new[k][0][0],ast_equal=True) for k in sorted(old)],
        stale_imports=stale)
    out=Path("audit_output");out.mkdir(exist_ok=True)
    (out/"dialog_relocation.json").write_text(json.dumps(report,indent=2),encoding="utf-8")
    print(json.dumps(report,indent=2))
    assert not stale,stale
    print("DIALOG_RELOCATION_VERIFIED",len(old))

if __name__=="__main__":
    main()
