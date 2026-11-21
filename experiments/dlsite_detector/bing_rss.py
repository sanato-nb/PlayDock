"""Bing 공개 RSS 웹 검색 어댑터. API 키/브라우저 자동화 불필요.

RSS 응답이 막히거나 웹페이지로 전환되면 검색 실패로 보고한다.
검색 결과는 비공식 출처이므로 DLsite 상품 페이지로 재확인해야 한다.
"""
from __future__ import annotations

from html import unescape
import re
import xml.etree.ElementTree as ET
from urllib.parse import urlencode, urlsplit
from urllib.request import Request, urlopen

from .no_api_html import PublicHtmlUnavailable

ENDPOINT = "https://www.bing.com/search"
MAX_BYTES = 1_250_000
MAX_RESULTS = 12


def _text(element, tag):
    val = element.findtext(tag) or ""
    return re.sub(r"\s+", " ", unescape(re.sub(r"<[^>]*>", " ", val))).strip()


def parse_bing_rss(data: bytes) -> list[dict]:
    """RSS channel/item 구조만 허용. HTML이나 검색 차단 페이지는 배제."""
    if len(data) > MAX_BYTES or b"<!DOCTYPE" in data.upper():
        raise PublicHtmlUnavailable("Bing RSS 문서 제한 초과/DOCTYPE 거절")
    try:
        root = ET.fromstring(data)
    except ET.ParseError as exc:
        raise PublicHtmlUnavailable("Bing RSS XML 파싱 실패") from exc
    if root.tag != "rss" or root.find("channel") is None:
        raise PublicHtmlUnavailable("Bing RSS 문서가 아닌 응답")
    rows, seen = [], set()
    for item in root.findall("./channel/item")[:MAX_RESULTS * 2]:
        url = _text(item, "link")
        title = _text(item, "title")[:240]
        description = _text(item, "description")[:420]
        parts = urlsplit(url)
        if not (parts.scheme == "https" and parts.hostname and
                not parts.username and not parts.password and len(url) <= 1000):
            continue
        if url in seen or not title:
            continue
        seen.add(url)
        rows.append({"title": title, "href": url, "body": description})
        if len(rows) >= MAX_RESULTS:
            break
    return rows


def search_bing_rss(query: str, *, timeout: float = 4, opener=urlopen) -> list[dict]:
    if not isinstance(query, str) or not 2 <= len(query) <= 160:
        return []
    url = ENDPOINT + "?" + urlencode({"q": query + " DLsite", "format": "rss"})
    request = Request(url, headers={"User-Agent": "PlayDock/0.1 (+https://github.com/sanato-nb/PlayDock)",
                                    "Accept": "application/rss+xml, application/xml, text/xml"})
    try:
        with opener(request, timeout=timeout) as response:
            final = response.geturl()
            parsed = urlsplit(final)
            if parsed.scheme != "https" or (parsed.hostname or "").casefold() not in {
                "www.bing.com", "bing.com"
            }:
                raise PublicHtmlUnavailable("Bing RSS 외부로 이동")
            ctype = (response.headers.get("Content-Type") or "").split(";")[0].lower()
            if ctype and ctype not in ("application/rss+xml", "application/xml",
                                       "text/xml", "application/atom+xml"):
                raise PublicHtmlUnavailable("Bing RSS 대신 " + ctype + " 응답")
            data = response.read(MAX_BYTES + 1)
    except PublicHtmlUnavailable:
        raise
    except Exception as exc:
        raise PublicHtmlUnavailable("Bing RSS 접속 오류: " + type(exc).__name__) from exc
    return parse_bing_rss(data)
