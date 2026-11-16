"""Optional, no-key public product-title lookup for local game library.

Reads only public metadata from DLsite; never sends file paths or installs
anything, and never modifies archive filenames. A user confirms all updates.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
import json
import re
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from core import load_json, save_json

PRODUCT_CODE = re.compile(r"(?<![A-Z0-9])((?:RJ|VJ|BJ|EJ)\d{6,8})(?!\d)", re.I)
TAG = re.compile(r"\[([^\[\]]{1,70})\]")
DLSITE_CATEGORIES = ("maniax", "home", "soft", "girls")
CACHE_DAYS = 30

# A minimal, individually cross-checked Korean display alias; these never
# overwrite the developer's published title unless a user approves the preview.
# Keep additional aliases out until independently verified.
VERIFIED_KOREAN_ALIASES = {"RJ01373814": "메시아 오브 로리타"}
# Source-cross-checked public work ID/original-title mapping. A local entry is
# NOT a live verification of the publisher page; the UI labels it accordingly.
CROSSCHECKED_OFFLINE_TITLES = {"RJ01081508": "6月の君と僕"}


def extract_code(*text_values: str) -> str | None:
    for value in text_values:
        match = PRODUCT_CODE.search(value or "")
        if match:
            return match.group(1).upper()
    return None


def clean_title(raw: str) -> str | None:
    if not isinstance(raw, str):
        return None
    title = re.sub(r"\s+", " ", raw).strip()
    if not 2 <= len(title) <= 240:
        return None
    # Reject obvious site masking placeholders and pseudo HTML results.
    if "<" in title or ">" in title or "***" in title:
        return None
    if re.fullmatch(r"[\W_0-9]+", title):
        return None
    return title


def display_title(official_title: str, original_display: str, code: str) -> str:
    """Preserve local build/patch tags; metadata cannot infer archive version."""
    title = clean_title(official_title)
    if not title:
        raise ValueError("정상적인 제목이 아닙니다.")
    # Preserve [v...], [수정2], [번역...], etc., but never duplicate RJ code.
    preserved = []
    seen = {title.casefold(), code.casefold()}
    for bracket in TAG.findall(original_display):
        label = bracket.strip()
        if not label or label.casefold() in seen or PRODUCT_CODE.fullmatch(label):
            continue
        if label.casefold() not in seen:
            preserved.append(f"[{label}]")
            seen.add(label.casefold())
    if code.casefold() not in title.casefold():
        preserved.append(f"[{code}]")
    return " ".join([title, *preserved]).strip()


def _parse_response(value, code: str) -> str | None:
    """Accept published DLsite product.json shapes, require an ID match."""
    if isinstance(value, dict):
        # Some API variants key the response by work number.
        if code in value:
            return _parse_response(value[code], code)
        for key in ("products", "items", "data"):
            if key in value and isinstance(value[key], (dict, list)):
                found = _parse_response(value[key], code)
                if found:
                    return found
        identity = value.get("workno") or value.get("work_no") or value.get("product_id") or value.get("work_id")
        if identity is not None and str(identity).upper() != code:
            return None
        # No ID inside a single object is ambiguous: do not assign it to a code.
        if identity is None:
            return None
        for key in ("work_name", "name", "title"):
            valid = clean_title(value.get(key))
            if valid:
                return valid
    if isinstance(value, list):
        for item in value:
            found = _parse_response(item, code)
            if found:
                return found
    return None


def _fetch_official(code: str, timeout: float = 6.0, opener=urlopen, locale: str = "ko_KR") -> tuple[str, str] | None:
    params = urlencode({"workno": code, "locale": locale})
    for category in DLSITE_CATEGORIES:
        url = f"https://www.dlsite.com/{category}/api/=/product.json?{params}"
        req = Request(url, headers={"User-Agent": "PlayDock/0.4 (local product metadata lookup)", "Accept": "application/json"})
        try:
            with opener(req, timeout=timeout) as res:
                raw = res.read(1_000_001)
            if len(raw) > 1_000_000:
                continue
            payload = json.loads(raw.decode("utf-8-sig"))
            title = _parse_response(payload, code)
            if title:
                return title, url
        except (HTTPError, URLError, TimeoutError, ConnectionError, OSError, ValueError, UnicodeError, TypeError):
            continue
    return None


def lookup_title(code: str, cache_path: Path, *, force_refresh: bool = False,
                 fetcher=_fetch_official) -> tuple[str, str]:
    """Returns a verified title and source; raises LookupError if unavailable.

    Existing local cache works offline; no OpenAI/Steam keys needed.
    """
    if not PRODUCT_CODE.fullmatch(code):
        raise ValueError("올바른 RJ/VJ/BJ/EJ 작품 코드가 아닙니다.")
    code = code.upper()
    cache = load_json(cache_path)
    cached = cache.get(code)
    if not force_refresh and isinstance(cached, dict):
        try:
            timestamp = datetime.fromisoformat(cached.get("checked_at", ""))
            fresh = datetime.now(timezone.utc) - timestamp.astimezone(timezone.utc) < timedelta(days=CACHE_DAYS)
        except (ValueError, TypeError):
            fresh = False
        if fresh and clean_title(cached.get("title")):
            return cached["title"], cached.get("source", "로컬 캐시")

    if code in CROSSCHECKED_OFFLINE_TITLES and not force_refresh:
        title = CROSSCHECKED_OFFLINE_TITLES[code]
        source = '공개 작품 코드 대조 (오프라인 참고자료, 공식 페이지 직접 확인 권장)'
        cache[code] = {'title': title, 'source': source,
                       'checked_at': datetime.now(timezone.utc).isoformat()}
        save_json(cache_path, cache)
        return title, source

    if code in VERIFIED_KOREAN_ALIASES and not force_refresh:
        title = VERIFIED_KOREAN_ALIASES[code]
        source = "검증된 한국어 표기 (로컬 데이터)"
        cache[code] = {"title": title, "source": source,
                       "checked_at": datetime.now(timezone.utc).isoformat()}
        save_json(cache_path, cache)
        return title, source

    result = fetcher(code)
    # Korean labels are optional local aliases; original publisher metadata
    # is still fetched/checked and names are only applied with confirmation.
    if result:
        name, source = result
        title = VERIFIED_KOREAN_ALIASES.get(code, name)
        cache[code] = {
            "title": title,
            "source": source + (" (확인된 한국어 표기)" if code in VERIFIED_KOREAN_ALIASES else ""),
            "checked_at": datetime.now(timezone.utc).isoformat(),
        }
        save_json(cache_path, cache)
        return cache[code]["title"], cache[code]["source"]

    if code in VERIFIED_KOREAN_ALIASES:
        return VERIFIED_KOREAN_ALIASES[code], "검증된 한국어 표기 (오프라인)"
    if isinstance(cached, dict) and clean_title(cached.get("title")):
        return cached["title"], cached.get("source", "로컬 캐시")
    raise LookupError("이 작품 코드의 공개 제목을 확인하지 못했습니다. 기존 이름을 유지합니다.")
