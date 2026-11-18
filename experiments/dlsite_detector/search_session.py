"""v0.5 대량 검증용 검색 세션: 중복 결과 재사용 및 검색 장애 시 회복.

GUI의 단일 작업 스레드가 공유한다. 원본 압축/개인 경로는 캐시하지 않고
정제된 제목/코드와 외부 검색의 구조화된 결과만 세션 종료 시까지 보관한다.
API 키, 디스크 기록, 사용자 게임 DB 변경은 없다.
"""
from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass, replace
from typing import Callable
import re
import time

from .detector import normalized_title
from .pipeline import SearchDecision

CODE = re.compile(r"^(?:(?:RJ|BJ|VJ|EJ)\d{6,8}|Steam App ID:\s*\d{3,10})$", re.I)
ERROR_MARKERS = (
    "일반 인터넷 검색 오류", "인터넷 조회 실패",
    "빠른 웹 검색 오류", "검색 서비스 오류",
    "RuntimeError", "TimeoutError", "ConnectionError",
)


@dataclass(frozen=True)
class SessionMetrics:
    requests: int
    cache_hits: int
    avoided_requests: int
    network_errors: int

    def to_dict(self) -> dict:
        return {
            "requests": self.requests,
            "cache_hits": self.cache_hits,
            "avoided_requests": self.avoided_requests,
            "network_errors": self.network_errors,
        }


class SearchSession:
    """같은 한 번의 GUI 검증 작업 동안 검색 결과를 안전하게 재사용한다.

    연속 웹 실패가 생기면 일반 제목 검색만 일시적으로 생략하고,
    명시적인 DLsite/Steam 번호의 조회는 여전히 허용한다.
    """

    def __init__(
        self, classifier: Callable[[str], SearchDecision], *,
        max_failures: int = 2, cache_size: int = 512,
        cooldown_seconds: float = 20.0,
    ) -> None:
        self.classifier = classifier
        self.max_failures = max(1, max_failures)
        self.cache_size = max(1, cache_size)
        self.cooldown_seconds = max(0.0, cooldown_seconds)
        self._retry_after = 0.0
        self._cache: OrderedDict[str, SearchDecision] = OrderedDict()
        self._failures = 0
        self._requests = 0
        self._hits = 0
        self._avoided = 0
        self._errors = 0
        self._pending: OrderedDict[str, str] = OrderedDict()

    def __call__(self, query: str) -> SearchDecision:
        key = normalized_title(query) or query.strip().casefold()
        cached = self._cache.get(key)
        if cached is not None:
            self._hits += 1
            self._cache.move_to_end(key)
            return replace(cached, original_query=query)
        # 연속 검색 장애가 있을 때도 작품 ID 조회는 계속한다.
        if (self._failures >= self.max_failures
                and time.monotonic() < self._retry_after
                and not CODE.fullmatch(query.strip())):
            self._avoided += 1
            self._remember_pending(key, query)
            return SearchDecision(
                "lookup_unavailable", query, web_checked=False,
                search_state="cooldown_skipped",
                reason="검색 서비스 연속 장애로 일반 제목의 추가 인터넷 요청을 생략했습니다. "
                       "게임이 없는 것은 아니며 정밀 재검사가 필요합니다.",
            )
        self._requests += 1
        try:
            result = self.classifier(query)
        except Exception as exc:
            result = SearchDecision(
                "lookup_unavailable", query, web_checked=True,
                search_state="network_error",
                reason=f"인터넷 조회 실패: {type(exc).__name__}",
            )
        is_error = (
            result.status == "lookup_unavailable" and
            (result.search_state == "network_error" or
             any(marker in result.reason for marker in ERROR_MARKERS))
        )
        if is_error:
            self._errors += 1
            self._remember_pending(key, query)
            self._failures += 1
            if self._failures >= self.max_failures:
                self._retry_after = time.monotonic() + self.cooldown_seconds
            # 외부 서비스가 복구되면 다른 파일에서 다시 시도하도록
            # 실패한 쿼리는 캐시하지 않는다.
        else:
            self._failures = 0
            self._retry_after = 0.0
            self._pending.pop(key, None)
            self._cache[key] = result
            self._cache.move_to_end(key)
            while len(self._cache) > self.cache_size:
                self._cache.popitem(last=False)
        return result

    def _remember_pending(self, key: str, query: str) -> None:
        self._pending[key] = query
        self._pending.move_to_end(key)
        while len(self._pending) > self.cache_size:
            self._pending.popitem(last=False)

    @property
    def pending_queries(self) -> tuple[str, ...]:
        """오류/쿨다운 생략 검색어. 파일 경로나 압축 내용은 보관하지 않는다."""
        return tuple(self._pending.values())

    def retry_pending(self, *, max_queries: int = 2) -> dict[str, SearchDecision]:
        """쿨다운 이후 요청한 경우에만 제한적으로 재검색. 원본 ZIP 재스캔 없음.

        재시도 결과는 호출자에게 반환하고 성공한 검색만 기존 캐시에 남긴다.
        """
        if time.monotonic() < self._retry_after:
            return {}
        out: dict[str, SearchDecision] = {}
        for query in self.pending_queries[:max(0, max_queries)]:
            result = self(query)
            out[query] = result
            if result.search_state in {"network_error", "cooldown_skipped"}:
                break
        return out

    @property
    def metrics(self) -> SessionMetrics:
        return SessionMetrics(self._requests, self._hits, self._avoided, self._errors)

    def clear(self) -> None:
        self._cache.clear()
        self._pending.clear()
        self._failures = 0
        self._retry_after = 0.0
