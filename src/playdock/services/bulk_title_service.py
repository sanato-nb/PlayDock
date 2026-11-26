"""일괄 제목 변경 미리보기·업무 규칙·저장을 담당한다.

대화상자/Qt를 몰라도 테스트할 수 있다. UI는 선택한 게임과 입력 문구,
체크된 변경안을 전달하고 결과를 보여준다.
"""
from __future__ import annotations

from services.simple_title_edit import original_display_name, localized_title_changes

from services.bulk_title_edit import (
    BulkChange, replace_name, name_was_manually_changed,
    preview_undo_name, apply_bulk_changes, validate_changes,
)
from product_titles import clean_title
from collections import Counter


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
            meta = self.library.meta(game)
            base, old = self.library.title_pair(game, meta=meta)
            if mode == "manual":
                proposed = base
                method = "manual"
            elif mode == "replace":
                proposed = replace_name(base, find, replacement,
                                        case_sensitive=case_sensitive)
                if not proposed or proposed == base:
                    continue
                method = "manual"
            elif mode == "undo":
                proposed = preview_undo_name(self.library, game, meta=meta)
                if proposed is None:
                    continue
                method = "undo"
            else:
                # First-seen archive filename is immutable once recorded.
                proposed = original_display_name(self.library, game, meta=meta)
                if base == proposed:
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
                records.append(BulkChange(
                    game.id, item.get("original") or self.library.title(game), title,
                    method="localized" if save_as_localized else "manual",
                    language=actual, source=item.get("source", ""),
                    product_code=str(item.get("code") or ""), lookup_result=True,
                    product_store=item.get("store") or "dlsite",
                ))
            else:
                records.append(BulkChange(
                    game.id, item.get("original") or self.library.title(game), "", method="manual",
                    source=item.get("error") or "조회 실패",
                    product_code=item.get("code", ""), lookup_result=True,
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
            if title != original.proposed_name and (original.lookup_result or original.method == "localized"):
                source = "사용자가 직접 수정한 제목 · 검증 필요"
                if original.method == "localized":
                    language = selected_language
            changes.append(BulkChange(
                original.game_id, original.expected_name, title,
                method=original.method, language=language,
                product_code=original.product_code, source=source, lookup_result=original.lookup_result,
                product_store=original.product_store,
            ))
        return changes

    def partition_changes(self, games, changes):
        """Reject individual invalid/stale plans before any write; never bypass validation."""
        by_id = {game.id: game for game in games}
        counts = Counter(change.game_id for change in changes)
        valid, rejected = [], []
        for change in changes:
            game = by_id.get(change.game_id)
            try:
                if counts[change.game_id] != 1:
                    raise ValueError("같은 게임이 중복되었습니다.")
                validate_changes(self.library, [game] if game is not None else [], [change])
            except (ValueError, OSError) as exc:
                rejected.append((change, str(exc)))
            else:
                valid.append(change)
        return valid, rejected

    def preview_status(self, game, original, text, selected_language):
        change = self.prepare_changes([(original, text)], selected_language)[0]
        if not change.proposed_name and change.method not in ("original", "undo"):
            return "제목 입력 필요", False
        valid, rejected = self.partition_changes([game] if game else [], [change])
        if not valid:
            reason = rejected[0][1]
            if "문자가 일치" in reason:
                return "언어 불일치 · 수정 필요", False
            return "확인 필요 · " + reason, False
        if (original.lookup_result or original.method == "localized") and text.strip() == original.proposed_name and change.language != selected_language:
            return "다른 언어 · 확인 필요", False
        if original.lookup_result and change.source != original.source:
            return "직접 수정 · 확인", True
        return "미리보기 확인", True

    def preview_display(self, game, original, text, selected_language):
        """Compute the actual displayed name with the same library rendering."""
        if game is None:
            return ""
        change = self.prepare_changes([(original, text)], selected_language)[0]
        meta = self.library.meta(game)
        if change.method == "undo":
            return preview_undo_name(self.library, game, meta=meta) or ""
        if change.method == "localized":
            try:
                meta = dict(meta, **localized_title_changes(meta, change.proposed_name,
                                                           change.language, change.source))
            except ValueError:
                return ""
        else:
            if not change.proposed_name:
                return ""
            meta = dict(meta, title=change.proposed_name, prefer_manual_title=True,
                        title_product_code="")
        return self.library.title_pair(game, meta=meta)[1]

    def apply_changes(self, games, changes):
        """기존 원자적 저장과 메타데이터 백업·롤백을 그대로 사용한다."""
        return apply_bulk_changes(self.library, games, changes)
