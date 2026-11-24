"""Compare recorded UI contracts and identify changed source blobs."""
import json
from pathlib import Path
import subprocess
import sys
root=Path(__file__).resolve().parents[1]
old,new=(Path(x) for x in sys.argv[1:3])
manifest=json.loads((root/"docs/ui_reference/source_manifest.json").read_text(encoding="utf-8"))
a,b=(json.loads((p/"ui_contract.json").read_text(encoding="utf-8")) for p in (old,new))
changed=[]
for row in manifest["files"]:
    r=subprocess.run(["git","rev-parse","HEAD:"+row["path"]],cwd=root,capture_output=True,text=True)
    if r.returncode or r.stdout.strip()!=row["sha"]:
        changed.append(row["path"])
print("UI_SOURCE_CHANGED_REVIEW",json.dumps(changed,ensure_ascii=False))
differences=[k for k in a if a[k]!=b.get(k)]
report={"baseline":manifest["baseline"],"changed_reference_files":changed,"contract_differences":differences,
        "note":"Screenshots retained for manual review. Offscreen captures do not establish native frame or pixel-perfect equivalence."}
(new/"comparison.json").write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8")
assert not differences, "UI contract changed: "+", ".join(differences)
print("UI_CONTRACT_MATCH")
