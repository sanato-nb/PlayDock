"""배너·아이콘 변경의 'DB 우선 기록 → 실제 파일 적용' 독립 실험 계층.

사용자가 승인하지 않으면 현재 파일을 수정하지 않는다. 기존 파일 원본은
DB의 before_image BLOB에 보관해 적용 뒤에도 복구할 수 있다.
"""
from __future__ import annotations

from contextlib import closing, contextmanager
from datetime import datetime, timezone
from hashlib import sha256
from io import BytesIO
from pathlib import Path
import os
import sqlite3
import tempfile

from PIL import Image, UnidentifiedImageError

from .review_store import ReviewStore


MAX_IMAGE = 16 * 1024 * 1024
MAX_PIXELS = 36_000_000
KINDS = {"hero": "hero.png", "icon": "icon.png"}


def _stamp() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _digest(content: bytes | None) -> str | None:
    return sha256(content).hexdigest() if content is not None else None


def _read_optional(path: Path) -> bytes | None:
    if path.is_symlink():
        raise ValueError("링크된 이미지 파일은 변경하지 않습니다.")
    if not path.exists():
        return None
    if not path.is_file() or path.stat().st_size > MAX_IMAGE:
        raise ValueError("이미지 파일이 아니거나 안전 크기를 초과했습니다.")
    return path.read_bytes()


def _validate_png(content: bytes):
    if not isinstance(content, bytes) or not (8 <= len(content) <= MAX_IMAGE):
        raise ValueError("이미지 크기가 올바르지 않습니다.")
    if not content.startswith(b"\x89PNG\r\n\x1a\n"):
        raise ValueError("배너·아이콘은 PNG 이미지여야 합니다.")
    try:
        with Image.open(BytesIO(content)) as im:
            if im.format != "PNG" or im.width * im.height > MAX_PIXELS:
                raise ValueError("PNG 형식이나 이미지 해상도가 허용 범위를 초과했습니다.")
            im.verify()
    except (UnidentifiedImageError, OSError, SyntaxError) as exc:
        raise ValueError("PNG 데이터를 해석할 수 없습니다.") from exc


def _replace_atomic(path: Path, content: bytes):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, staging = tempfile.mkstemp(prefix=".playdock-preview-", suffix=".png", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(staging, path)
    finally:
        if os.path.exists(staging):
            os.unlink(staging)


class ArtworkStaging:
    def __init__(self, database_path: Path):
        self.registry = ReviewStore(database_path)
        self.path = Path(database_path)
        with self.connect() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS artwork_changes (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    game_id TEXT NOT NULL REFERENCES games(game_id),
                    kind TEXT NOT NULL CHECK(kind IN ('hero', 'icon')),
                    before_image BLOB,
                    before_sha256 TEXT,
                    after_image BLOB NOT NULL,
                    after_sha256 TEXT NOT NULL,
                    source TEXT NOT NULL DEFAULT '',
                    state TEXT NOT NULL DEFAULT 'pending'
                        CHECK(state IN ('pending', 'applied', 'restored', 'cancelled')),
                    created_at TEXT NOT NULL,
                    applied_at TEXT
                );
                CREATE INDEX IF NOT EXISTS ix_artwork_game
                    ON artwork_changes(game_id, kind, id);
            """)

    @contextmanager
    def connect(self):
        with closing(sqlite3.connect(self.path)) as db:
            db.row_factory = sqlite3.Row
            db.execute("PRAGMA foreign_keys=ON")
            with db:
                yield db

    @staticmethod
    def _target(game_id: str, kind: str, cache_root: Path) -> Path:
        ReviewStore._validate_id(game_id)
        if kind not in KINDS:
            raise ValueError("이미지는 배너(hero) 또는 아이콘(icon)만 변경할 수 있습니다.")
        root = Path(cache_root)
        if root.is_symlink() or (root / game_id).is_symlink():
            raise ValueError("링크된 이미지 캐시 폴더는 변경하지 않습니다.")
        return root / game_id / KINDS[kind]

    def stage_image(self, game_id: str, kind: str, image_png: bytes,
                    *, cache_root: Path, source: str = "") -> int:
        """이미지 원본/변경본을 먼저 DB에 저장한다. 실제 PNG는 변경하지 않는다."""
        _validate_png(image_png)
        target = self._target(game_id, kind, cache_root)
        if self.registry.get_game(game_id) is None:
            raise KeyError("등록되지 않은 게임입니다.")
        before = _read_optional(target)
        with self.connect() as db:
            pending = db.execute("""
                SELECT 1 FROM artwork_changes
                WHERE game_id=? AND kind=? AND state='pending'
            """, (game_id, kind)).fetchone()
            if pending:
                raise ValueError("기존 이미지 변경 요청을 먼저 적용하거나 취소하세요.")
            if before == image_png:
                raise ValueError("현재 이미지와 새 이미지가 같습니다.")
            cursor = db.execute("""
                INSERT INTO artwork_changes(
                    game_id, kind, before_image, before_sha256,
                    after_image, after_sha256, source, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (game_id, kind, before, _digest(before), image_png,
                  _digest(image_png), source[:2048], _stamp()))
            return cursor.lastrowid

    def get_change(self, change_id: int) -> dict | None:
        with self.connect() as db:
            row = db.execute("""
                SELECT id, game_id, kind, before_sha256, after_sha256,
                       source, state, created_at, applied_at
                FROM artwork_changes WHERE id=?
            """, (change_id,)).fetchone()
            return dict(row) if row else None

    def list_changes(self, game_id: str) -> list[dict]:
        with self.connect() as db:
            return [dict(row) for row in db.execute("""
                SELECT id, game_id, kind, before_sha256, after_sha256,
                       source, state, created_at, applied_at
                FROM artwork_changes WHERE game_id=? ORDER BY id
            """, (game_id,))]

    def _full_change(self, change_id: int):
        with self.connect() as db:
            row = db.execute("SELECT * FROM artwork_changes WHERE id=?", (change_id,)).fetchone()
            return dict(row) if row else None

    def _mark(self, change_id: int, before_status: str, after_status: str):
        with self.connect() as db:
            cursor = db.execute("""
                UPDATE artwork_changes SET state=?, applied_at=?
                WHERE id=? AND state=?
            """, (after_status, _stamp(), change_id, before_status))
            if cursor.rowcount != 1:
                raise RuntimeError("이미지 변경 상태가 다른 작업에서 바뀌었습니다.")

    def apply_image(self, change_id: int, *, cache_root: Path):
        """DB에 이미 등록된 PNG만 파일에 반영한다. 충돌은 덮어쓰지 않는다."""
        change = self._full_change(change_id)
        if change is None or change["state"] != "pending":
            raise ValueError("승인 대기 중인 이미지 요청이 아닙니다.")
        target = self._target(change["game_id"], change["kind"], cache_root)
        current = _read_optional(target)
        if _digest(current) == change["after_sha256"]:
            # 파일 반영 직후 정전/DB 오류가 있었던 경우 재시도로 상태를 복구한다.
            self._mark(change_id, "pending", "applied")
            return
        if _digest(current) != change["before_sha256"]:
            raise RuntimeError("이미지가 요청 시점 이후 변경됐습니다. 자동 덮어쓰기를 중단합니다.")
        _replace_atomic(target, change["after_image"])
        self._mark(change_id, "pending", "applied")

    def restore_image(self, change_id: int, *, cache_root: Path):
        """DB에 보관된 이전 이미지로 되돌린다. 다른 변경이 있으면 거부한다."""
        change = self._full_change(change_id)
        if change is None or change["state"] != "applied":
            raise ValueError("복원 가능한 적용 이력이 아닙니다.")
        target = self._target(change["game_id"], change["kind"], cache_root)
        if _digest(_read_optional(target)) != change["after_sha256"]:
            raise RuntimeError("이미지가 이후에 바뀌어서 이전 버전을 덮어쓸 수 없습니다.")
        if change["before_image"] is None:
            target.unlink(missing_ok=True)
        else:
            _replace_atomic(target, change["before_image"])
        self._mark(change_id, "applied", "restored")

    def cancel_image(self, change_id: int):
        """대기 중 요청을 취소하되 원본 파일은 그대로 유지한다."""
        self._mark(change_id, "pending", "cancelled")
