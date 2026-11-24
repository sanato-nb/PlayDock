"""Standalone title editor for PlayDock.

Only changes per-game *display titles* in the existing metadata cache.
Archives, installed directories, executable choices and collections are untouched.
"""
from __future__ import annotations

from time import sleep
from pathlib import Path

from PySide6.QtCore import QThread, Signal

from product_titles import display_title, lookup_title
from artwork import ai_game_title, get_secret
from ai_providers import PROVIDERS
from localized_titles import lookup_localized_title
from title_translation import translate_work_title
from korean_title_search import find_korean_titles


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
                official, source = lookup_title(self.code, self.cache_path)
                suggested = display_title(official, self.original_title, self.code)
                self.found.emit(self.game_id, suggested, source, self.code)
            elif self.mode == 'localized':
                if not self.code:
                    raise ValueError('품번이 없는 게임은 직접 제목을 입력해 주세요.')
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
                    raise ValueError(f"{PROVIDERS[self.provider]['name']} 키가 없습니다. PlayDock의 AI 설정에서 등록해 주세요.")
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

    def __init__(self, entries, language: str, cache_path: Path):
        super().__init__()
        self.entries = list(entries)  # game_id, original_title, work_code
        self.language = language
        self.cache_path = cache_path
        self.cancelled = False

    def stop(self):
        self.cancelled = True

    def run(self):
        results = []
        total = len(self.entries)
        for index, (game_id, original, code) in enumerate(self.entries, 1):
            if self.cancelled:
                break
            try:
                result = lookup_localized_title(code, self.language, self.cache_path)
                results.append({'game_id': game_id, 'original': original,
                                'code': code, 'title': result.title,
                                'source': result.source, 'language': result.language})
            except (ValueError, LookupError, OSError) as exc:
                results.append({'game_id': game_id, 'original': original,
                                'code': code, 'error': str(exc)})
            self.progress.emit(index, total, code)
            if index < total and not self.cancelled:
                sleep(0.35)
        self.complete.emit(results)

