"""Cross-revision source-only data compatibility; no build or binary execution."""
from pathlib import Path
import argparse
import json
import os
import subprocess
import sys
import tempfile

from verify_upgrade_compatibility import prepare, imports, describe, snapshot


def verify_source(source, root, output):
    Library, WorkDatabase, CollectionStore, _, _ = imports(source)
    data = root / "program" / "data"
    expected = json.loads((root / "expected.json").read_text(encoding="utf-8"))
    before = snapshot(data)
    gamefiles = {d: snapshot(root / d) for d in ("archives", "games", "external")}
    library = Library(data)
    db = WorkDatabase(data)
    collections = CollectionStore(data)
    actual = describe(root, library, db, collections)
    assert json.loads(json.dumps(actual, ensure_ascii=False)) == expected
    assert snapshot(data) == before
    assert all(snapshot(root / d) == v for d, v in gamefiles.items())
    # The application refresh also synchronizes explicit IDs; compare meaning
    # and metadata rather than assuming SQLite never rewrites a page.
    db.sync_library(library, library.scan())
    actual = describe(root, library, db, CollectionStore(data))
    assert json.loads(json.dumps(actual, ensure_ascii=False)) == expected
    after = snapshot(data)
    assert {k:v for k,v in after.items() if k != "playdock.db"} == {
        k:v for k,v in before.items() if k != "playdock.db"}
    assert all(snapshot(root / d) == v for d, v in gamefiles.items())
    report = {"source_only": True, "data_reopen": True, "library_refresh": True,
              "preserved_data_files": len(before),
              "preserved_game_files": sum(map(len, gamefiles.values())),
              "games": len(expected["games"]), "collections": len(expected["collections"]),
              "installer_payload_verified": False}
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print("SOURCE_COMPATIBILITY_VERIFIED", json.dumps(report, ensure_ascii=False))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--baseline", type=Path, required=True)
    ap.add_argument("--source", type=Path, required=True)
    ap.add_argument("--output", type=Path, required=True)
    ap.add_argument("--prepare", type=Path)
    args = ap.parse_args()
    if args.prepare:
        prepare(args.baseline.resolve(), args.prepare)
        return
    with tempfile.TemporaryDirectory(prefix="playdock-source-audit-") as temp:
        root = Path(temp)
        subprocess.run([sys.executable, __file__, "--baseline", str(args.baseline.resolve()),
                        "--source", str(args.source.resolve()), "--output", str(args.output.resolve()),
                        "--prepare", str(root)], cwd=args.baseline.resolve(), check=True,
                       env={k:v for k,v in os.environ.items() if k != "PYTHONPATH"})
        verify_source(args.source.resolve(), root, args.output.resolve())


if __name__ == "__main__":
    main()
