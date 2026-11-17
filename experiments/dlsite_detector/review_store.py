"""분리형 검색·이름 변경 검토 DB. PlayDock 본체 DB를 직접 건드리지 않는다.

검색 분류와 화면 표시 이름·압축파일 표시 정보는 SQLite에 저장한다.
압축파일 자체의 이름/내용/저장 경로는 결코 변경하지 않는다.
"""
from __future__ import annotations

from contextlib import closing, contextmanager
from datetime import datetime, timezone
from pathlib import Path
import json
import re
import sqlite3

from .pipeline import SearchDecision


GAME_ID = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
CATEGORIES = frozenset({
    "confirmed_game", "suspected_non_game", "internet_confirmed_game",
    "lookup_unavailable", "manual_game", "manual_non_game",
})
EDITABLE_FIELDS = {
    "display_name": "display_name",
    "archive_label": "archive_label",
}


def _stamp() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _name(value: str, *, archive: bool = False) -> str:
    value = (value or "").strip()
    if not 1 <= len(value) <= 240 or any(ord(ch) < 32 for ch in value):
        raise ValueError("이름은 한 줄 1~240자로 입력해야 합니다.")
    if archive and any(ch in value for ch in "/\\:"):
        raise ValueError("압축파일 표시 이름에는 경로 구분자나 콜론을 사용할 수 없습니다.")
    return value


class ReviewStore:
    def __init__(self, path: Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS games (
                    game_id TEXT PRIMARY KEY,
                    original_name TEXT NOT NULL,
                    display_name TEXT NOT NULL,
                    original_archive_name TEXT NOT NULL,
                    archive_label TEXT NOT NULL,
                    original_archive_size INTEGER,
                    classification TEXT NOT NULL DEFAULT 'lookup_unavailable',
                    classification_source TEXT NOT NULL DEFAULT 'automatic',
                    automatic_status TEXT NOT NULL DEFAULT '',
                    classification_reason TEXT NOT NULL DEFAULT '',
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS classifications (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    game_id TEXT NOT NULL REFERENCES games(game_id),
                    before_status TEXT NOT NULL,
                    after_status TEXT NOT NULL,
                    source TEXT NOT NULL,
                    reason TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS name_changes (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    game_id TEXT NOT NULL REFERENCES games(game_id),
                    field TEXT NOT NULL CHECK(field IN ('display_name', 'archive_label')),
                    before_name TEXT NOT NULL,
                    after_name TEXT NOT NULL,
                    state TEXT NOT NULL DEFAULT 'pending'
                        CHECK(state IN ('pending', 'applied', 'cancelled')),
                    created_at TEXT NOT NULL,
                    applied_at TEXT
                );
                CREATE INDEX IF NOT EXISTS ix_names_game ON name_changes(game_id, id);
                CREATE TABLE IF NOT EXISTS search_runs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    game_id TEXT NOT NULL REFERENCES games(game_id),
                    status TEXT NOT NULL,
                    proposed_title TEXT NOT NULL,
                    dlsite_status TEXT NOT NULL,
                    dlsite_code TEXT NOT NULL,
                    web_checked INTEGER NOT NULL,
                    evidence_json TEXT NOT NULL,
                    reason TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS ix_search_game ON search_runs(game_id, id);
            """)

    @contextmanager
    def connect(self):
        with closing(sqlite3.connect(self.path)) as db:
            db.row_factory = sqlite3.Row
            db.execute("PRAGMA foreign_keys=ON")
            with db:
                yield db

    @staticmethod
    def _validate_id(game_id: str):
        if not isinstance(game_id, str) or not GAME_ID.fullmatch(game_id):
            raise ValueError("게임 ID는 영문·숫자·하이픈·밑줄만 허용합니다.")

    def add_game(self, game_id: str, original_name: str, archive_filename: str,
                 *, archive_size: int | None = None):
        """첫 등록 때 원본 이름을 불변 스냅샷으로 저장한다."""
        self._validate_id(game_id)
        original_name = _name(original_name)
        archive_filename = _name(archive_filename, archive=True)
        if archive_size is not None and (not isinstance(archive_size, int) or archive_size < 0):
            raise ValueError("압축파일 크기가 올바르지 않습니다.")
        with self.connect() as db:
            db.execute("""
                INSERT INTO games (
                    game_id, original_name, display_name,
                    original_archive_name, archive_label, original_archive_size, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(game_id) DO NOTHING
            """, (game_id, original_name, original_name,
                  archive_filename, archive_filename, archive_size, _stamp()))

    def get_game(self, game_id: str) -> dict | None:
        with self.connect() as db:
            row = db.execute("SELECT * FROM games WHERE game_id=?", (game_id,)).fetchone()
            return dict(row) if row else None

    def all_games(self) -> list[dict]:
        with self.connect() as db:
            return [dict(row) for row in db.execute("SELECT * FROM games ORDER BY game_id")]

    def save_search_result(self, game_id: str, result: SearchDecision):
        if result.status not in CATEGORIES - {"manual_game", "manual_non_game"}:
            raise ValueError("지원하지 않는 자동 판별 결과입니다.")
        with self.connect() as db:
            row = db.execute("SELECT classification, classification_source FROM games WHERE game_id=?",
                             (game_id,)).fetchone()
            if not row:
                raise KeyError("등록되지 않은 게임입니다.")
            old_status, source = row["classification"], row["classification_source"]
            # 수동 판정을 자동 검색이 무단 덮어쓰지 않는다.
            next_status = old_status if source == "manual" else result.status
            if source == "manual":
                db.execute("""
                    UPDATE games SET automatic_status=?, updated_at=? WHERE game_id=?
                """, (result.status, _stamp(), game_id))
            else:
                db.execute("""
                    UPDATE games SET classification=?, automatic_status=?,
                        classification_reason=?, updated_at=? WHERE game_id=?
                """, (next_status, result.status, result.reason, _stamp(), game_id))
            db.execute("""
                INSERT INTO classifications(game_id, before_status, after_status, source, reason, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (game_id, old_status, next_status, "automatic", result.reason, _stamp()))
            db.execute("""
                INSERT INTO search_runs(game_id, status, proposed_title, dlsite_status,
                        dlsite_code, web_checked, evidence_json, reason, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (game_id, result.status, result.proposed_title, result.dlsite_status,
                  result.dlsite_code, int(result.web_checked),
                  json.dumps([row.__dict__ for row in result.evidence],
                             ensure_ascii=False), result.reason, _stamp()))

    def manual_classify(self, game_id: str, status: str, *, reason: str = "사용자 선택"):
        if status not in CATEGORIES:
            raise ValueError("분류 상태가 잘못됐습니다.")
        with self.connect() as db:
            row = db.execute("SELECT classification FROM games WHERE game_id=?", (game_id,)).fetchone()
            if not row:
                raise KeyError("등록되지 않은 게임입니다.")
            db.execute("""
                UPDATE games SET classification=?, classification_source='manual',
                    classification_reason=?, updated_at=? WHERE game_id=?
            """, (status, reason[:500], _stamp(), game_id))
            db.execute("""
                INSERT INTO classifications(game_id, before_status, after_status, source, reason, created_at)
                VALUES (?, ?, ?, 'manual', ?, ?)
            """, (game_id, row["classification"], status, reason[:500], _stamp()))

    def list_unresolved(self) -> list[dict]:
        return self._list_by_status(("lookup_unavailable",))

    def list_suspected_non_game(self) -> list[dict]:
        return self._list_by_status(("suspected_non_game", "manual_non_game"))

    def _list_by_status(self, statuses: tuple[str, ...]) -> list[dict]:
        placeholders = ",".join("?" for _ in statuses)
        with self.connect() as db:
            return [dict(row) for row in db.execute(
                f"SELECT * FROM games WHERE classification IN ({placeholders}) ORDER BY game_id", statuses)]

    def search_history(self, game_id: str) -> list[dict]:
        with self.connect() as db:
            records = [dict(row) for row in db.execute(
                "SELECT * FROM search_runs WHERE game_id=? ORDER BY id", (game_id,))]
        for row in records:
            row["evidence"] = json.loads(row.pop("evidence_json"))
        return records

    def classification_history(self, game_id: str) -> list[dict]:
        with self.connect() as db:
            return [dict(row) for row in db.execute(
                "SELECT * FROM classifications WHERE game_id=? ORDER BY id", (game_id,))]

    def stage_name_change(self, game_id: str, new_name: str,
                          *, field: str = "display_name") -> int:
        if field not in EDITABLE_FIELDS:
            raise ValueError("이름을 변경할 수 없는 필드입니다.")
        new_name = _name(new_name, archive=field == "archive_label")
        with self.connect() as db:
            row = db.execute(f"SELECT {field} FROM games WHERE game_id=?", (game_id,)).fetchone()
            if row is None:
                raise KeyError("등록되지 않은 게임입니다.")
            before = row[field]
            if before == new_name:
                raise ValueError("변경 전후 이름이 동일합니다.")
            # 보류 중 요청은 항상 사용자가 먼저 결정해야 한다.
            existing = db.execute(
                "SELECT 1 FROM name_changes WHERE game_id=? AND field=? AND state='pending'",
                (game_id, field)).fetchone()
            if existing:
                raise ValueError("처리되지 않은 이름 변경 요청이 있습니다.")
            cursor = db.execute("""
                INSERT INTO name_changes(game_id, field, before_name, after_name, created_at)
                VALUES (?, ?, ?, ?, ?)
            """, (game_id, field, before, new_name, _stamp()))
            return cursor.lastrowid

    def apply_name_change(self, change_id: int) -> dict:
        """DB에 이미 기록된 전/후 값을 확인 후 현재 *표시값*에 적용한다."""
        with self.connect() as db:
            row = db.execute("SELECT * FROM name_changes WHERE id=?", (change_id,)).fetchone()
            if not row or row["state"] != "pending":
                raise ValueError("승인 대기 중인 이름 변경 요청이 아닙니다.")
            field = row["field"]
            current = db.execute(
                f"SELECT {field} FROM games WHERE game_id=?", (row["game_id"],)).fetchone()
            if current is None or current[field] != row["before_name"]:
                raise RuntimeError("이름이 요청 시점 이후 바뀌었습니다. 다시 요청하세요.")
            db.execute(f"UPDATE games SET {field}=?, updated_at=? WHERE game_id=?",
                       (row["after_name"], _stamp(), row["game_id"]))
            db.execute("UPDATE name_changes SET state='applied', applied_at=? WHERE id=?",
                       (_stamp(), change_id))
            return dict(row)

    def cancel_name_change(self, change_id: int):
        with self.connect() as db:
            result = db.execute(
                "UPDATE name_changes SET state='cancelled' WHERE id=? AND state='pending'",
                (change_id,))
            if result.rowcount != 1:
                raise ValueError("취소 가능한 요청이 아닙니다.")

    def restore_original_name(self, game_id: str, *, field: str = "display_name") -> int | None:
        """원본으로 복구할 때도 새로운 전/후 이력으로 먼저 DB에 기록한다."""
        target_field = {
            "display_name": "original_name",
            "archive_label": "original_archive_name",
        }.get(field)
        if not target_field:
            raise ValueError("지원하지 않는 복구 필드입니다.")
        row = self.get_game(game_id)
        if row is None:
            raise KeyError("등록되지 않은 게임입니다.")
        if row[field] == row[target_field]:
            return None
        change_id = self.stage_name_change(game_id, row[target_field], field=field)
        self.apply_name_change(change_id)
        return change_id

    def name_history(self, game_id: str) -> list[dict]:
        with self.connect() as db:
            return [dict(row) for row in db.execute(
                "SELECT * FROM name_changes WHERE game_id=? ORDER BY id", (game_id,))]
