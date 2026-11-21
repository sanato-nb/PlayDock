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
from .metasearch_no_key import search_meta_no_key
from .bing_rss import search_bing_rss
from .multilingual_search import title_candidates, explicit_original_titles
from .search_terms import cleaned_search_title, title_web_queries

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
           f"keyword/{quote(title, safe='').replace('%20', '+')}/")
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
    """제목을 따옴표로 묶지 않고 웹 전체에서 검색해 공식 링크와 품번 힌트를 수집."""
    endpoints = {"bing_html": "https://www.bing.com/search",
                 "google_html": "https://www.google.com/search"}
    if provider not in endpoints:
        raise ValueError("허용하지 않은 검색 사이트")
    # 번역 제목과 원제가 서로 다를 수 있으므로 정확 문구 일치/도메인 한정 금지.
    query = title + " DLsite RJ"
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
    rows = parse_catalog_links(body, final)
    rows.extend(parse_web_code_hints(body, final, title))
    return rows



class _WebCodeAnchors(HTMLParser):
    """검색 결과의 링크 제목에 명시된 작품번호 힌트만 채집."""
    def __init__(self, base_url: str):
        super().__init__(convert_charrefs=True)
        self.base_url = base_url
        self.current = None
        self.rows = []

    def handle_starttag(self, tag, attrs):
        if tag == "a" and self.current is None:
            props = dict(attrs)
            href = urljoin(self.base_url, unescape(props.get("href") or ""))
            self.current = {"href": href, "text": [props.get("title") or ""]}
        elif tag == "img" and self.current is not None:
            self.current["text"].append(dict(attrs).get("alt") or "")

    def handle_data(self, data):
        if self.current is not None:
            self.current["text"].append(data)

    def handle_endtag(self, tag):
        if tag == "a" and self.current is not None:
            title = re.sub(r"\s+", " ", " ".join(self.current["text"])).strip()
            if title and CODE_PATTERN.search(title):
                self.rows.append({"title": title[:240], "url": self.current["href"]})
            self.current = None


def parse_web_code_hints(html: str, base_url: str, title: str) -> list[dict]:
    """제3자 검색결과의 링크 '한국어 게임명 [RJ...]'을 별도 근거로 수집.

    이 URL은 공식 확인 근거가 아니며 같은 품번의 DLsite HTML 재확인을 요구한다.
    """
    if len(normalized_title(title)) < 5:
        return []
    parser = _WebCodeAnchors(base_url)
    parser.feed(html)
    found = []
    seen = set()
    for item in parser.rows:
        href = item["url"]
        parts = urlsplit(href)
        if parts.scheme not in ("https", "http") or not parts.hostname:
            continue
        if parts.hostname.endswith(("google.com", "bing.com")) and "/search" in parts.path:
            continue
        code_hits = tuple(dict.fromkeys(m.group(1).upper()
                    for m in CODE_PATTERN.finditer(item["title"])))
        if len(code_hits) != 1 or code_hits[0] in seen:
            continue
        if _match_score(title, item["title"]) == 0:
            continue
        seen.add(code_hits[0])
        found.append(item)
        if len(found) >= MAX_CANDIDATES:
            break
    return found


def _match_score(query: str, title: str) -> int:
    left, right = normalized_title(query), normalized_title(title)
    if not left or not right or len(left) < 3:
        return 0
    if left == right:
        return 100
    # 짧은 한글 번역 제목도 뒤에 RJ코드/제작사 표기가 붙을 수 있다.
    # 'NOR', 'REC' 같은 짧은 라틴 일반어는 기존처럼 부분 일치 불허.
    if (len(left) >= 7 or
        (len(left) >= 5 and any("가" <= ch <= "힣" for ch in left))):
        if left in right:
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
    meta_search: Callable[[str], list[dict]] | None = None,
    rss_search: Callable[[str], list[dict]] | None = None,
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
    seed_names = title_candidates(raw)
    if not seed_names:
        seed_names = (title,)
    search_names = list(seed_names)
    discovered_aliases: list[str] = []
    hits = {}
    providers = []
    warnings = []

    def register_explicit_originals(rows):
        for alias in explicit_original_titles(rows, tuple(seed_names)):
            if alias not in search_names and len(discovered_aliases) < 2:
                discovered_aliases.append(alias)
                search_names.append(alias)

    def relevant_hit_exists():
        return any(max(_match_score(n, row["title"]) for n in search_names) > 0
                   for row in hits.values())

    def add_hit(item: dict, source: str):
        url = str(item.get("url") or item.get("href") or "")
        code_cat = product_page_candidate(url)
        heading = str(item.get("title") or "")
        summary = str(item.get("body") or "")[:420]
        # 웹 제목과 요약문은 유효한 검색 근거지만 원본 공식 제목은 아니다.
        evidence = (heading + " " + summary).strip()[:640]
        if code_cat:
            code, category = code_cat
        elif source in ("bing_html", "google_html", "ddg_html", "mojeek_html", "ddgs_meta", "bing_rss"):
            # 비공식 사이트에서 발견한 품번은 최종 확인이 아니며,
            # 반드시 원문 검색 제목과 연결된 링크일 때만 잠정 후보로 수용.
            codes = tuple(dict.fromkeys(m.group(1).upper()
                       for m in CODE_PATTERN.finditer(evidence)))
            if len(codes) != 1 or max(_match_score(n, evidence) for n in search_names) == 0:
                return
            code, category = codes[0], ""
            url = ""  # 외부 사이트 URL을 DLsite 공식 페이지로 가장하지 않는다.
        else:
            return
        if code not in hits:
            hits[code] = {"code": code, "category": category, "url": url,
                          "title": evidence if source in ("ddgs_meta", "bing_rss") else heading[:240],
                          "source": source}
        elif max(_match_score(n, heading) for n in search_names) > max(
                _match_score(n, hits[code]["title"]) for n in search_names):
            hits[code].update({"title": heading[:240], "source": source})

    # 검색 우선순위: DLsite 공식 카탈로그 → Bing RSS → DDGS.
    # 기본 검색기는 외부 주입 검색기가 없는 경우에만 자동 연결한다.
    if meta_search is None and (
            catalog_search is search_catalog_html and
            external_search is search_public_html and
            engine_search is search_engine_html):
        meta_search = search_meta_no_key
    if rss_search is None and (
            catalog_search is search_catalog_html and
            external_search is search_public_html and
            engine_search is search_engine_html):
        rss_search = search_bing_rss

    catalog_queried: set[tuple[str, str]] = set()

    def search_official_catalog(names, *, max_calls: int, first_all_categories: bool):
        """결과에 있는 링크를 수집하되 관련 후보가 나오면 불필요한 추가 요청을 생략."""
        calls = 0
        for name_index, candidate_name in enumerate(names):
            categories = (CATEGORIES if first_all_categories and name_index == 0
                          else ("maniax", "home"))
            for category in categories:
                if calls >= max_calls or relevant_hit_exists():
                    break
                pair = (candidate_name, category)
                if pair in catalog_queried:
                    continue
                catalog_queried.add(pair)
                calls += 1
                try:
                    results = catalog_search(candidate_name, category) or []
                    providers.append({"provider": "dlsite_" + category,
                                      "query": candidate_name,
                                      "state": "ok", "count": len(results)})
                    for item in results[:40]:
                        if isinstance(item, dict):
                            add_hit(item, "dlsite_search_html")
                except Exception as exc:
                    detail = (str(exc)[:160] if isinstance(exc, PublicHtmlUnavailable)
                              else type(exc).__name__)
                    providers.append({"provider": "dlsite_" + category,
                                      "query": candidate_name,
                                      "state": "error", "detail": detail})
                    warnings.append(f"DLsite {category} 검색 장애: {detail}")
            if calls >= max_calls or relevant_hit_exists():
                break

    # 1순위: 파일명에 실제 표기된 한국어/영어/일본어 이름을 공식 사이트에서 검색.
    # 첫 번째 별칭 4개 카테고리, 나머지는 2개씩 총 8회 이하.
    search_official_catalog(seed_names, max_calls=8, first_all_categories=True)

    # 2순위: 공식 검색에서 일치 후보가 없을 때만 API 키 없는 Bing RSS를 사용.
    # 비공식 웹 정보는 검증 근거가 아닌 '후보'이며 원제가 명시되면 별칭에 등록.
    if rss_search is not None and not relevant_hit_exists():
        for candidate_name in seed_names[:2]:
            try:
                results = rss_search(candidate_name) or []
                providers.append({"provider": "bing_rss", "query": candidate_name,
                                  "state": "ok", "count": len(results)})
                register_explicit_originals(results)
                for item in results[:12]:
                    if isinstance(item, dict):
                        add_hit(item, "bing_rss")
                if relevant_hit_exists():
                    break
            except Exception as exc:
                detail = (str(exc)[:200] if isinstance(exc, PublicHtmlUnavailable)
                          else type(exc).__name__)
                providers.append({"provider": "bing_rss", "query": candidate_name,
                                  "state": "error", "detail": detail})
                warnings.append("Bing RSS 검색 장애: " + detail)

    # 3순위: DLsite/Bing RSS로도 관련 품번을 얻지 못했을 때만 DDGS 시도.
    # DuckDuckGo/Brave/Bing 백엔드는 기존 DDGS 래퍼에서 각각 실패를 처리한다.
    if meta_search is not None and not relevant_hit_exists():
        for candidate_name in search_names:
            try:
                results = meta_search(candidate_name) or []
                providers.append({"provider": "ddgs_meta", "query": candidate_name,
                                  "state": "ok", "count": len(results)})
                for item in results[:12]:
                    if isinstance(item, dict):
                        add_hit(item, "ddgs_meta")
                register_explicit_originals(results)
                if relevant_hit_exists():
                    break
            except Exception as exc:
                detail = (str(exc)[:200] if isinstance(exc, PublicHtmlUnavailable)
                          else type(exc).__name__)
                providers.append({"provider": "ddgs_meta", "query": candidate_name,
                                  "state": "error", "detail": detail})
                warnings.append("DDGS 자동 검색 장애: " + detail)

    # Bing RSS / DDGS에서 발견한 *명시적 일본어 원제*는 공식 카탈로그에 재조회.
    # 원래 제목과 동일 검색은 건너뛰며 별칭 2개 × 2개 카테고리(최대 4회).
    if discovered_aliases and not relevant_hit_exists():
        search_official_catalog(discovered_aliases[:2], max_calls=4,
                                first_all_categories=False)

    # 공식·RSS 결과가 없을 때만 기존 HTML 검색 경로를 보충 사용한다.

    if not relevant_hit_exists():
        for candidate_name in search_names[:3]:
            for provider in ("bing_html", "google_html", "ddg_html", "mojeek_html"):
                try:
                    if provider in ("bing_html", "google_html"):
                        results = engine_search(candidate_name, provider) or []
                    else:
                        results = external_search(candidate_name + " DLsite RJ", provider) or []
                    providers.append({"provider": provider, "query": candidate_name,
                                      "state": "ok", "count": len(results)})
                    register_explicit_originals(results)
                    for item in results[:12]:
                        if isinstance(item, dict):
                            add_hit(item, provider)
                    if relevant_hit_exists():
                        break
                except Exception as exc:
                    providers.append({"provider": provider, "query": candidate_name,
                                      "state": "error", "detail": type(exc).__name__})
                    warnings.append(f"{provider} 검색 장애: {type(exc).__name__}")
            if relevant_hit_exists():
                break

    if not relevant_hit_exists():
        official = [p for p in providers if p["provider"].startswith("dlsite_")]
        official_blocked = bool(official) and all(p["state"] == "error" for p in official)
        state = ("unavailable" if official_blocked or (
            providers and all(p["state"] == "error" for p in providers))
            else "no_candidate")
        warnings.append(
            "공식 DLsite 검색이 모두 실패했고 다른 검색에서도 유효한 품번을 얻지 못했습니다."
            if official_blocked else
            "품번 후보를 찾지 못했습니다. 작품이 없다는 뜻은 아닙니다."
        )
        return Lookup("title_to_code", title, state, warnings=tuple(warnings),
                      providers=tuple(providers))

    ranked = sorted(
        (hit for hit in hits.values()
         if max(_match_score(n, hit["title"]) for n in search_names) > 0),
        key=lambda h: max(_match_score(n, h["title"]) for n in search_names),
        reverse=True,
    )
    output = []
    for item in ranked[:MAX_CANDIDATES]:
        product = None
        if len(output) < MAX_VERIFY:
            try:
                product = fetcher(item["code"])
            except Exception as exc:
                warnings.append(f"{item['code']} 공식 페이지 조회 장애: {type(exc).__name__}")
        if product is not None and product.code.upper() == item["code"]:
            match_quality = max(_match_score(n, product.title) for n in seed_names)
            alias_quality = max((_match_score(n, product.title)
                                 for n in discovered_aliases), default=0)
            # A valid product ID is not evidence that the game name matched.
            # Reject e.g. "NOR"/"REC" website menu recommendations.
            if max(match_quality, alias_quality, *(
                    _match_score(n, item["title"]) for n in search_names)) == 0:
                continue
            output.append(Match(
                item["code"], product.title, product.url, product.category,
                "exact_title" if match_quality == 100 else "official_code",
                "dlsite_product_html" if item["source"] == "dlsite_search_html" else item["source"],
                ("공식 페이지에서 제목 일치" if match_quality == 100 else
                 "웹 제목에 품번이 함께 표시되고 공식 상품번호를 확인함. 번역명 일치는 미확인." if not item["url"] else
                 "품번·상품명 확인; 정식 제목의 일부만 일치하여 수동 검토 필요")))
        elif max(_match_score(n, item["title"]) for n in search_names) > 0:
            output.append(Match(
                item["code"], item["title"], item["url"], item["category"],
                "search_candidate", item["source"],
                "웹 검색 결과에 제목과 품번이 보이나 공식 작품 페이지는 미확인"))
    if not output:
        warnings.append("웹 검색에 작품 링크가 있었으나 입력 이름과 연관성이 없어 제외했습니다.")
    state = ("confirmed" if len(output) == 1 and output[0].confidence == "exact_title"
             else "candidates" if output else "no_candidate")
    if len(ranked) > MAX_CANDIDATES:
        warnings.append("후보가 많아 상위 8개만 표시했습니다.")
    return Lookup("title_to_code", title, state, tuple(output),
                  tuple(warnings), tuple(providers))
