"""모음집 선택창에서 요청한 데이터 변경을 CollectionStore로 전달한다."""
from __future__ import annotations


class CollectionMembershipActions:
    def __init__(self, collections):
        self.collections = collections

    def choices_for_game(self, game_id: str):
        return [
            (record["id"], record["name"], game_id in record["game_ids"])
            for record in self.collections.list()
        ]

    def create(self, name: str) -> tuple[str, str]:
        collection_id = self.collections.create(name)
        return collection_id, name.strip()

    def save_memberships(self, game_id: str, selected_ids: set[str]) -> None:
        self.collections.set_game_memberships(game_id, selected_ids)
