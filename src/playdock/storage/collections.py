"""Named, persistent, many-to-many game collections for PlayDock.

Collections only hold references to games. None of these operations alters game
archives, installation folders, or cached artwork.
"""
from __future__ import annotations

from pathlib import Path
from uuid import uuid4

from core import load_json, save_json


class CollectionStore:
    def __init__(self, store: Path):
        self.path = Path(store) / "collections.json"
        raw = load_json(self.path)
        self._collections: list[dict] = []
        for item in raw.get("collections", []) if isinstance(raw.get("collections"), list) else []:
            if not isinstance(item, dict):
                continue
            cid, name, ids = item.get("id"), item.get("name"), item.get("game_ids")
            if (not isinstance(cid, str) or not isinstance(name, str)
                    or not isinstance(ids, list) or not name.strip()):
                continue
            self._collections.append({
                "id": cid,
                "name": name.strip(),
                "game_ids": list(dict.fromkeys(x for x in ids if isinstance(x, str))),
            })

    def list(self) -> list[dict]:
        return [dict(id=c["id"], name=c["name"], game_ids=list(c["game_ids"]))
                  for c in self._collections]

    def _get(self, cid: str) -> dict:
        for col in self._collections:
            if col["id"] == cid:
                return col
        raise KeyError("모음집을 찾을 수 없습니다.")

    def _valid_name(self, name: str, ignore_id: str | None = None) -> str:
        cleaned = name.strip()
        if not cleaned or len(cleaned) > 80:
            raise ValueError("모음집 이름은 1~80자로 입력해 주세요.")
        if any(c["name"].casefold() == cleaned.casefold() and c["id"] != ignore_id
               for c in self._collections):
            raise ValueError("같은 이름의 모음집이 이미 있습니다.")
        if cleaned.casefold() in {"모든 게임", "설치됨", "미설치"}:
            raise ValueError("기본 분류와 같은 이름은 사용할 수 없습니다.")
        return cleaned

    def _save(self):
        save_json(self.path, {"version": 1, "collections": self._collections})

    def create(self, name: str) -> str:
        name = self._valid_name(name)
        cid = uuid4().hex
        self._collections.append({"id": cid, "name": name, "game_ids": []})
        self._save()
        return cid

    def rename(self, cid: str, name: str):
        col = self._get(cid)
        new_name = self._valid_name(name, ignore_id=cid)
        col["name"] = new_name
        self._save()

    def delete(self, cid: str):
        self._get(cid)
        self._collections = [c for c in self._collections if c["id"] != cid]
        self._save()

    def members(self, cid: str) -> set[str]:
        return set(self._get(cid)["game_ids"])

    def for_game(self, game_id: str) -> list[dict]:
        return [dict(id=c["id"], name=c["name"]) for c in self._collections
                if game_id in c["game_ids"]]

    def set_game_memberships(self, game_id: str, collection_ids: set[str]):
        valid_ids = {c["id"] for c in self._collections}
        if collection_ids - valid_ids:
            raise ValueError("존재하지 않는 모음집이 선택되었습니다.")
        for col in self._collections:
            if col["id"] in collection_ids:
                if game_id not in col["game_ids"]:
                    col["game_ids"].append(game_id)
            elif game_id in col["game_ids"]:
                col["game_ids"].remove(game_id)
        self._save()
