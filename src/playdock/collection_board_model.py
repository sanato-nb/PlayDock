"""Pure data helpers for the collection overview (safe to test without Qt)."""
from __future__ import annotations


def list_collection_cards(collections: list[dict], games: list) -> list[dict]:
    available = {g.id for g in games}
    return [
        {
            'id': col['id'], 'name': col['name'],
            'game_ids': [gid for gid in col['game_ids'] if gid in available],
        }
        for col in collections
    ]


def member_games(games: list, game_ids: list[str]) -> list:
    ids = set(game_ids)
    return [g for g in games if g.id in ids]


def unassigned_games(games: list, collection_rows: list[dict]) -> list:
    """여러 모음집의 연결을 모아, 아직 분류되지 않은 게임을 반환한다."""
    assigned_ids = {gid for row in collection_rows for gid in row["game_ids"]}
    return [game for game in games if game.id not in assigned_ids]
