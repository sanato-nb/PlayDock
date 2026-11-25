"""Small public official-lookup sample; no local data or credentials."""
from pathlib import Path
import argparse
import json
import sys
import time

ap = argparse.ArgumentParser()
ap.add_argument("--source", type=Path, required=True)
ap.add_argument("--output", type=Path, required=True)
a = ap.parse_args()
sys.path[:0] = [str(a.source.resolve() / "src/playdock"), str(a.source.resolve())]
from integrations.official_lookup.code_only import InputItem, check
rows = []
# Steam public sample; DLsite uses the same example code as existing fixtures.
# No assertion of registration if a service cannot confirm the sample.
for label in ("[Steam 620]", "[RJ123456]"):
    start = time.perf_counter()
    result = check(InputItem(label, "archive"))
    rows.append({"sample": label, "outcome": result.status,
                 "attempted": result.attempted_stores, "selected": result.selected_store,
                 "verified": [{"store": w.store, "code": w.code} for w in result.works
                              if w.status == "verified"],
                 "warnings": result.warnings, "elapsed_ms": (time.perf_counter()-start)*1000})
a.output.parent.mkdir(parents=True, exist_ok=True)
a.output.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
print("STAGE9_ONLINE", json.dumps(rows, ensure_ascii=False))
