"""Bridge between local game library and imported scanner metadata.

No scanner dependency, network access, automatic renaming or metadata mutation.
DLsite wins when an explicit code has an imported match; otherwise accept an
explicitly marked Steam App ID from the original archive or game name.
"""
from __future__ import annotations

import re

from database.official_catalog import _valid_identity

STEAM_MARKED = re.compile(
    r"(?i)(?<![a-z0-9])(?:steam(?:[\s_-]*(?:app[\s_-]*id|id))?"
    r"|app[\s_-]*id)[\s:=#_-]*([1-9]\d{2,9})(?![a-z0-9])"
)


def official_metadata_for_game(library, game, db) -> dict | None:
    """Never infer a store ID from an unmarked version/build number."""
    code = library.product_code(game)
    if code:
        record = db.get_official_work("dlsite", code)
        if record and _valid_identity("dlsite", record["product_id"], record["page_url"]):
            return record

    meta = library.meta(game)
    # An explicitly cleared product_code means the user rejected auto-linking.
    # Do not infer another ID from filename or old metadata in that case.
    if "product_code" in meta and not code:
        return None

    sources = [game.archive.name if game.archive else "", game.name]
    manual = meta.get("steam_app_id")
    if manual:
        sources.insert(0, f"Steam {manual}")
    for source in sources:
        for match in STEAM_MARKED.finditer(source):
            app_id = match.group(1)
            record = db.get_official_work("steam", app_id)
            if record and _valid_identity("steam", record["product_id"], record["page_url"]):
                return record
    return None


def official_info_rows(record: dict | None) -> list[tuple[str, str]]:
    if not record:
        return []
    store = "DLsite" if record["store"] == "dlsite" else "Steam"
    return [
        ("공식 판매처", store),
        ("공식 품번 / App ID", record["product_id"]),
        ("공식 작품명", record["official_title"]),
        ("공식 작품 종류·분류", record["category"] or "정보 없음"),
        ("공식 작품 페이지", record["page_url"]),
    ]
