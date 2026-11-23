"""Read-only inspection of PlayDock's two SQLite databases.

No changes are made to either DB and a missing scanner database is never
created. Intended for the Settings > DB status screen and offline diagnostics.
"""
from __future__ import annotations

from contextlib import closing
from pathlib import Path
import sqlite3

from database.official_catalog import default_catalog_path


MAIN_TABLES = ("works", "work_titles", "work_tags", "work_images",
               "library_links", "official_works")
SCAN_TABLES = ("official_works",)


def _inspect(path: Path, expected_tables: tuple[str, ...]) -> dict:
    result = {"path": str(path), "exists": False, "ok": False,
              "version": None, "counts": {}, "by_store": {}, "error": ""}
    try:
        if path.is_symlink():
            result["error"] = "연결 파일(심볼릭 링크)이므로 읽지 않았습니다."
            return result
        if not path.is_file():
            result["error"] = "파일 없음"
            return result
        result["exists"] = True
        with closing(sqlite3.connect(path.resolve().as_uri() + "?mode=ro",
                                     uri=True, timeout=3)) as connection:
            connection.execute("PRAGMA query_only=ON")
            result["version"] = connection.execute("PRAGMA user_version").fetchone()[0]
            checked = connection.execute("PRAGMA quick_check(1)").fetchone()
            if checked is None or checked[0] != "ok":
                result["error"] = "SQLite 검사 실패"
                return result
            existing = {row[0] for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table'")}
            for table in expected_tables:
                if table in existing:
                    # Table names come only from MAIN_TABLES/SCAN_TABLES constants.
                    result["counts"][table] = connection.execute(
                        f"SELECT COUNT(*) FROM {table}").fetchone()[0]
                else:
                    result["counts"][table] = None
            if "official_works" in existing:
                result["by_store"] = dict(connection.execute(
                    """SELECT store, COUNT(*) FROM official_works
                       GROUP BY store""").fetchall())
            result["ok"] = True
    except (OSError, sqlite3.Error, ValueError) as exc:
        result["error"] = f"읽기 실패: {type(exc).__name__}"
    return result


def database_status(store: str | Path, *, scanner_path: str | Path | None = None) -> dict:
    """Return actual SQLite state, without guessing how many works were imported."""
    main = _inspect(Path(store) / "playdock.db", MAIN_TABLES)
    source = _inspect(Path(scanner_path) if scanner_path is not None
                      else default_catalog_path(), SCAN_TABLES)
    return {"main": main, "scanner": source}


def _count(info: dict, table: str) -> str:
    count = info["counts"].get(table)
    return "테이블 없음" if count is None else f"{count:,}건"


def format_database_status(report: dict, *, live_games: int | None = None) -> str:
    """Human-readable status for the in-app dialog; fields remain read-only."""
    main, scanner = report["main"], report["scanner"]
    lines = ["[PlayDock 본체 DB]", f"경로: {main['path']}"]
    if main["ok"]:
        lines.extend([
            f"SQLite 스키마 버전: {main['version']} (현재 코드: v2)",
            f"기존 작품 정보(works): {_count(main, 'works')}",
            f"작품 연결 기록(library_links): {_count(main, 'library_links')}",
            f"공식 작품정보(official_works): {_count(main, 'official_works')}",
            f"  DLsite: {main['by_store'].get('dlsite', 0):,}건  /  Steam: {main['by_store'].get('steam', 0):,}건",
            "SQLite 빠른 무결성 검사: 정상",
        ])
    else:
        lines.append(f"상태: {main['error']}")
    if live_games is not None:
        lines.append(f"현재 화면 라이브러리: {live_games:,}개 게임")
    lines.extend(["", "[정체 판독기 원본 DB]", f"경로: {scanner['path']}"])
    if scanner["ok"]:
        lines.extend([
            f"공식 작품정보: {_count(scanner, 'official_works')}",
            f"  DLsite: {scanner['by_store'].get('dlsite', 0):,}건  /  Steam: {scanner['by_store'].get('steam', 0):,}건",
            "SQLite 빠른 무결성 검사: 정상",
        ])
    else:
        lines.append(f"상태: {scanner['error']}")
    lines.extend(["", "PlayDock 시작/새로고침 시 공식정보를 본체 DB에 가져옵니다.",
                  "작품 연결 기록 수는 공식 확인 작품 수와 다를 수 있습니다.",
                  "이 화면은 읽기 전용이며 DB·압축파일을 수정하지 않습니다."])
    return "\n".join(lines)
