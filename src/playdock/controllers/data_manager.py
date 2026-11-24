"""UI 이벤트와 라이브러리 데이터 서비스 사이의 연결 계층.

입력창, 확인 대화상자, Qt 위젯을 생성하지 않는다.
"""
from __future__ import annotations

from pathlib import Path

from services.cache_service import image_stats, recycle_images
from services.data_service import inventory, backup_data, inspect_backup, restore_data


class DataManagementController:
    def __init__(self, owner):
        self.owner = owner

    def inventory(self):
        return inventory(self.owner.library, self.owner.games, self.owner.collections)

    def list_collections(self):
        return self.owner.collections.list()

    def rescan(self):
        self.owner.reload()

    def create_collection(self, name: str):
        self.owner.collections.create(name)
        self.owner.reload()

    def rename_collection(self, collection_id: str, name: str):
        self.owner.collections.rename(collection_id, name)
        self.owner.reload()

    def delete_collection(self, collection_id: str):
        self.owner.collections.delete(collection_id)
        self.owner.reload()

    def image_stats(self, game_ids=None):
        return image_stats(self.owner.library.cache, game_ids)

    def recycle_images(self, game_ids=None):
        return recycle_images(self.owner.library.cache, game_ids)

    def default_backup_folder(self) -> Path:
        folder = self.owner.library.store / "backups"
        folder.mkdir(parents=True, exist_ok=True)
        return folder

    def export_backup(self, destination: Path) -> int:
        return backup_data(self.owner.library.store, self.owner.games, destination)

    def inspect_backup(self, source: Path) -> list[str]:
        return inspect_backup(source)

    def restore_backup(self, source: Path) -> tuple[int, Path]:
        result = restore_data(self.owner.library.store, source)
        self.owner.refresh_all_data()
        return result
