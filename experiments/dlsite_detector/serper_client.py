"""PlayDock 선택형 Serper Google 검색: 게임명만 전송, 키는 인증 헤더에만 전달."""
from __future__ import annotations

import json
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

ENDPOINT = "https://google.serper.dev/search"
MAX_RESULTS = 8
MAX_BYTES = 350_000


class SerperSearchError(RuntimeError):
    """인증 토큰·원문 응답을 포함하지 않는 오류."""


def serper_google_search(title: str, api_key: str, *,
                         timeout: float = 4.0, opener=urlopen) -> list[dict]:
    if not api_key or not api_key.strip():
        raise SerperSearchError("Serper API 키 미입력")
    if not title or len(title) > 180:
        return []
    if any("가" <= c <= "힣" for c in title):
        qualifier = "게임"
    elif any("\u3040" <= c <= "\u30ff" or "\u4e00" <= c <= "\u9fff"
             for c in title):
        qualifier = "ゲーム"
    else:
        qualifier = "game"
    payload = json.dumps({"q": f'"{title.strip()}" {qualifier}',
                          "num": MAX_RESULTS, "gl": "kr", "hl": "ko"},
                         ensure_ascii=False).encode("utf-8")
    request = Request(ENDPOINT, data=payload, method="POST", headers={
        "X-API-KEY": api_key.strip(),
        "Content-Type": "application/json",
        "Accept": "application/json",
        "User-Agent": "PlayDock-Filename-Tester/0.11.5",
    })
    try:
        with opener(request, timeout=timeout) as reply:
            raw = reply.read(MAX_BYTES + 1)
    except HTTPError as exc:
        reasons = {401: "API 키가 유효하지 않습니다",
                   402: "사용량 한도를 확인하세요",
                   403: "접근 권한이 없습니다",
                   429: "호출 또는 사용량 제한"}
        raise SerperSearchError(
            f"Serper HTTP {exc.code}: " + reasons.get(exc.code, "서비스 오류")
        ) from None
    except (URLError, OSError, TimeoutError) as exc:
        raise SerperSearchError("Serper 연결 오류: " + type(exc).__name__) from None
    if len(raw) > MAX_BYTES:
        raise SerperSearchError("Serper 응답 크기 초과")
    try:
        data = json.loads(raw)
    except (ValueError, UnicodeError):
        raise SerperSearchError("Serper JSON 응답 오류") from None
    if not isinstance(data, dict) or not isinstance(data.get("organic", []), list):
        raise SerperSearchError("Serper organic 결과 형식 오류")
    rows, seen = [], set()
    for item in data.get("organic", [])[:MAX_RESULTS * 2]:
        if not isinstance(item, dict):
            continue
        url = item.get("link", "")
        if not isinstance(url, str):
            continue
        try:
            parsed = urlsplit(url)
        except ValueError:
            continue
        if parsed.scheme != "https" or not parsed.hostname or url in seen:
            continue
        seen.add(url)
        rows.append({"title": str(item.get("title") or "")[:300],
                     "href": url[:1100],
                     "body": str(item.get("snippet") or "")[:700]})
        if len(rows) >= MAX_RESULTS:
            break
    return rows
