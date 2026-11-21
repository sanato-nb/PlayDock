"""API/키 없이 DLsite 공식 HTML만을 근거로 이름↔품번을 찾는 독립 실험 엔진.

검색 결과는 '후보'이고, 공식 작품 HTML과 품번을 확인했을 때만 '공식 확인'.
품번을 못 찾았다는 사실은 작품이 존재하지 않는다는 증거가 아니다.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from html import unescape
from html.parser import HTMLParser
import re
from typing import Callable
from urllib.parse import parse_qs, quote, urlencode, urljoin, urlsplit

from .detector import CODE_PATTERN, EXACT_CODE, Product, normalized_title, product_page_candidate
from .no_api_html import PublicHtmlUnavailable, _fetch_html, fetch_dlsite_html, search_public_html
from .search_terms import cleaned_search_title

CATEGORIES = ("maniax", "home", "soft", "girls")
MAX_CANDIDATES = 8
MAX_VERIFY = 5


@dataclass(frozen=True)
class Match:
    code: str
    title: str
    url: str
    category: str
    confidence: str  # exact_title / official_code / search_candidate
    source: str
    note: str = ""


@dataclass(frozen=True)
class Lookup:
    direction: str
    query: str
    status: str  # confirmed / candidates / no_candidate / unavailable / invalid
    matches: tuple[Match, ...] = ()
    warnings: tuple[str, ...] = ()
    providers: tuple[dict, ...] = ()
    input_origin: str = "manual"  # archive / manual

    def to_dict(self) -> dict:
        return asdict(self)


class _CatalogLinks(HTMLParser):
    """공식 검색 HTML의 작품별 링크 및 이미지 alt/앵커 텍스트만 추출."""
    def __init__(self, base: str):
        super().__init__(convert_charrefs=True)
        self.base = base
        self.rows: list[tuple[str, str]] = []
        self.current: dict | None = None

    def handle_starttag(self, tag, attrs):
        props = dict(attrs)
        if tag == "a":
            href = urljoin(self.base, unescape(props.get("href") or ""))
            parts = urlsplit(href)
            # Google 일반 검색 HTML의 /url?q=... 링크만 안전하게 풀어냄.
            if parts.hostname in ("google.com", "www.google.com") and parts.path == "/url":
                href = parse_qs(parts.query).get("q", [""])[0]
            # 출처가 진짜 DLsite 작품 페이지인지 반드시 URL 검증.
            if product_page_candidate(href):
                self.current = {"href": href, "texts": [props.get("title") or ""]}
        elif self.current is not None and tag == "img":
            self.current["texts"].append(props.get("alt") or "")

    def handle_data(self, data):
        if self.current is not None:
            self.current["texts"].append(data)

    def handle_endtag(self, tag):
        if tag == "a" and self.current is not None:
            title = re.sub(r"\s+", " ", " ".join(self.current["texts"])).strip()
            self.rows.append((self.current["href"], title[:240]))
            self.current = None


def parse_catalog_links(html: str, base_url: str) -> list[dict]:
    """공식 작품 페이지 URL에서 품번을 추출. 메뉴/제3자 링크는 거절."""
    parser = _CatalogLinks(base_url)
    parser.feed(html)
    unique = {}
    for href, title in parser.rows:
        code_and_category = product_page_candidate(href)
        if code_and_category is None:
            continue
        code, category = code_and_category
        if code not in unique or (not unique[code]["title"] and title):
            unique[code] = {"code": code, "category": category,
                            "title": title, "url": href}
        if len(unique) >= 40:
            break
    return list(unique.values())


def search_catalog_html(title: str, category: str, *, timeout: float = 3.0,
                        opener=None) -> list[dict]:
    """DLsite 일반 검색 페이지 /fsr/ 요청 (JSON/AJAX API 사용 금지)."""
    if category not in CATEGORIES:
        raise ValueError("허용하지 않은 DLsite 매장")
    if not isinstance(title, str) or not (2 <= len(title) <= 160):
        return []
    # 사용자 문자열은 경로 구성 요소로만 인코딩한다.
    url = (f"https://www.dlsite.com/{category}/fsr/=/language/jp/"
           f"keyword/{quote(title, safe='')}/")
    kwargs = {"timeout": timeout}
    if opener is not None:
        kwargs["opener"] = opener
    final, html = _fetch_html(url, **kwargs)
    host = (urlsplit(final).hostname or "").casefold()
    if host != "www.dlsite.com":
        raise PublicHtmlUnavailable("공식 검색 페이지 외부로 이동")
    if "/fsr/" not in urlsplit(final).path:
        raise PublicHtmlUnavailable("검색 페이지가 다른 화면으로 이동")
    return parse_catalog_links(html, final)


def search_engine_html(title: str, provider: str, *, timeout: float = 2.8,
                       opener=None) -> list[dict]:
    """Bing/Google 일반 검색 HTML에서 DLsite 공식 작품 링크만 수집."""
    endpoints = {"bing_html": "https://www.bing.com/search",
                 "google_html": "https://www.google.com/search"}
    if provider not in endpoints:
        raise ValueError("허용하지 않은 검색 사이트")
    query = 'site:dlsite.com "' + title + '"'
    url = endpoints[provider] + "?" + urlencode({"q": query})
    kwargs = {"timeout": timeout}
    if opener is not None:
        kwargs["opener"] = opener
    final, body = _fetch_html(url, **kwargs)
    host = (urlsplit(final).hostname or "").casefold()
    valid = {"bing_html": ("www.bing.com", "bing.com"),
             "google_html": ("www.google.com", "google.com")}[provider]
    if host not in valid:
        raise PublicHtmlUnavailable("일반 검색 페이지가 외부 사이트로 이동")
    return parse_catalog_links(body, final)


def _match_score(query: str, title: str) -> int:
    left, right = normalized_title(query), normalized_title(title)
    if not left or not right or len(left) < 3:
        return 0
    if left == right:
        return 100
    if len(left) >= 7 and left in right:
        return 40
    return 0


def lookup_code(code: str, *, fetcher: Callable[[str], Product | None] = fetch_dlsite_html) -> Lookup:
    value = str(code or "").strip().upper()
    if not EXACT_CODE.fullmatch(value):
        return Lookup("code_to_title", value, "invalid",
                      warnings=("RJ/VJ/BJ/EJ + 숫자 6~8자리만 입력하세요.",))
    try:
        product = fetcher(value)
    except Exception as exc:
        return Lookup("code_to_title", value, "unavailable",
                      warnings=("공식 HTML 조회 장애: " + type(exc).__name__,))
    if product is None or product.code.upper() != value or not product.title.strip():
        return Lookup("code_to_title", value, "unavailable",
                      warnings=("공식 페이지에서 이 품번의 이름을 확인하지 못했습니다. 미등록 판정이 아닙니다.",))
    match = Match(value, product.title, product.url, product.category,
                  "official_code", "dlsite_product_html",
                  "공식 품번·상품명 확인. 게임 유형은 확인하지 않음.")
    return Lookup("code_to_title", value, "confirmed", (match,))


def lookup_title(
    raw_title: str, *,
    catalog_search: Callable[[str, str], list[dict]] = search_catalog_html,
    external_search: Callable[[str, str], list[dict]] = search_public_html,
    engine_search: Callable[[str, str], list[dict]] = search_engine_html,
    fetcher: Callable[[str], Product | None] = fetch_dlsite_html,
) -> Lookup:
    raw = str(raw_title or "")
    title = cleaned_search_title(raw)

    # The archive filename already contains a DLsite product ID:
    # do not discard it and perform a noisy search for a translated title.
    known_codes = tuple(dict.fromkeys(match.group(1).upper()
                                      for match in CODE_PATTERN.finditer(raw)))
    if known_codes:
        found = []
        warnings = []
        for code in known_codes[:MAX_CANDIDATES]:
            try:
                product = fetcher(code)
            except Exception as exc:
                product = None
                warnings.append(f"{code} 공식 상품 HTML 조회 장애: {type(exc).__name__}")
            if product is not None and product.code.upper() == code and product.title.strip():
                found.append(Match(
                    code, product.title, product.url, product.category,
                    "filename_code_verified", "dlsite_product_html",
                    "파일명에 있는 품번을 추출하고 동일 품번의 공식 상품명을 확인함. "
                    "번역명·파일 내용은 검증하지 않음."))
            else:
                found.append(Match(
                    code, "", "", "", "filename_code_only", "archive_filename",
                    "파일명에서 품번을 추출함. 공식 상품 정보는 확인하지 못했음."))
        if len(known_codes) > 1:
            warnings.append("파일명에 여러 DLsite 품번이 있습니다. 동일 작품 여부를 자동 결정하지 않습니다.")
        if len(known_codes) > MAX_CANDIDATES:
            warnings.append("품번이 많아 상위 8개만 표시했습니다.")
        if any(match.confidence == "filename_code_only" for match in found):
            warnings.append("파일명에 적힌 품번은 공식 작품번호라고 검증된 것은 아닙니다.")
        state = ("confirmed" if len(found) == 1 and
                 found[0].confidence == "filename_code_verified" else "candidates")
        return Lookup("title_to_code", title or raw, state, tuple(found),
                      tuple(warnings), providers=())

    if not (2 <= len(title) <= 160) or not any(ch.isalpha() for ch in title):
        return Lookup("title_to_code", title, "invalid",
                      warnings=("검색할 작품명을 2~160자로 입력하세요.",))
    hits = {}
    providers = []
    warnings = []

    def add_hit(item: dict, source: str):
        url = str(item.get("url") or item.get("href") or "")
        code_cat = product_page_candidate(url)
        if not code_cat:
            return
        code, category = code_cat
        heading = str(item.get("title") or "")
        if code not in hits:
            hits[code] = {"code": code, "category": category, "url": url,
                          "title": heading[:240], "source": source}
        elif _match_score(title, heading) > _match_score(title, hits[code]["title"]):
            hits[code].update({"title": heading[:240], "source": source})

    # DLsite 공식 검색을 우선; 2곳에서 비어 있으면 다른 카테고리까지 보충.
    for category in CATEGORIES:
        if category in ("soft", "girls") and hits:
            break
        try:
            results = catalog_search(title, category) or []
            providers.append({"provider": "dlsite_" + category, "state": "ok",
                              "count": len(results)})
            for item in results[:40]:
                if isinstance(item, dict):
                    add_hit(item, "dlsite_search_html")
        except Exception as exc:
            providers.append({"provider": "dlsite_" + category, "state": "error",
                              "detail": type(exc).__name__})
            warnings.append(f"DLsite {category} 검색 장애: {type(exc).__name__}")

    # 공식 검색에서 링크를 찾지 못한 때만 일반 HTML 검색에 'DLsite' 제한어 사용.
    if not hits:
        for provider in ("bing_html", "google_html", "ddg_html", "mojeek_html"):
            try:
                if provider in ("bing_html", "google_html"):
                    results = engine_search(title, provider) or []
                else:
                    results = external_search('site:dlsite.com "' + title + '"', provider) or []
                providers.append({"provider": provider, "state": "ok",
                                  "count": len(results)})
                for item in results[:12]:
                    if isinstance(item, dict):
                        add_hit(item, provider)
                if hits:
                    break
            except Exception as exc:
                providers.append({"provider": provider, "state": "error",
                                  "detail": type(exc).__name__})
                warnings.append(f"{provider} 검색 장애: {type(exc).__name__}")

    if not hits:
        state = ("unavailable" if providers and all(
            p["state"] == "error" for p in providers) else "no_candidate")
        warnings.append("품번을 찾지 못했습니다. 작품이 없다는 뜻은 아닙니다.")
        return Lookup("title_to_code", title, state, warnings=tuple(warnings),
                      providers=tuple(providers))

    ranked = sorted(hits.values(), key=lambda h: _match_score(title, h["title"]),
                    reverse=True)
    output = []
    for item in ranked[:MAX_CANDIDATES]:
        product = None
        if len(output) < MAX_VERIFY:
            try:
                product = fetcher(item["code"])
            except Exception as exc:
                warnings.append(f"{item['code']} 공식 페이지 조회 장애: {type(exc).__name__}")
        if product is not None and product.code.upper() == item["code"]:
            match_quality = _match_score(title, product.title)
            # A valid product ID is not evidence that the game name matched.
            # Reject e.g. "NOR"/"REC" website menu recommendations.
            if max(match_quality, _match_score(title, item["title"])) == 0:
                continue
            output.append(Match(
                item["code"], product.title, product.url, product.category,
                "exact_title" if match_quality == 100 else "official_code",
                "dlsite_product_html",
                ("공식 페이지에서 제목 일치" if match_quality == 100 else
                 "품번·상품명 확인; 정식 제목의 일부만 일치하여 수동 검토 필요")))
        elif _match_score(title, item["title"]) > 0:
            output.append(Match(
                item["code"], item["title"], item["url"], item["category"],
                "search_candidate", item["source"],
                "검색 링크의 제목이 일부 일치하지만 공식 상품 페이지는 미확인"))
    if not output:
        warnings.append("웹 검색에 작품 링크가 있었으나 입력 이름과 연관성이 없어 제외했습니다.")
    state = ("confirmed" if any(m.confidence == "exact_title" for m in output)
             else "candidates" if output else "no_candidate")
    if len(ranked) > MAX_CANDIDATES:
        warnings.append("후보가 많아 상위 8개만 표시했습니다.")
    return Lookup("title_to_code", title, state, tuple(output),
                  tuple(warnings), tuple(providers))
