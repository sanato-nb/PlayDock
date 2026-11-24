"""Verify production lookup provenance and absence of experiment imports."""
from __future__ import annotations
import ast
import json
from pathlib import Path
from audit_import_cleanup import tree, source
from audit_source import git

BASELINE = "535cdced1e890562545658d7c3ae4fecee67e47a"
MODULES = ("code_only", "detector", "no_api_html", "steam_client", "search_terms")
ORIGIN = "experiments/dlsite_detector/"
TARGET = "src/playdock/integrations/official_lookup/"
CALLERS = {"src/playdock/controllers/metadata.py", "src/playdock/services/catalog_collection_service.py",
           "src/playdock/workers/identity_artwork.py"}

def main():
    before, after = tree(BASELINE), tree("HEAD")
    assert not set(before)-set(after)
    experiments = [p for p in before if p.startswith("experiments/")]
    assert all(before[p]==after[p] for p in experiments)
    copies = []
    for name in MODULES:
        old,new=ORIGIN+name+".py",TARGET+name+".py"
        assert before[old]==after[new], (old,new)
        copies.append(dict(source=old,target=new,sha=after[new]))
    production = [p for p in before if p.startswith("src/playdock/") or p in
        {"app.py","title_editor.py","title_editor_entry.py","setup_wizard.py","uninstall_wizard.py","requirements.txt"}]
    changed = {p for p in production if before[p]!=after[p]}
    assert changed==CALLERS, changed
    for p in changed:
        assert source(BASELINE,p).replace("experiments.dlsite_detector.code_only",
            "integrations.official_lookup.code_only")==source("HEAD",p),p
    findings = []
    for p in sorted(after):
        if not p.endswith(".py") or not (p.startswith("src/playdock/") or p in production):
            continue
        for node in ast.walk(ast.parse(source("HEAD",p),filename=p)):
            modules = []
            if isinstance(node,ast.Import):
                modules = [a.name for a in node.names]
            elif isinstance(node,ast.ImportFrom):
                modules = [node.module or ""]
            for module in modules:
                if module=="experiments" or module.startswith("experiments."):
                    findings.append(dict(path=p,line=node.lineno,module=module))
            if isinstance(node,ast.Constant) and isinstance(node.value,str):
                if node.value.startswith("experiments."):
                    findings.append(dict(path=p,line=node.lineno,module=node.value))
    report=dict(baseline=BASELINE,head=git("rev-parse","HEAD").decode().strip(),
        promoted=copies,unchanged_experiment_files=len(experiments),changed_callers=sorted(changed),
        production_experiment_imports=findings)
    out=Path("audit_output");out.mkdir(exist_ok=True)
    (out/"official_lookup_isolation.json").write_text(json.dumps(report,indent=2),encoding="utf-8")
    print(json.dumps(report,indent=2))
    assert not findings,findings
    print("OFFICIAL_LOOKUP_ISOLATION_VERIFIED")

if __name__=="__main__":
    main()
