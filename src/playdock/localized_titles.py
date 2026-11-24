"""Multi-language *display* titles from an exact public work code.

Never invent a translation, rename an archive, or replace the user's manual title.
Prefer source-language results to a purported translation when locale metadata
still returns the original Japanese text. All web results require user approval.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
import re

from core import load_json, save_json
from product_titles import (
    PRODUCT_CODE, clean_title, _fetch_official,
    VERIFIED_KOREAN_ALIASES, CROSSCHECKED_OFFLINE_TITLES,
)

LANGUAGES = {"ko": ("한국어", "ko_KR"), "en": ("English", "en_US"), "ja": ("日本語", "ja_JP")}
CODE_ONLY = re.compile(r"^(?:RJ|VJ|BJ|EJ)\d{6,8}$", re.I)
JAPANESE_KANA = re.compile(r"[\u3040-\u30ff]")
EAST_ASIAN_SCRIPT = re.compile(r"[\u3040-\u30ff\u3400-\u9fff\uac00-\ud7a3]")
KOREAN_HANGUL = re.compile(r"[\uac00-\ud7a3]")


@dataclass(frozen=True)
class LocalizedTitle:
    code: str
    title: str
    language: str  # Actual language, not the requested language
    source: str
    is_fallback: bool = False


def is_code_only_title(raw: str) -> bool:
    """A code alone with optional release, translation or version tags."""
    no_tags = re.sub(r"\[[^\[\]]*\]", " ", raw or "")
    return bool(CODE_ONLY.fullmatch(no_tags.strip()))


def language_is_plausible(title: str, language: str) -> bool:
    if not clean_title(title):
        return False
    if language == "ko":
        # A Latin proper name is not necessarily untranslated; Japanese kana is.
        return not JAPANESE_KANA.search(title)
    if language == "en":
        return not EAST_ASIAN_SCRIPT.search(title)
    if language == "ja":
        return not KOREAN_HANGUL.search(title)
    return False


def _fresh(entry: dict, *, days: int = 30) -> bool:
    try:
        stamp = datetime.fromisoformat(str(entry.get("checked_at", "")))
        return datetime.now(timezone.utc) - stamp.astimezone(timezone.utc) < timedelta(days=days)
    except (ValueError, TypeError, OverflowError):
        return False


def _save(cache: dict, path: Path, result: LocalizedTitle) -> LocalizedTitle:
    code_cache = cache.setdefault(result.code, {})
    if not isinstance(code_cache, dict):
        cache[result.code] = code_cache = {}
    code_cache[result.language] = {
        "title": result.title,
        "source": result.source,
        "checked_at": datetime.now(timezone.utc).isoformat(),
    }
    save_json(path, cache)
    return result


def lookup_localized_title(code: str, preferred: str, cache_path: Path, *,
                           fetcher=None, force_refresh: bool = False) -> LocalizedTitle:
    """Look up an exact code and prefer a real title for the requested language.

    fetcher is (code, locale) -> (title, source URL) | None, for offline tests.
    If a translation cannot be verified, return a clearly labeled original-
    language fallback instead of silently claiming to have translated it.
    """
    code = (code or "").strip().upper()
    if not PRODUCT_CODE.fullmatch(code):
        raise ValueError("정확한 RJ/VJ/BJ/EJ 작품 코드를 입력하세요.")
    if preferred not in LANGUAGES:
        raise ValueError("한국어·영어·일본어 중 하나를 선택하세요.")
    if fetcher is None:
        fetcher = lambda c, loc: _fetch_official(c, locale=loc)
    cache = load_json(cache_path)
    code_cache = cache.get(code, {})
    if not isinstance(code_cache, dict):
        code_cache = {}

    languages = [preferred] + (["ja"] if preferred != "ja" else [])
    fallback: LocalizedTitle | None = None
    for language in languages:
        if language == "ko" and code in VERIFIED_KOREAN_ALIASES and not force_refresh:
            return _save(cache, cache_path, LocalizedTitle(code, VERIFIED_KOREAN_ALIASES[code],
                "ko", "검증된 한국어 표기 · 로컬 참고자료"))
        if language == "ja" and code in CROSSCHECKED_OFFLINE_TITLES and not force_refresh:
            result = LocalizedTitle(code, CROSSCHECKED_OFFLINE_TITLES[code], "ja",
                "공개 자료 대조 · 일본어 원제 (원문 직접 확인 권장)", preferred != "ja")
            if language == preferred:
                return _save(cache, cache_path, result)
            fallback = result
            break
        entry = code_cache.get(language)
        if not force_refresh and isinstance(entry, dict) and _fresh(entry):
            title = clean_title(entry.get("title"))
            if title and language_is_plausible(title, language):
                result = LocalizedTitle(code, title, language, str(entry.get("source") or "저장된 조회 결과"),
                                        language != preferred)
                if language == preferred:
                    return result
                fallback = result
                break
        try:
            raw = fetcher(code, LANGUAGES[language][1])
        except (OSError, TimeoutError, ConnectionError, ValueError, TypeError):
            raw = None
        if raw:
            title, source = raw
            title = clean_title(title)
            if title and language_is_plausible(title, language):
                result = LocalizedTitle(code, title, language, str(source), language != preferred)
                _save(cache, cache_path, result)
                if language == preferred:
                    return result
                fallback = result
                break
    if fallback:
        return fallback
    raise LookupError("품번과 일치하는 공개 작품명을 확인하지 못했습니다. 원본 이름은 유지합니다.")


def display_language_for(meta: dict, settings: dict) -> str:
    local = meta.get("title_language") or settings.get("title_language") or "ko"
    return local if local in LANGUAGES else "ko"


def localized_title_for(meta: dict, settings: dict, *, original_name: str,
                        product_code: str) -> str | None:
    """Prefer chosen locale; for a code-only name allow Japanese fallback."""
    variants = meta.get("localized_titles") or {}
    if not isinstance(variants, dict):
        return None
    desired = display_language_for(meta, settings)
    translated = clean_title(variants.get(desired))
    if not translated and is_code_only_title(original_name):
        translated = clean_title(variants.get("ja")) or clean_title(variants.get("en"))
    if not translated:
        return None
    # Keep the archive's [v...]/[KR]/[revision] metadata separate from the
    # published name and preserve the exact product code once.
    from product_titles import display_title
    return display_title(translated, original_name, product_code)
