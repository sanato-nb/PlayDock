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


def partition_collection_games(games, collections):
    """Group in input game order with one ID lookup per game.

    A game may belong to multiple collections. Keep separate buckets by row
    index (not collection ID), ignore unavailable IDs, and preserve duplicates
    in the input game sequence. No persistent index or file mutations.
    """
    membership = {}
    buckets = [[] for _ in collections]
    for index, collection in enumerate(collections):
        for game_id in set(collection["game_ids"]):
            membership.setdefault(game_id, []).append(index)
    unassigned = []
    for game in games:
        indexes = membership.get(game.id)
        if indexes:
            for index in indexes:
                buckets[index].append(game)
        else:
            unassigned.append(game)
    return buckets, unassigned
