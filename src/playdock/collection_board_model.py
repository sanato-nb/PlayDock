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
