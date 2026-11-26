"""Standalone title editor for PlayDock.

Only changes per-game *display titles* in the existing metadata cache.
Archives, installed directories, executable choices and collections are untouched.
"""
from __future__ import annotations

from time import sleep
from pathlib import Path
import sqlite3

from database.work_repository import WorkDatabase

from PySide6.QtCore import QThread, Signal

from product_titles import display_title, lookup_title
from artwork import ai_game_title, get_secret
from ai_providers import PROVIDERS
from services.localized_titles import lookup_localized_title, language_is_plausible
from title_translation import translate_work_title
from korean_title_search import find_korean_titles


def _db_title(code: str, language: str, cache_path: Path, *, store: str = 'dlsite'):
    """DB-first localized title with HONEST fallback language.

    A Japanese title is never reported as Korean if no official Korean
    translation exists. No external requests for a verified DB cache hit.
    """
    path = Path(cache_path).parent / "playdock.db"
    if not path.is_file():
        return None
    try:
        db = WorkDatabase(path.parent)
        record = db.get_official_work(store, code)
    except (OSError, ValueError, RuntimeError):
        return None
    return _title_from_record(record, language, store=store)


def _title_from_record(record, language, *, store):
    if not record:
        return None
    titles = record.get("titles") or {}
    if not isinstance(titles, dict):
        titles = {}
    for actual in dict.fromkeys((language, "ja", "en", "ko")):
        title = titles.get(actual)
        if isinstance(title, str) and language_is_plausible(title, actual):
            return title, "PlayDock 공식 작품 DB · " + actual, actual
    # The base title has no explicit locale. Retain the existing store default
    # only when the script is compatible; never relabel a conflicting variant.
    actual = "en" if store == "steam" else "ja"
    title = record.get("title")
    if isinstance(title, str) and language_is_plausible(title, actual):
        return title, "PlayDock 공식 작품 DB · 기본 작품명", actual
    return None


class TitleWorker(QThread):
    found = Signal(str, str, str, str)  # game ID, suggestion, source, code
    localized_found = Signal(str, str, str, str, str)  # ID, title, source, code, language
    korean_web_found = Signal(str, object)  # ID, unsaved public-page suggestions
    failed = Signal(str, str)

    def __init__(self, game_id: str, original_title: str, code: str | None,
                 cache_path: Path, mode: str, provider: str = 'openai', model: str = '', language: str = 'ko'):
        super().__init__()
        self.game_id = game_id
        self.original_title = original_title
        self.code = code
        self.cache_path = cache_path
        self.mode = mode
        self.provider = provider
        self.language = language
        self.model = model or PROVIDERS[provider]['text_model']

    def run(self):
        try:
            if self.mode == 'rj':
                if not self.code:
                    raise ValueError('RJ/VJ/BJ/EJ 작품 코드가 없습니다.')
                cached = _db_title(self.code, "ja", self.cache_path)
                if cached:
                    official, source, _language = cached
                else:
                    official, source = lookup_title(self.code, self.cache_path)
                suggested = display_title(official, self.original_title, self.code)
                self.found.emit(self.game_id, suggested, source, self.code)
            elif self.mode == 'localized':
                if not self.code:
                    raise ValueError('품번이 없는 게임은 직접 제목을 입력해 주세요.')
                cached = _db_title(self.code, self.language, self.cache_path)
                if cached:
                    title, source, actual = cached
                    self.localized_found.emit(self.game_id, title, source,
                                              self.code, actual)
                else:
                    result = lookup_localized_title(self.code, self.language, self.cache_path)
                    self.localized_found.emit(self.game_id, result.title, result.source,
                                              self.code, result.language)
            elif self.mode == 'korean_web':
                suggestions = find_korean_titles(self.code, self.original_title)
                self.korean_web_found.emit(self.game_id, suggestions)
            elif self.mode == 'translate':
                key = get_secret(self.provider) if self.provider != 'ollama' else ''
                if self.provider != 'ollama' and not key:
                    raise ValueError('선택한 AI 서비스 키가 없습니다.')
                translated = translate_work_title(self.original_title, self.language,
                                                  self.provider, self.model, key)
                self.localized_found.emit(self.game_id, translated,
                    f'{PROVIDERS[self.provider]["name"]} 텍스트 AI 번역 후보 · 미검증',
                    self.code or '', self.language)
            elif self.mode == 'gpt':
                key = get_secret(self.provider) if self.provider != 'ollama' else ''
                if self.provider != 'ollama' and not key:
                    raise ValueError(f"{PROVIDERS[self.provider]['name']} 키가 없습니다. 환경 변수 또는 기존 Windows 자격 증명 저장소에서 확인해 주세요.")
                candidate = ai_game_title(self.original_title, key, provider=self.provider, model=self.model)
                if not candidate:
                    raise ValueError('AI가 제목을 확인하지 못했습니다.')
                self.found.emit(self.game_id, candidate, f"{PROVIDERS[self.provider]['name']} API 추천", self.code or '')
            else:
                raise ValueError('지원하지 않는 작업입니다.')
        except Exception as exc:
            self.failed.emit(self.game_id, str(exc))


class BulkTitleWorker(QThread):
    """Fetch public work names without ever changing library metadata."""
    progress = Signal(int, int, str)
    complete = Signal(object)

    def __init__(self, entries, language: str, cache_path: Path, *, db_only=False,
                 verified_records=None):
        super().__init__()
        self.entries = list(entries)  # game_id, original_title, code, store
        self.language = language
        self.cache_path = cache_path
        self.db_only = bool(db_only)
        self.verified_records = verified_records
        self.cancelled = False

    def stop(self):
        self.cancelled = True

    def run(self):
        results = []
        total = len(self.entries)
        records = self.verified_records
        if self.db_only and records is None and not self.cancelled:
            records = {}
            path = Path(self.cache_path).parent / "playdock.db"
            if path.is_file():
                try:
                    db = WorkDatabase(path.parent)
                    records = db.get_official_works(
                        (entry[3] if len(entry) > 3 else "dlsite", entry[2])
                        for entry in self.entries)
                except (OSError, ValueError, RuntimeError, sqlite3.Error):
                    # Keep the existing per-entry missing-DB error behavior.
                    records = {}
        for index, entry in enumerate(self.entries, 1):
            if self.cancelled:
                break
            game_id, original, code = entry[:3]
            store = entry[3] if len(entry) > 3 else "dlsite"
            from_db = False
            try:
                if self.db_only:
                    key = WorkDatabase._official_key(store, code)
                    record = (records or {}).get(key)
                    cached = _title_from_record(record, self.language, store=store)
                    if record and not cached:
                        raise LookupError("DB 제목의 언어를 확인할 수 없습니다. 제목을 직접 확인해 주세요.")
                else:
                    cached = _db_title(code, self.language, self.cache_path, store=store)
                if cached:
                    found_title, source, actual = cached
                    from_db = True
                elif self.db_only or store == "steam":
                    raise LookupError("해당 작품의 공식정보가 DB에 없습니다. 먼저 게임 정보 수집을 실행해 주세요.")
                else:
                    result = lookup_localized_title(code, self.language, self.cache_path)
                    found_title, source, actual = result.title, result.source, result.language
                results.append({'game_id': game_id, 'original': original,
                                'code': code, 'store': store, 'title': found_title,
                                'source': source, 'language': actual})
            except (ValueError, LookupError, OSError) as exc:
                results.append({'game_id': game_id, 'original': original,
                                'code': code, 'store': store, 'error': str(exc)})
            self.progress.emit(index, total, code)
            if index < total and not self.cancelled and not from_db:
                sleep(0.35)
        self.complete.emit(results)

