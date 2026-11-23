"""일괄 제목 변경 미리보기·업무 규칙·저장을 담당한다.

대화상자/Qt를 몰라도 테스트할 수 있다. UI는 선택한 게임과 입력 문구,
체크된 변경안을 전달하고 결과를 보여준다.
"""
from __future__ import annotations

from bulk_title_edit import (
    BulkChange, replace_name, name_was_manually_changed,
    preview_undo_name, apply_bulk_changes,
)
from product_titles import clean_title


def valid_korean_candidate(raw_title: str) -> bool:
    """인터넷에서 확인한 한국어 제목을 저장 후보로 받아도 되는지 검사한다."""
    return bool(clean_title(raw_title)) and any("가" <= ch <= "힣" for ch in raw_title)


class BulkTitleActions:
    def __init__(self, library):
        self.library = library

    def eligible_games(self, games, *, skip_custom: bool = False):
        if not skip_custom:
            return list(games)
        return [g for g in games if not name_was_manually_changed(self.library, g)]

    def preview_changes(self, games, mode: str, *, find: str = "",
                        replacement: str = "", case_sensitive: bool = False):
        """원본 파일명·이전 이력·문구 교체·직접 입력을 보존하는 변경안."""
        if mode not in {"manual", "replace", "undo", "original"}:
            raise ValueError("지원하지 않는 일괄 변경 방식입니다.")
        records = []
        for game in games:
            old = self.library.title(game)
            if mode == "manual":
                proposed = self.library.base_title(game)
                method = "manual"
            elif mode == "replace":
                proposed = replace_name(self.library.base_title(game), find, replacement,
                                        case_sensitive=case_sensitive)
                if not proposed or proposed == self.library.base_title(game):
                    continue
                method = "manual"
            elif mode == "undo":
                proposed = preview_undo_name(self.library, game)
                if proposed is None:
                    continue
                method = "undo"
            else:
                proposed = game.name
                if self.library.base_title(game) == game.name:
                    continue
                method = "original"
            records.append(BulkChange(game.id, old, proposed, method,
                                      source="사용자 일괄 변경"))
        return records

    def lookup_preview(self, games, rows, language: str, *, save_as_localized: bool):
        """검색 결과의 실제 언어와 출처를 그대로 유지한다."""
        by_id = {game.id: game for game in games}
        records = []
        for item in rows:
            game = by_id.get(item["game_id"])
            if game is None:
                continue
            title = item.get("title") or ""
            if title:
                actual = item.get("language") or language
                is_steam = item.get("store") == "steam"
                records.append(BulkChange(
                    game.id, self.library.title(game), title,
                    method="manual" if is_steam else (
                        "localized" if save_as_localized else "manual"),
                    language=actual, source=item.get("source", ""),
                    product_code="" if is_steam else item.get("code", ""),
                ))
            else:
                records.append(BulkChange(
                    game.id, self.library.title(game), "", method="manual",
                    source=item.get("error") or "조회 실패",
                    product_code=item.get("code", ""),
                ))
        return records

    @staticmethod
    def prepare_changes(approved_edits, selected_language: str):
        """UI가 확인한 (원본 미리보기, 편집된 텍스트)를 저장 요청으로 변환한다."""
        changes = []
        for original, entered_title in approved_edits:
            title = entered_title.strip()
            language = original.language
            source = original.source
            if original.method == "localized" and title != original.proposed_name:
                source = "사용자가 직접 수정한 제목 · 검증 필요"
                if original.language != selected_language:
                    language = selected_language
            changes.append(BulkChange(
                original.game_id, original.expected_name, title,
                method=original.method, language=language,
                product_code=original.product_code, source=source,
            ))
        return changes

    def apply_changes(self, games, changes):
        """기존 원자적 저장과 메타데이터 백업·롤백을 그대로 사용한다."""
        return apply_bulk_changes(self.library, games, changes)
