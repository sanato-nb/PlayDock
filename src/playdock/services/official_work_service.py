"""Resolve explicit DLsite/Steam identities and display unified work details.

No network calls, no archive contents read, no guessing Steam from bare numbers.
"""
from __future__ import annotations
import re
from database.official_catalog import _valid_identity

STEAM_MARKED = re.compile(
    r"(?i)(?<![a-z0-9])(?:steam(?:[\s_-]*(?:app[\s_-]*id|id))?"
    r"|app[\s_-]*id)[\s:=#_-]*([1-9]\d{2,9})(?![a-z0-9])"
)


def explicit_work_identity(library, game):
    meta = library.meta(game)
    # A manually cleared ID must override all automatic file-name guesses.
    if "product_code" in meta and not meta.get("product_code"):
        return None
    # Explicit store+code wins; retained for future generic code-editor UI.
    store = str(meta.get("product_store") or "").strip().lower()
    if store == "steam":
        code = str(meta.get("product_code") or meta.get("steam_app_id") or "").strip()
        if code.isdigit() and code[0] != "0" and 3 <= len(code) <= 10:
            return ("steam", code)
    if store == "dlsite":
        code = library.product_code(game)
        return ("dlsite", code) if code else None
    code = library.product_code(game)
    if code:
        return ("dlsite", code)
    candidates = []
    if meta.get("steam_app_id"):
        candidates.append("Steam " + str(meta["steam_app_id"]))
    candidates.extend((game.archive.name if game.archive else "", game.name))
    for name in candidates:
        match = STEAM_MARKED.search(name)
        if match:
            return ("steam", match.group(1))
    return None


def official_metadata_for_game(library, game, db):
    identity = explicit_work_identity(library, game)
    if not identity:
        return None
    store, code = identity
    record = db.get_official_work(store, code)
    return record if record and _valid_identity(store, code, record["page_url"]) else None


def official_info_rows(record):
    if not record:
        return []
    store = "DLsite" if record["store"] == "dlsite" else "Steam"
    rows = [
        ("공식 판매처", store),
        ("공식 품번 / App ID", record["code"]),
        ("공식 작품명", record["title"]),
        ("공식 작품 종류·분류", record.get("category") or "정보 없음"),
        ("공식 작품 페이지", record["page_url"]),
    ]
    if record.get("maker"):
        rows.append(("제작사", record["maker"]))
    if record.get("release_date"):
        rows.append(("발매일", record["release_date"]))
    if record.get("tags"):
        rows.append(("장르·태그", ", ".join(record["tags"][:8])))
    return rows
