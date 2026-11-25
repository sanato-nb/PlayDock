"""독립 DLsite 등록·게임 유형 판별 실험 모듈.

본체 Library/DB/Qt를 import하지 않으며 파일을 쓰지 않는다.
품번/제목 힌트 -> DLsite 원본 JSON의 동일 품번 확인 -> work_type 분류.
실패·무응답은 '등록되지 않음'이 아니라 '미확인/조회 불가'이다.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Callable
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit, urlencode
from urllib.request import Request, urlopen
import json
import re

from .search_terms import cleaned_search_title, search_title_variants


CATEGORIES = ("maniax", "home", "soft", "girls", "pro")
CODE_PATTERN = re.compile(r"(?<![A-Za-z0-9])((?:RJ|VJ|BJ|EJ)\d{6,8})(?![A-Za-z0-9])", re.I)
EXACT_CODE = re.compile(r"(?:RJ|VJ|BJ|EJ)\d{6,8}", re.I)
PRODUCT_PAGE = re.compile(r"/(?P<category>maniax|home|soft|girls|pro)/work/=/product_id/(?P<code>(?:RJ|VJ|BJ|EJ)\d{6,8})\.html(?:$|/)", re.I)
# '기타'와 원인 불명 유형은 게임이라고 단정하지 않는다.
GAME_TYPES = frozenset({"ACN", "ACT", "ADV", "AVG", "DNV", "RPG", "SLG", "SLN", "SIM", "STG", "PZL", "QIZ", "TBL", "TYP"})
NON_GAME_TYPES = frozenset({"SOU", "ICG", "MNG", "SCM", "WBT", "MOV", "NRE", "KSV"})
MAX_RESPONSE = 1_000_000
MAX_SEARCH_RESULTS = 12
MAX_CANDIDATES = 3

LABELS = {
    "confirmed_game": "DLsite 등록 게임 확인",
    "registered_non_game": "DLsite 등록 · 비게임으로 추정",
    "registered_type_unknown": "DLsite 등록 확인 · 게임 여부 미확인",
    "needs_review": "DLsite 후보 확인 필요",
    "unverified": "DLsite 등록 미확인",
    "lookup_unavailable": "DLsite 조회 불가",
    "input_error": "입력 오류",
}


@dataclass(frozen=True)
class Product:
    code: str
    title: str
    work_type: str
    category: str
    url: str


@dataclass(frozen=True)
class Detection:
    status: str
    query: str
    code: str = ""
    work_title: str = ""
    work_type: str = ""
    page_url: str = ""
    code_origin: str = ""
    title_match: bool | None = None
    possible_codes: tuple[str, ...] = ()
    reason: str = ""

    @property
    def label(self) -> str:
        return LABELS[self.status]

    def to_dict(self) -> dict:
        value = asdict(self)
        value["label"] = self.label
        return value


class LookupUnavailable(RuntimeError):
    """차단·통신 실패·응답 형식 오류 등으로 확인할 수 없음."""


def extract_code(text: str) -> str:
    hit = CODE_PATTERN.search(text or "")
    return hit.group(1).upper() if hit else ""


def _clean_input_title(raw: str) -> str:
    """경로를 전달하거나 검색하지 않고, 파일명에서 필요 없는 확장자만 제거한다."""
    name = re.split(r"[/\\]", raw or "")[-1].strip()
    return re.sub(r"\.(?:zip|7z|rar)$", "", name, flags=re.I)


def normalized_title(raw: str) -> str:
    title = cleaned_search_title(raw).casefold()
    return "".join(ch for ch in title if ch.isalnum())


def _payload_for_code(raw, code: str, depth: int = 0) -> dict | None:
    """응답 배열·코드 키·data/items/products 래퍼를 지원하고 타 작품은 거절한다."""
    if depth > 6:
        return None
    if isinstance(raw, list):
        for row in raw[:40]:
            candidate = _payload_for_code(row, code, depth + 1)
            if candidate:
                return candidate
        return None
    if not isinstance(raw, dict):
        return None
    # 실제 DLsite 응답은 { "RJ01234567": {...} } 형태로 올 수 있다.
    for key, value in raw.items():
        if isinstance(key, str) and key.upper() == code and isinstance(value, dict):
            ident = value.get("workno") or value.get("work_no") or value.get("product_id") or value.get("work_id")
            if ident is not None and str(ident).upper() != code:
                return None
            return {**value, "workno": code}
    ident = raw.get("workno") or raw.get("work_no") or raw.get("product_id") or raw.get("work_id")
    if ident is not None:
        return raw if str(ident).upper() == code else None
    for field in ("products", "items", "data"):
        if field in raw:
            candidate = _payload_for_code(raw[field], code, depth + 1)
            if candidate:
                return candidate
    return None


def parse_product(raw, code: str, category: str) -> Product | None:
    """다른 품번·이름 없는 응답을 일치 증거로 사용하지 않는다."""
    code = (code or "").strip().upper()
    if not EXACT_CODE.fullmatch(code) or category not in CATEGORIES:
        raise ValueError("올바른 DLsite 작품 코드 또는 카테고리가 아닙니다.")
    item = _payload_for_code(raw, code)
    if not item:
        return None
    name = item.get("work_name") or item.get("name") or item.get("title")
    if not isinstance(name, str):
        return None
    name = " ".join(name.split())[:240]
    if len(name) < 2 or "<" in name or ">" in name or "***" in name:
        return None
    work_type = item.get("work_type") or item.get("work_type_code") or ""
    work_type = str(work_type).strip().upper()[:30] if isinstance(work_type, str) else ""
    return Product(
        code, name, work_type, category,
        f"https://www.dlsite.com/{category}/work/=/product_id/{code}.html",
    )


def fetch_product(code: str, *, opener=urlopen, categories=CATEGORIES, timeout: float = 8.0) -> Product | None:
    """단일 품번에 한해 비공식 DLsite 작품 JSON을 최대 5개 구역에서 확인한다.

    응답 404나 데이터 없음만으로 비등록이라고 판단하지 않는다.
    보호된 페이지·HTTP 403/429·네트워크 오류는 별도로 표시한다.
    """
    code = (code or "").strip().upper()
    if not EXACT_CODE.fullmatch(code):
        raise ValueError("RJ/VJ/BJ/EJ + 숫자 6~8자리의 품번을 입력하세요.")
    failures = []
    for category in categories:
        if category not in CATEGORIES:
            raise ValueError("허용되지 않은 DLsite 카테고리입니다.")
        url = (f"https://www.dlsite.com/{category}/api/=/product.json?"
               + urlencode({"workno": code, "locale": "ja_JP"}))
        request = Request(url, headers={
            "User-Agent": "PlayDock-DLsite-Detector-Experiment/0.1",
            "Accept": "application/json",
        })
        try:
            with opener(request, timeout=timeout) as response:
                if getattr(response, "status", 200) != 200:
                    failures.append(f"HTTP {response.status}")
                    continue
                content = response.read(MAX_RESPONSE + 1)
            if len(content) > MAX_RESPONSE:
                failures.append("응답 크기 제한 초과")
                continue
            item = parse_product(json.loads(content.decode("utf-8-sig")), code, category)
            if item:
                return item
        except HTTPError as exc:
            if exc.code not in (404, 410):
                failures.append(f"HTTP {exc.code}")
        except (URLError, TimeoutError, ConnectionError, OSError, ValueError,
                TypeError, UnicodeError, json.JSONDecodeError) as exc:
            failures.append(type(exc).__name__)
    if failures:
        raise LookupUnavailable("일부 DLsite 조회에 실패했습니다: " + ", ".join(failures[:4]))
    return None


def product_page_candidate(raw_url: str) -> tuple[str, str] | None:
    """검색 결과가 실제 DLsite HTTPS 작품 페이지일 때만 후보 품번을 받아들인다."""
    try:
        parts = urlsplit(raw_url)
        host = (parts.hostname or "").lower().rstrip(".")
        if (parts.scheme != "https" or parts.username or parts.password
                or host not in ("dlsite.com", "www.dlsite.com", "dlsite.jp", "www.dlsite.jp")):
            return None
        match = PRODUCT_PAGE.search(parts.path)
        if match:
            return match.group("code").upper(), match.group("category").lower()
    except (TypeError, ValueError, AttributeError):
        return None
    return None


def dlsite_search_hits(title: str) -> list[dict]:
    """명시적 제목 조회 시에만 공개 검색 결과를 받아온다. 구매/계정 API 사용 없음."""
    try:
        from ddgs import DDGS
    except ImportError as exc:
        raise LookupUnavailable("제목 검색에는 ddgs 설치가 필요합니다.") from exc
    with DDGS(timeout=12) as client:
        return list(client.text(f'site:dlsite.com "{title}"', max_results=MAX_SEARCH_RESULTS) or [])


def _result_for_product(query: str, item: Product, *, origin: str,
                        candidate_codes: tuple[str, ...] = ()) -> Detection:
    local_title = normalized_title(query)
    official_title = normalized_title(item.title)
    exact_match = bool(local_title and official_title and local_title == official_title)
    if item.work_type in NON_GAME_TYPES:
        status = "registered_non_game"
        reason = f"DLsite 품번은 확인됐고 작품 형식 {item.work_type}은 비게임으로 추정됩니다."
    elif item.work_type not in GAME_TYPES:
        status = "registered_type_unknown"
        reason = f"DLsite 작품은 확인됐으나 작품 형식 {item.work_type or '미제공'}으로 게임 여부를 확정할 수 없습니다."
    elif local_title and not exact_match:
        status = "needs_review"
        reason = "DLsite에 게임 형식으로 등록됐지만 로컬 제목과 공식 제목이 일치하지 않습니다. 수동 확인이 필요합니다."
    else:
        status = "confirmed_game"
        reason = f"DLsite 동일 품번 및 게임 작품 형식({item.work_type})을 확인했습니다."
    return Detection(
        status, query, code=item.code, work_title=item.title,
        work_type=item.work_type, page_url=item.url,
        code_origin=origin, title_match=exact_match if local_title else None,
        possible_codes=candidate_codes, reason=reason,
    )


def detect_dlsite_game(title: str, *, code: str = "",
                       fetcher: Callable[[str], Product | None] = fetch_product,
                       searcher: Callable[[str], list[dict]] | None = dlsite_search_hits,
                       allow_title_search: bool = False) -> Detection:
    """조회만 수행하며 저장하지 않는다. 본체/UI/DB 연결 없는 독립 실험 API.

    제목만 있을 때 웹 검색은 allow_title_search=True로 명시적으로 활성화한다.
    결과를 얻지 못한 경우 'DLsite에 없음'으로 판정하지 않는다.
    """
    raw = (title or "").strip()
    query = _clean_input_title(raw)
    explicit = (code or "").strip().upper()
    if explicit and not EXACT_CODE.fullmatch(explicit):
        return Detection("input_error", query, reason="입력한 작품 코드 형식이 올바르지 않습니다.")
    selected_code = explicit or extract_code(query)
    if selected_code:
        origin = "explicit_code" if explicit else "filename_code"
        try:
            item = fetcher(selected_code)
        except (LookupUnavailable, OSError, TimeoutError, ValueError, LookupError) as exc:
            return Detection("lookup_unavailable", query, code=selected_code,
                             code_origin=origin, reason=str(exc))
        if item is None:
            return Detection("unverified", query, code=selected_code, code_origin=origin,
                             reason="동일 품번의 공개 작품 정보를 확인하지 못했습니다. 미등록이라는 뜻은 아닙니다.")
        # 의존성 주입된 조회 결과도 동일 품번이어야 한다.
        if item.code != selected_code:
            return Detection("unverified", query, code=selected_code, code_origin=origin,
                             reason="조회 결과의 작품 코드가 달라 확인하지 않았습니다.")
        return _result_for_product(query, item, origin=origin)

    if not query or not normalized_title(query):
        return Detection("input_error", query, reason="검색할 게임 이름 또는 작품 코드를 입력하세요.")
    if not allow_title_search:
        return Detection("unverified", query, reason="작품 코드가 없습니다. 제목 검색을 실행해야 확인할 수 있습니다.")
    if searcher is None:
        return Detection("lookup_unavailable", query, reason="제목 검색 기능이 연결되지 않았습니다.")

    # 정확한 작품명이 파일명에 가려져 있을 수 있으므로, 정리한 제목을
    # 먼저 검색하고 증거가 없으면 원본 제목을 최대 한 차례 다시 시도한다.
    queries = search_title_variants(query)
    rows = []
    errors = []
    for title_query in queries:
        try:
            found_rows = searcher(title_query) or []
            rows.extend(found_rows[:MAX_SEARCH_RESULTS])
        except Exception as exc:
            errors.append(type(exc).__name__)
    if not rows and errors:
        return Detection("lookup_unavailable", query,
                         reason="DLsite 제목 검색 실패: " + ", ".join(errors))
    candidates: dict[str, str] = {}
    for row in rows[:2 * MAX_SEARCH_RESULTS]:
        if not isinstance(row, dict):
            continue
        hit = product_page_candidate(str(row.get("href") or row.get("url") or ""))
        if hit:
            candidate_code, category = hit
            candidates.setdefault(candidate_code, category)
    codes = tuple(candidates)
    if not codes:
        status = "lookup_unavailable" if errors else "unverified"
        return Detection(status, query,
                         reason="공개 검색에서 DLsite 작품 페이지를 확인하지 못했습니다. "
                                + ("일부 검색 오류: " + ", ".join(errors) if errors
                                   else "DLsite에 없다는 증거는 아닙니다."))
    if len(codes) > MAX_CANDIDATES:
        return Detection("needs_review", query, possible_codes=codes,
                         reason="검색된 DLsite 품번이 많아 자동 선택하지 않았습니다.")

    verified = []
    unavailable = False
    for candidate_code in codes:
        try:
            item = fetcher(candidate_code)
        except (LookupUnavailable, OSError, TimeoutError, ValueError, LookupError):
            unavailable = True
            continue
        if item is not None and item.code == candidate_code:
            verified.append(item)
    if not verified:
        return Detection("lookup_unavailable" if unavailable else "unverified", query,
                         possible_codes=codes, reason="후보 품번은 나왔지만 DLsite 원본 작품 정보로 검증하지 못했습니다.")

    exact = [item for item in verified if normalized_title(item.title) == normalized_title(query)]
    if len(exact) == 1:
        return _result_for_product(query, exact[0], origin="title_search", candidate_codes=codes)
    if len(exact) > 1:
        return Detection("needs_review", query, possible_codes=codes,
                         reason="같은 제목으로 확인된 DLsite 작품이 여러 개여서 선택이 필요합니다.")
    item = verified[0]
    return Detection(
        "needs_review", query, code=item.code, work_title=item.title,
        work_type=item.work_type, page_url=item.url,
        code_origin="title_search", title_match=False,
        possible_codes=codes,
        reason="검색 후보의 품번은 실제지만 로컬 게임과 같은 작품인지 확인되지 않았습니다.",
    )
