"""Compare same-run benchmark output; fail on functional divergence."""
import json
from pathlib import Path
import sys
a,b=(json.loads(Path(p).read_text(encoding="utf-8")) for p in sys.argv[1:3])
assert a["python"]==b["python"] and a["qt"]==b["qt"]
assert a["measurements"].keys()==b["measurements"].keys()
rows={}
for key,old in a["measurements"].items():
    new=b["measurements"][key]
    assert old["digest"]==new["digest"], f"Output changed: {key}"
    rows[key]={"baseline_median_ms":old["median_ms"],"optimized_median_ms":new["median_ms"],
               "change_pct":100*(new["median_ms"]/old["median_ms"]-1) if old["median_ms"] else None}
assert (a["title_meta_reads"],b["title_meta_reads"])==(3000,1000)
assert a["db_reads"]=={"connections":2000,"selects":2000}
assert b["db_reads"]=={"connections":1,"selects":3}
assert a["card_pixels"]==[1600,520] and b["card_pixels"]==[768,250]
report={"baseline":a["commit"],"optimized":b["commit"],"same_output":True,"timings":rows,
        "title_meta_reads":[a["title_meta_reads"],b["title_meta_reads"]],
        "db_reads":[a["db_reads"],b["db_reads"]],
        "card_rgba_bytes_estimate":[a["card_rgba_bytes_estimate"],b["card_rgba_bytes_estimate"]]}
Path(sys.argv[3]).write_text(json.dumps(report,indent=2,ensure_ascii=False),encoding="utf-8")
print("PERFORMANCE_COMPARISON_VERIFIED")
print(json.dumps(report,ensure_ascii=False))
