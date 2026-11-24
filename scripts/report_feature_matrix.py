"""Report per-feature results from the actual full-suite JUnit report."""
import json
from pathlib import Path
import sys
import xml.etree.ElementTree as ET

root=Path(__file__).resolve().parents[1]
manifest=json.loads((root/"docs/source_audit/25_feature_matrix.json").read_text(encoding="utf-8"))
cases=list(ET.parse(sys.argv[1]).getroot().iter("testcase"))
assert cases,"No pytest results"
def status(case):
    for label in ("failure","error","skipped"):
        if case.find(label) is not None:
            return label
    return "passed"
def counts(items):
    return {label:sum(status(case)==label for case in items) for label in ("passed","failure","error","skipped")}
def matches(case,path):
    module=Path(path).stem
    return module in case.attrib.get("classname","").split(".")
result={"total":counts(cases),"groups":[],"skipped":[{"class":c.attrib.get("classname"),"name":c.attrib.get("name"),
          "reason":c.find("skipped").attrib.get("message","")} for c in cases if status(c)=="skipped"]}
for group in manifest["groups"]:
    missing=[p for p in group["files"] if not any(matches(c,p) for c in cases)]
    selected=[c for c in cases if any(matches(c,p) for p in group["files"])]
    result["groups"].append({**group,"counts":counts(selected),"missing_modules":missing})
out=Path(sys.argv[2]);out.parent.mkdir(parents=True,exist_ok=True)
out.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding="utf-8")
print("FEATURE_MATRIX",json.dumps(result,ensure_ascii=False))
assert not result["total"]["failure"] and not result["total"]["error"]
assert all(not g["missing_modules"] and g["counts"]["passed"]>0 for g in result["groups"])
print("FEATURE_MATRIX_VERIFIED")
