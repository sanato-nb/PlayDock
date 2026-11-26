"""Compare identical synthetic workloads on the same Windows runner."""
import json
from pathlib import Path
import statistics
import sys

old, new = (json.loads(Path(p).read_text(encoding="utf-8")) for p in sys.argv[1:3])
for key in ("python", "qt", "os", "count", "platform", "scale"):
    assert old[key] == new[key], key
assert old["measurements"].keys() == new["measurements"].keys()
rows = {}
for key, a in old["measurements"].items():
    b = new["measurements"][key]
    assert a["digest"] == b["digest"], key
    rows[key] = {"before_ms": a["median_ms"], "after_ms": b["median_ms"],
                 "change_pct": 100 * (b["median_ms"] / a["median_ms"] - 1) if a["median_ms"] else None,
                 "before_cpu_ms": statistics.median(a["cpu_ms"]),
                 "after_cpu_ms": statistics.median(b["cpu_ms"]),
                 "before_rss_mb": statistics.median(a["rss_mb"]),
                 "after_rss_mb": statistics.median(b["rss_mb"])}
assert old["event_loop_closed"] and new["event_loop_closed"]
assert old["settings_menu"] == ["폴더 설정", "데이터 관리", "라이브러리 속성", "DB 상태 확인"]
assert new["settings_menu"] == old["settings_menu"]
assert old["support_button"] is None and new["support_button"] == "♡ 개발자 후원"
report = {"count": old["count"], "baseline": old["commit"], "current": new["commit"],
          "startup_window_ms": [old["startup_window_ms"], new["startup_window_ms"]],
          "import_ms": [old["import_ms"], new["import_ms"]],
          "rss_after_window_mb": [old["rss_after_window_mb"], new["rss_after_window_mb"]],
          "detail_counts": [old["detail_operation_counts"], new["detail_operation_counts"]],
          "same_operation_results": True, "approved_topbar_change": "♡ 개발자 후원", "operations": rows}
Path(sys.argv[3]).write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
print("STAGE9_COMPARISON", json.dumps(report, ensure_ascii=False))
