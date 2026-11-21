"""작품명→품번 후보 이력. 사용자 컴퓨터의 로컬 앱 데이터에만 저장.

이력은 과거 발견 내역이지 현재 공식 인증이 아니다. 캐시에서 복구된 품번은
항상 history_candidate로 표시하며 confirmed로 승격하지 않는다.
EXE/공개 GitHub 배포에 사용자 게임 목록을 포함하지 않는다.
"""
from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path

from .detector import CODE_PATTERN, EXACT_CODE, product_page_candidate
from .reverse_lookup import Lookup, Match
from .search_terms import cleaned_search_title

MAX_KEYS = 1200
MAX_CODES_PER_TITLE = 6
MAX_AGE_DAYS = 180
CACHE_NAME = "identity_lookup_candidates.json"
VALID_CONFIDENCE = frozenset(("exact_title", "official_code", "search_candidate"))


def default_history_path() -> Path:
    root = os.environ.get("LOCALAPPDATA")
    if root:
        return Path(root) / "PlayDock" / CACHE_NAME
    return Path.home() / ".local" / "state" / "PlayDock" / CACHE_NAME


def _key(raw: str) -> str:
    if CODE_PATTERN.search(raw):
        return ""
    return cleaned_search_title(raw).strip().casefold()[:160]


def _safe_match(raw: dict) -> dict | None:
    if not isinstance(raw, dict) or raw.get("confidence") not in VALID_CONFIDENCE:
        return None
    code = str(raw.get("code", "")).upper()
    if not EXACT_CODE.fullmatch(code):
        return None
    url = str(raw.get("url") or "")[:500]
    ref = product_page_candidate(url) if url else None
    # 제3자 링크는 로컬 이력에서 공식 링크로 표시하지 않는다.
    if ref is None or ref[0] != code:
        url = ""
    return {
        "code": code,
        "title": str(raw.get("title") or "")[:240],
        "url": url,
        "category": str(raw.get("category") or "")[:20] if url else "",
    }


class CandidateHistory:
    def __init__(self, path: Path | None = None):
        self.path = Path(path) if path is not None else default_history_path()
        self.rows: dict[str, dict] = {}
        self._load()

    def _load(self):
        try:
            if self.path.stat().st_size > 3_000_000:
                return
            data = json.loads(self.path.read_text(encoding="utf-8"))
            if not isinstance(data, dict) or data.get("version") != 1:
                return
            cutoff = (datetime.now(timezone.utc) -
                      timedelta(days=MAX_AGE_DAYS)).isoformat()
            for key, entry in list(data.get("entries", {}).items())[:MAX_KEYS]:
                if not isinstance(key, str) or not isinstance(entry, dict):
                    continue
                if str(entry.get("updated") or "") < cutoff:
                    continue
                codes = {}
                for obj in entry.get("matches", [])[:MAX_CODES_PER_TITLE]:
                    # 저장된 이력은 인증으로 다시 사용하지 않음.
                    candidate = _safe_match({**obj, "confidence": "official_code"}) \
                        if isinstance(obj, dict) else None
                    if candidate:
                        codes[candidate["code"]] = candidate
                if codes:
                    self.rows[key] = {"updated": str(entry.get("updated")),
                                      "matches": list(codes.values())}
        except (OSError, ValueError, TypeError, AttributeError):
            # 파일 삭제/손상/이전 포맷이어도 검색 동작은 유지.
            pass

    def _save(self):
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            # 최근 항목만 남기고 무제한 개인 데이터 수집을 피한다.
            ordered = sorted(self.rows.items(),
                             key=lambda item: item[1].get("updated", ""),
                             reverse=True)[:MAX_KEYS]
            self.rows = dict(ordered)
            content = json.dumps({"version": 1, "entries": self.rows},
                                 ensure_ascii=False, indent=2)
            staging = self.path.with_suffix(".tmp")
            staging.write_text(content, encoding="utf-8")
            staging.replace(self.path)
        except OSError:
            # 캐시 오류는 실제 검색을 실패시키지 않는다.
            pass

    def _remember(self, raw: str, matches, *, save: bool) -> int:
        key = _key(raw)
        if not key:
            return 0
        entry = self.rows.get(key, {"matches": []})
        codes = {row["code"]: row for row in entry.get("matches", [])
                 if isinstance(row, dict) and "code" in row}
        initial = len(codes)
        for raw_match in matches:
            obj = _safe_match(raw_match)
            if obj and obj["code"] not in codes:
                if len(codes) >= MAX_CODES_PER_TITLE:
                    break
                codes[obj["code"]] = obj
        if len(codes) > initial:
            self.rows[key] = {
                "updated": datetime.now(timezone.utc).isoformat(),
                "matches": list(codes.values()),
            }
            if save:
                self._save()
        return len(codes) - initial

    def merge_and_save(self, result: Lookup) -> Lookup:
        """현재 조회를 우선하고 부족한 과거 후보만 회색 기록으로 덧붙임."""
        if result.direction != "title_to_code" or result.status == "invalid":
            return result
        key = _key(result.query)
        if not key:
            return result
        old = self.rows.get(key, {}).get("matches", [])
        current = {m.code for m in result.matches}
        historical = []
        if result.status != "confirmed":
            for item in old:
                if item["code"] in current:
                    continue
                historical.append(Match(
                    item["code"], item["title"], item["url"],
                    item["category"], "history_candidate", "local_history",
                    "과거에 발견한 후보: 이번 실행에서는 다시 확인하지 못함. 수동 확인 필요."))
                if len(historical) >= MAX_CODES_PER_TITLE:
                    break
        # 새로 찾은 후보만 캐시에 저장. 과거 후보 재저장으로 시각을 갱신하지 않는다.
        self._remember(result.query, [
            {"code": m.code, "title": m.title, "url": m.url,
             "category": m.category, "confidence": m.confidence}
            for m in result.matches
        ], save=True)
        if not historical:
            return result
        warnings = tuple(result.warnings) + (
            "과거 검색 이력에서 후보를 복원했습니다. 이번 검색에서 재확인하지 못했습니다.",)
        return replace(
            result,
            status="candidates" if result.status in ("no_candidate", "unavailable") else result.status,
            matches=tuple(result.matches) + tuple(historical),
            warnings=warnings,
        )

    def import_export(self, path: Path) -> tuple[int, int]:
        """기존 v4/v5/v6 JSON의 발견 후보를 보존. 사용자가 선택한 파일만 읽음."""
        source = Path(path)
        if source.stat().st_size > 5_000_000:
            raise ValueError("JSON 파일은 5MB 이하여야 합니다.")
        payload = json.loads(source.read_text(encoding="utf-8"))
        if not isinstance(payload, dict) or payload.get("mode") != "title_to_code":
            raise ValueError("이름→품번 검색 결과 JSON이 아닙니다.")
        results = payload.get("results")
        if not isinstance(results, list) or len(results) > 2500:
            raise ValueError("JSON 결과 목록 형식이 올바르지 않습니다.")
        added = 0
        titles = 0
        for result in results:
            if not isinstance(result, dict) or not isinstance(result.get("matches"), list):
                continue
            found = self._remember(str(result.get("query") or ""),
                                   result["matches"][:MAX_CODES_PER_TITLE], save=False)
            if found:
                titles += 1
                added += found
        if added:
            self._save()
        return titles, added
