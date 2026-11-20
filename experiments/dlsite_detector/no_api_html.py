"""PlayDock public HTML-only discovery and product-page checks.

No external API endpoint, token, credential or JSON search service is called.
HTML search is best-effort, rate-limit and robots/site policies may prevent access.
The functions only accept a game title or validated public product ID.
"""
from __future__ import annotations

from html import unescape
from html.parser import HTMLParser
import re
from urllib.parse import parse_qs, unquote, urlencode, urlsplit
from urllib.request import Request, urlopen

from .detector import CATEGORIES, EXACT_CODE, Product
from .steam_client import STEAM_ID, SteamProduct

MAX_HTML_BYTES = 600_000
SEARCH_LIMIT = 12
SEARCH_ENDPOINTS = {
    "ddg_html": "https://html.duckduckgo.com/html/",
    "itch_html": "https://itch.io/search",
    "mojeek_html": "https://www.mojeek.com/search",
    "steam_html": "https://store.steampowered.com/search/",
}


class PublicHtmlUnavailable(RuntimeError):
    """HTML unavailable, blocked, challenged or structurally unusable."""


class _HtmlFacts(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.anchors = []
        self.meta = {}
        self.page_title = ""
        self.heading = ""
        self._anchor = None
        self._title = False
        self._heading = False

    def handle_starttag(self, tag, attrs):
        props = dict(attrs)
        if tag == "a":
            self._anchor = {"href": props.get("href", ""), "class": props.get("class", ""), "text": []}
        elif tag == "meta":
            key = (props.get("property") or props.get("name") or "").casefold()
            if key in {"og:title", "twitter:title", "og:type"}:
                self.meta[key] = props.get("content", "")
        elif tag == "title":
            self._title = True
        elif tag == "h1":
            self._heading = True

    def handle_data(self, text):
        if self._anchor is not None:
            self._anchor["text"].append(text)
        if self._title:
            self.page_title += text
        if self._heading:
            self.heading += text

    def handle_endtag(self, tag):
        if tag == "a" and self._anchor is not None:
            self._anchor["text"] = " ".join(self._anchor["text"])
            self.anchors.append(self._anchor)
            self._anchor = None
        elif tag == "title":
            self._title = False
        elif tag == "h1":
            self._heading = False


def _clean(value: str) -> str:
    return re.sub(r"\s+", " ", unescape(str(value))).strip()


def _fetch_html(url: str, *, timeout: float, opener=urlopen) -> tuple[str, str]:
    req = Request(url, headers={
        "User-Agent": "Mozilla/5.0 (compatible; PlayDockFilenameResearch/0.11.7)",
        "Accept": "text/html,application/xhtml+xml;q=0.9",
        "Accept-Language": "en-US,en;q=0.9",
    })
    try:
        with opener(req, timeout=timeout) as response:
            final_url = response.geturl() if hasattr(response, "geturl") else url
            content_type = response.headers.get("Content-Type", "text/html")
            body = response.read(MAX_HTML_BYTES + 1)
    except Exception as exc:
        raise PublicHtmlUnavailable(type(exc).__name__) from exc
    if not content_type.lower().startswith(("text/html", "application/xhtml+xml")):
        raise PublicHtmlUnavailable("HTML이 아닌 응답")
    if len(body) > MAX_HTML_BYTES:
        raise PublicHtmlUnavailable("HTML 크기 제한 초과")
    text = body.decode("utf-8-sig", errors="replace")
    lower = text[:100_000].casefold()
    if any(marker in lower for marker in (
        "anomaly-modal", "challenge-form", "captcha-delivery",
        "cf-chl-widget", "verify you are human",
    )):
        raise PublicHtmlUnavailable("자동 접근 차단 또는 CAPTCHA")
    return final_url, text


def _facts(body: str) -> _HtmlFacts:
    p = _HtmlFacts()
    try:
        p.feed(body)
    except (ValueError, AssertionError) as exc:
        raise PublicHtmlUnavailable("HTML 파싱 실패") from exc
    return p


def _external_url(raw: str, *, source: str) -> str:
    raw = unescape(raw or "").strip()
    if raw.startswith("//"):
        raw = "https:" + raw
    if raw.startswith("/") and source == "itch_html":
        raw = "https://itch.io" + raw
    try:
        parts = urlsplit(raw)
        host = (parts.hostname or "").casefold()
        if parts.scheme != "https" or not host or parts.username or parts.password:
            return ""
        if host in {"duckduckgo.com", "html.duckduckgo.com", "lite.duckduckgo.com"}:
            values = parse_qs(parts.query).get("uddg", [])
            if not values:
                return ""
            raw = unquote(values[0])
            parts = urlsplit(raw)
            host = (parts.hostname or "").casefold()
        if parts.scheme != "https" or not host or parts.username or parts.password:
            return ""
        if host in {"duckduckgo.com", "www.mojeek.com", "mojeek.com", "itch.io"}:
            return ""
        if source == "itch_html" and not host.endswith(".itch.io"):
            return ""
        if source == "steam_html" and (host != "store.steampowered.com"
                                      or not re.match(r"^/app/\d+", parts.path)):
            return ""
        if len(raw) > 1000:
            return ""
        return raw
    except ValueError:
        return ""


def search_public_html(title: str, provider: str, *,
                       timeout: float = 2.5, opener=urlopen) -> list[dict]:
    """Search the normal HTML website rather than a public/paid JSON API."""
    if provider not in SEARCH_ENDPOINTS:
        raise ValueError("허용되지 않은 HTML 검색 사이트")
    if not isinstance(title, str) or not 1 <= len(title) <= 160:
        return []
    key = "term" if provider == "steam_html" else "q"
    url = SEARCH_ENDPOINTS[provider] + "?" + urlencode({key: title})
    final, body = _fetch_html(url, timeout=timeout, opener=opener)
    if (urlsplit(final).hostname or "").casefold() != (urlsplit(url).hostname or "").casefold():
        raise PublicHtmlUnavailable("검색 사이트가 다른 호스트로 이동함")
    info = _facts(body)
    found = []
    seen = set()
    for row in info.anchors:
        dest = _external_url(row["href"], source=provider)
        heading = _clean(row["text"])[:220]
        if not dest or len(heading) < 3 or dest in seen:
            continue
        # Don't treat normal header/footer navigation as a game search hit.
        if provider == "ddg_html" and "result__a" not in row["class"] and "result-link" not in row["class"]:
            continue
        seen.add(dest)
        found.append({"title": heading, "href": dest, "body": ""})
        if len(found) >= SEARCH_LIMIT:
            break
    if not found and ("result__a" in body or "result-link" in body):
        raise PublicHtmlUnavailable("검색 HTML 구조 변경 또는 결과 추출 실패")
    return found


def _store_title(html: str) -> str:
    facts = _facts(html)
    title = (_clean(facts.meta.get("og:title") or facts.meta.get("twitter:title")
                    or facts.heading or facts.page_title))
    title = re.sub(r"\s*[-|]\s*(?:DLsite|Steam|DLsite 同人).*$", "", title, flags=re.I)
    title = re.sub(r"(?i)\s+on Steam$", "", title).strip()
    if not 2 <= len(title) <= 240 or "captcha" in title.casefold():
        return ""
    return title


def fetch_dlsite_html(code: str, *, timeout: float = 2.5,
                      opener=urlopen) -> Product | None:
    """Verify product code on an actual official work HTML page, not a JSON API."""
    code = str(code).upper()
    if not EXACT_CODE.fullmatch(code):
        raise ValueError("DLsite 작품번호 형식이 잘못됨")
    for category in CATEGORIES:
        url = f"https://www.dlsite.com/{category}/work/=/product_id/{code}.html"
        try:
            final, body = _fetch_html(url, timeout=timeout, opener=opener)
        except PublicHtmlUnavailable:
            continue
        final_parts = urlsplit(final)
        if (final_parts.hostname or "").casefold() != "www.dlsite.com":
            continue
        if not re.search(rf"/work/=/product_id/{re.escape(code)}\.html", final_parts.path, re.I):
            continue
        if code not in body.upper():
            continue
        title = _store_title(body)
        if not title or "dlsite" == title.casefold():
            continue
        # HTML alone doesn't reliably prove game type; don't infer it.
        return Product(code, title, "", category, url)
    return None


def fetch_steam_html(app_id: str, *, timeout: float = 3.0,
                     opener=urlopen) -> SteamProduct | None:
    """Read the normal public Store app page; never call /api/appdetails."""
    app_id = str(app_id)
    if not STEAM_ID.fullmatch(app_id):
        raise ValueError("Steam App ID 형식이 잘못됨")
    url = f"https://store.steampowered.com/app/{app_id}/?l=english"
    final, body = _fetch_html(url, timeout=timeout, opener=opener)
    final_parts = urlsplit(final)
    if (final_parts.hostname or "").casefold() != "store.steampowered.com":
        return None
    if not re.match(rf"^/app/{re.escape(app_id)}(?:/|$)", final_parts.path):
        return None
    name = _store_title(body)
    if not name or name.casefold() in {"steam", "welcome to steam"}:
        return None
    lower = body.casefold()
    kind = "dlc" if "downloadable content" in lower and "game_area_dlc_bubble" in lower else "unknown"
    return SteamProduct(app_id, name, kind, f"https://store.steampowered.com/app/{app_id}/")
