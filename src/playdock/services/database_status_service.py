"""Read-only status for one shared PlayDock/data/playdock.db SQLite database."""
from __future__ import annotations
from contextlib import closing
from pathlib import Path
import sqlite3


def database_status(store: str | Path, *, scanner_path=None):
    # scanner_path is ignored for API compatibility: scanner writes this DB now.
    path = Path(store) / "playdock.db"
    result = {"path": str(path), "exists": False, "ok": False,
              "version": None, "counts": {}, "by_store": {}, "error": ""}
    try:
        if path.is_symlink() or path.is_junction():
            result["error"] = "연결 파일(심볼릭 링크)이므로 읽지 않았습니다."
            return {"main": result}
        if not path.is_file():
            result["error"] = "파일 없음"
            return {"main": result}
        result["exists"] = True
        with closing(sqlite3.connect(path.resolve().as_uri() + "?mode=ro",
                                     uri=True, timeout=4)) as con:
            con.execute("PRAGMA query_only=ON")
            result["version"] = con.execute("PRAGMA user_version").fetchone()[0]
            checked = con.execute("PRAGMA quick_check(1)").fetchone()
            if not checked or checked[0] != "ok":
                result["error"] = "SQLite 무결성 검사 실패"
                return {"main": result}
            names = {x[0] for x in con.execute(
                "SELECT name FROM sqlite_master WHERE type='table'")}
            for table in ("works", "library_links"):
                result["counts"][table] = (
                    con.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
                    if table in names else None)
            if "works" in names and "store" in {row[1] for row in
                                                  con.execute("PRAGMA table_info(works)")}:
                result["by_store"] = dict(con.execute(
                    "SELECT store,COUNT(*) FROM works GROUP BY store").fetchall())
            result["ok"] = True
    except (OSError, sqlite3.Error, ValueError) as exc:
        result["error"] = f"읽기 실패: {type(exc).__name__}"
    return {"main": result}


def format_database_status(report, *, live_games=None):
    info = report["main"]
    lines = ["[통합 PlayDock DB]", f"경로: {info['path']}"]
    if info["ok"]:
        lines.extend([
            f"SQLite 스키마 버전: {info['version']} (현재 코드: v3)",
            f"공식 작품정보(works): {info['counts'].get('works') or 0:,}건",
            f"  DLsite: {info['by_store'].get('dlsite', 0):,}건"
            f"  /  Steam: {info['by_store'].get('steam', 0):,}건",
            f"게임 연결 기록(library_links): {info['counts'].get('library_links') or 0:,}건",
            "SQLite 빠른 무결성 검사: 정상",
        ])
    else:
        lines.append(f"상태: {info['error']}")
    if live_games is not None:
        lines.append(f"현재 화면 라이브러리: {live_games:,}개 게임")
    lines.extend([
        "", "PlayDock 본체와 정체 판독기가 같은 works 테이블을 사용합니다.",
        "이전 공식정보 DB가 있다면 최초 실행 시 데이터를 한 번만 이전합니다.",
        "이 화면은 읽기 전용이며 DB·게임 파일을 변경하지 않습니다.",
    ])
    return "\n".join(lines)
