"""API 키가 없는 자동 다중 검색 엔진 어댑터.

구글 웹페이지 스크래핑에 의존하지 않고 공개 메타검색 라이브러리 DDGS의
DuckDuckGo/Brave/Bing 백엔드를 사용한다. 서비스 정책 및 차단은 존중한다.
결과는 반드시 별도의 DLsite 품번 검증을 거치는 '후보'이다.
"""
from __future__ import annotations

from urllib.parse import urlsplit

from .no_api_html import PublicHtmlUnavailable

MAX_WEB_RESULTS = 12
MAX_TITLE = 240
MAX_SUMMARY = 420
# Google 자동수집은 이용약관 제약이 있으므로 제외한다.
BACKENDS = "duckduckgo,brave,bing"


def search_meta_no_key(
    query: str, *, searcher=None, timeout: int = 5,
) -> list[dict]:
    """자동 웹 검색 결과의 제목/설명/URL을 반환. API 토큰과 브라우저 조작 불필요.

    searcher 인자는 순수 회귀 테스트용 주입 지점. 기본 경로는 DDGS를 사용한다.
    """
    if not isinstance(query, str) or not 2 <= len(query) <= 160:
        return []
    if searcher is None:
        try:
            from ddgs import DDGS
        except ImportError as exc:
            raise PublicHtmlUnavailable("DDGS 미설치") from exc
        try:
            rows = DDGS(timeout=timeout).text(
                query, region="kr-kr", safesearch="off",
                max_results=MAX_WEB_RESULTS, backend=BACKENDS,
            )
        except Exception as exc:
            raise PublicHtmlUnavailable("DDGS 검색 실패: " + type(exc).__name__) from exc
    else:
        rows = searcher(query)

    if not isinstance(rows, (list, tuple)):
        raise PublicHtmlUnavailable("DDGS 응답 형식 오류")

    found = []
    seen = set()
    for row in rows[:MAX_WEB_RESULTS * 2]:
        if not isinstance(row, dict):
            continue
        url = str(row.get("href") or row.get("url") or "")
        parts = urlsplit(url)
        if parts.scheme != "https" or not parts.hostname or parts.username or parts.password:
            continue
        if len(url) > 1000:
            continue
        title = " ".join(str(row.get("title") or "").split())[:MAX_TITLE]
        snippet = " ".join(str(row.get("body") or "").split())[:MAX_SUMMARY]
        if not title or url in seen:
            continue
        seen.add(url)
        found.append({"title": title, "href": url, "body": snippet})
        if len(found) >= MAX_WEB_RESULTS:
            break
    return found
