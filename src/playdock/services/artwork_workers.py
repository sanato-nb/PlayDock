"""인터넷 작품 이미지 검색·다운로드·식별 작업을 UI 스레드 밖에서 처리한다.

QThread 신호 형식과 오류 전달 방식은 v0.8.4와 호환된다.
"""
from __future__ import annotations

from io import BytesIO

from PySide6.QtCore import QThread, Signal

from online_artwork import Candidate, search_images, download_image, _get, read_image
from game_identity import lookup_code_identity, discover_public_identity, suggest_ai_identity
from ai_providers import require_access


class SearchJob(QThread):
    ready = Signal(object, object)
    failed = Signal(str)

    def __init__(self, query: str, kind: str, product_code: str | None = None):
        super().__init__()
        self.query = query
        self.kind = kind
        self.product_code = product_code

    def run(self):
        try:
            results = search_images(self.query, self.kind, limit=8, product_code=self.product_code)
            thumbs = []
            for result in results:
                try:
                    thumb = read_image(_get(result.thumbnail_url, 2 * 1024 * 1024))
                    thumb.thumbnail((420, 270))
                    stream = BytesIO()
                    thumb.convert('RGB').save(stream, format='JPEG', quality=80)
                    thumbs.append(stream.getvalue())
                except Exception:
                    thumbs.append(None)
            self.ready.emit(results, thumbs)
        except Exception as exc:
            self.failed.emit(str(exc))


class DownloadJob(QThread):
    ready = Signal(bytes)
    failed = Signal(str)

    def __init__(self, candidate: Candidate):
        super().__init__()
        self.candidate = candidate

    def run(self):
        try:
            self.ready.emit(download_image(self.candidate.image_url))
        except Exception as exc:
            self.failed.emit(str(exc))


class IdentityJob(QThread):
    ready = Signal(object)
    failed = Signal(str)

    def __init__(self, mode, library, game, code, filename, provider='', model=''):
        super().__init__()
        self.mode, self.library, self.game = mode, library, game
        self.code, self.filename = code, filename
        self.provider, self.model = provider, model

    def run(self):
        try:
            if self.mode == 'code':
                if not self.code:
                    raise ValueError('조회할 작품 코드가 없습니다.')
                result = lookup_code_identity(self.code, self.library.store / 'product_titles.json')
            elif self.mode == 'discover':
                result = discover_public_identity(self.filename, self.library.store / 'product_titles.json')
            elif self.mode == 'ai':
                key = require_access(self.provider)
                result = suggest_ai_identity(self.filename, self.code,
                                             self.provider, self.model, key)
            else:
                raise ValueError('지원하지 않는 확인 방법입니다.')
            self.ready.emit(result)
        except Exception as exc:
            self.failed.emit(str(exc))


