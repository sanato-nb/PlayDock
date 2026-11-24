"""Qt image-search chooser and interactive, non-generative crop editor."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from urllib.parse import quote_plus
from io import BytesIO
from pathlib import Path
import shutil

from PySide6.QtCore import Qt, Signal, QThread, QTimer, QUrl
from PySide6.QtGui import QPixmap, QDesktopServices
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QGridLayout, QScrollArea, QWidget,
    QLabel, QLineEdit, QPushButton, QComboBox, QSlider, QFrame, QMessageBox,
)
from ui.selectors import DarkMenuSelect

from online_artwork import Candidate, search_images, download_image, _get, read_image, crop_png, save_selected_art, crop_pan_center
from game_identity import initial_identity, lookup_code_identity, suggest_ai_identity, discover_public_identity, GameIdentity
from ai_providers import current_provider, current_models, require_access, provider_details
from product_titles import extract_code
from game_codes import normalize_code


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


class DragCropPreview(QLabel):
    """Fixed-size image viewport; drag signals are relative image movement."""
    dragged = Signal(float, float)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._last = None
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setCursor(Qt.CursorShape.OpenHandCursor)
        self.setStyleSheet('background:#101923; border:1px solid #344b60; border-radius:5px; padding:0;')

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and self.pixmap() is not None:
            self._last = event.position()
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._last is not None and event.buttons() & Qt.MouseButton.LeftButton:
            pos = event.position()
            delta = pos - self._last
            self._last = pos
            self.dragged.emit(delta.x(), delta.y())
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if self._last is not None:
            self._last = None
            self.setCursor(Qt.CursorShape.OpenHandCursor)
            event.accept()
            return
        super().mouseReleaseEvent(event)


class CropEditor(QDialog):
    """Mouse-draggable crop editor with linked pan and zoom sliders."""

    def __init__(self, image_data: bytes, kind: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle('이미지 자르기 · 편집')
        self.kind = kind
        self.image_data = image_data
        self.source_size = read_image(image_data).size
        self.setMinimumWidth(710 if kind == 'hero' else 470)
        self.setModal(True)
        body = QVBoxLayout(self)
        body.setContentsMargins(18, 16, 18, 16)
        body.setSpacing(12)
        note = QLabel('이미지를 마우스로 잡아 이동하거나 슬라이더로 위치를 바꿔 봐. 확대 후에도 이동할 수 있어.')
        note.setWordWrap(True)
        body.addWidget(note)
        self.preview = DragCropPreview()
        self.preview_size = (640, 208) if kind == 'hero' else (256, 256)
        self.preview.setFixedSize(*self.preview_size)
        preview_row = QHBoxLayout()
        preview_row.addStretch()
        preview_row.addWidget(self.preview)
        preview_row.addStretch()
        body.addLayout(preview_row)
        self.x = self._add_slider(body, '좌우 중심', 0, 100, 50)
        self.y = self._add_slider(body, '상하 중심', 0, 100, 50)
        self.zoom = self._add_slider(body, '확대', 100, 180, 100)
        self.timer = QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.timeout.connect(self.render_preview)
        for control in (self.x, self.y, self.zoom):
            control.valueChanged.connect(lambda _value: self.timer.start(50))
        self._pan_x, self._pan_y = 50.0, 50.0
        self._drag_updating = False
        self.x.valueChanged.connect(lambda value: self._sync_pan_axis('x', value))
        self.y.valueChanged.connect(lambda value: self._sync_pan_axis('y', value))
        self.preview.dragged.connect(self.drag_image)
        row = QHBoxLayout()
        row.addStretch()
        cancel = QPushButton('취소')
        cancel.clicked.connect(self.reject)
        apply = QPushButton('이미지 적용')
        apply.setObjectName('Blue')
        apply.clicked.connect(self.accept)
        row.addWidget(cancel)
        row.addWidget(apply)
        body.addLayout(row)
        self.render_preview()

    @staticmethod
    def _add_slider(layout, label, low, high, start):
        line = QHBoxLayout()
        name = QLabel(label)
        name.setFixedWidth(65)
        slider = QSlider(Qt.Orientation.Horizontal)
        slider.setRange(low, high)
        slider.setValue(start)
        line.addWidget(name)
        line.addWidget(slider, 1)
        layout.addLayout(line)
        return slider

    def _sync_pan_axis(self, axis: str, value: int):
        if not self._drag_updating:
            if axis == 'x':
                self._pan_x = float(value)
            else:
                self._pan_y = float(value)

    def drag_image(self, dx: float, dy: float):
        # Keep sub-slider precision while dragging; repeated 1px moves should
        # accumulate rather than being rounded down to zero every event.
        self._pan_x, self._pan_y = crop_pan_center(
            self.source_size, self.kind, self._pan_x, self._pan_y,
            self.zoom.value(), dx, dy, self.preview_size)
        self._drag_updating = True
        try:
            self.x.setValue(round(self._pan_x))
            self.y.setValue(round(self._pan_y))
        finally:
            self._drag_updating = False
        self.render_preview()

    def render_preview(self):
        try:
            raw = crop_png(self.image_data, self.kind, self.x.value(),
                           self.y.value(), self.zoom.value(), preview=True)
            pixmap = QPixmap()
            if pixmap.loadFromData(raw, 'PNG'):
                self.preview.setPixmap(pixmap)
        except Exception as exc:
            self.preview.setText(f'미리보기를 표시할 수 없습니다: {exc}')


class OnlineArtworkDialog(QDialog):
    """Opt-in selection only: download candidate -> crop -> confirm -> save."""
    applied = Signal(str)

    def __init__(self, library, game, parent=None, initial_kind='hero', confirm_replace=None):
        super().__init__(parent)
        self.library = library
        self.game = game
        self.confirm_replace = confirm_replace
        self.setWindowTitle(f'인터넷 이미지 검색 및 편집 · {library.title(game)}')
        self.setMinimumSize(810, 690)
        self._search_job = None
        self._download_job = None
        self._candidate = None
        self._preview_rows = []
        self._identity_job = None
        self._identity_search_pending = False
        self._automatic_code_lookup = False
        self.identity = initial_identity(self.library.base_title(game), game.name,
                                         game.archive.name if game.archive else '')
        meta = self.library.meta(game)
        registered_code = self.library.product_code(game)
        if 'product_code' in meta and not registered_code:
            # User explicitly designated this as a game without a work code.
            self.identity = GameIdentity(self.identity.title, '작품 코드 없음 · 게임명으로 검색',
                                         None, self.identity.confidence, False)
        elif registered_code:
            self.identity = GameIdentity(self.identity.title, self.identity.source,
                                         registered_code, self.identity.confidence, False)
        saved_code = meta.get('artwork_identity_code', '')
        saved_title = meta.get('artwork_identity_title', '')
        if registered_code and extract_code(saved_code) == registered_code and isinstance(saved_title, str) and saved_title.strip():
            self.identity = GameIdentity(saved_title, '이전에 확인한 작품 정보 (게임 캐시)',
                                         registered_code, 1.0, True)
        self._setup_ui(initial_kind)
        # The caller explicitly asked to search for existing game artwork.
        # Start in the next GUI event cycle so results appear without a second menu click.
        QTimer.singleShot(0, self._initial_search)

    def _setup_ui(self, initial_kind):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(15, 13, 15, 13)
        layout.setSpacing(10)
        title = QLabel('게임 정체 확인 · 이미지 검색 · 후보 편집')
        title.setStyleSheet('font-size:19px; font-weight:700; background:transparent;')
        layout.addWidget(title)
        intro = QLabel('① 작품 이름 확인  →  ② 같은 게임의 실제 이미지 후보 검색  →  ③ 선택·자르기 후 캐시 저장\n이미지 생성 API는 사용하지 않습니다. AI를 통한 이름 추천은 선택 기능입니다.')
        intro.setWordWrap(True)
        layout.addWidget(intro)
        self.identity_note = QLabel(self.identity.source)
        self.identity_note.setWordWrap(True)
        self.identity_note.setStyleSheet('color:#a7d4f1; background:transparent;')
        layout.addWidget(self.identity_note)
        code_row = QHBoxLayout()
        code_label = QLabel('작품 코드')
        code_label.setMinimumWidth(62)
        code_row.addWidget(code_label)
        self.code_input = QLineEdit(self.identity.code or '')
        self.code_input.setPlaceholderText('RJ / VJ / BJ / EJ 번호 (예: RJ01081508)')
        self.code_input.setMaximumWidth(280)
        self.code_input.returnPressed.connect(self.save_code)
        code_row.addWidget(self.code_input)
        self.code_save_button = QPushButton('품번 저장')
        self.code_save_button.clicked.connect(self.save_code)
        code_row.addWidget(self.code_save_button)
        self.code_clear_button = QPushButton('품번 없음')
        self.code_clear_button.clicked.connect(self.clear_code)
        code_row.addWidget(self.code_clear_button)
        self.code_button = QPushButton('RJ 품번으로 작품명 확인')
        self.code_button.clicked.connect(lambda: self.resolve_identity('code'))
        code_row.addStretch(1)
        layout.addLayout(code_row)
        hint = QLabel('품번은 선택 사항이야. 코드가 없다면 빈칸으로 저장하고, 게임 이름만 검색하면 돼.')
        hint.setStyleSheet('color:#9bb0c2; background:transparent;')
        layout.addWidget(hint)
        confirm_row = QHBoxLayout()
        confirm_row.addWidget(self.code_button)
        self.discover_button = QPushButton('웹에서 작품 코드 찾기 (무료)')
        self.discover_button.clicked.connect(lambda: self.resolve_identity('discover'))
        confirm_row.addWidget(self.discover_button)
        self.ai_button = QPushButton('AI로 게임명 추천 (선택)')
        self.ai_button.clicked.connect(lambda: self.resolve_identity('ai'))
        confirm_row.addWidget(self.ai_button)
        self.browser_button = QPushButton('웹 이미지 검색 열기')
        self.browser_button.clicked.connect(self.open_web_search)
        confirm_row.addWidget(self.browser_button)
        confirm_row.addStretch(1)
        layout.addLayout(confirm_row)
        search = QHBoxLayout()
        # Keep filename/display identity separate from the web search query.
        # The search input is editable but must never rename a game in storage.
        self.original_title_note = QLabel('라이브러리 제목: ' + self.library.title(self.game))
        self.original_title_note.setWordWrap(True)
        self.original_title_note.setStyleSheet('color:#9bb0c2; background:transparent;')
        layout.addWidget(self.original_title_note)
        self.query = QLineEdit(self.identity.title)
        self.query.setPlaceholderText('확인한 실제 게임 이름 또는 품번을 입력하세요')
        self.query.returnPressed.connect(self.search)
        search.addWidget(self.query, 1)
        self.kind = DarkMenuSelect()
        self.kind.addItem('가로 배너 (1600×520)', 'hero')
        self.kind.addItem('정사각 아이콘 (256×256)', 'icon')
        self.kind.setCurrentIndex(0 if initial_kind == 'hero' else 1)
        self.kind.setMinimumWidth(205)
        search.addWidget(self.kind)
        self.search_btn = QPushButton('이미지 검색')
        self.search_btn.setObjectName('Blue')
        self.search_btn.clicked.connect(self.search)
        search.addWidget(self.search_btn)
        layout.addLayout(search)
        self.status = QLabel('이름이 정확하면 바로 검색할 수 있습니다. 검색 결과는 사용자 확인 전까지 적용되지 않습니다.')
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.items_widget = QWidget()
        self.items_grid = QGridLayout(self.items_widget)
        self.items_grid.setSpacing(13)
        self.items_grid.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.scroll.setWidget(self.items_widget)
        layout.addWidget(self.scroll, 1)
        bottom = QHBoxLayout()
        credit = QLabel('검색 결과의 이미지가 공식 이미지라는 보장은 없어. 저작권·사용 조건은 원본 페이지에서 확인해.')
        credit.setWordWrap(True)
        bottom.addWidget(credit, 1)
        close = QPushButton('닫기')
        close.clicked.connect(self.reject)
        bottom.addWidget(close)
        layout.addLayout(bottom)

    def save_code(self):
        """Store optional product code, never rename ZIPs/folders."""
        try:
            code = normalize_code(self.code_input.text())
            self.library.set_product_code(self.game, code)
            self.code_input.setText(code)
        except ValueError as exc:
            self.status.setText('품번 저장 실패: ' + str(exc))
            return
        if code:
            if self.identity.code != code:
                self.identity = GameIdentity(self.query.text().strip(),
                                             '직접 입력한 작품 코드 · 공식 작품 확인 전',
                                             code, 0.5, False)
            self.status.setText('품번 ' + code + ' 저장 완료. 제목에 없으면 자동 표시돼. 작품 확인은 별도로 할 수 있어.')
        else:
            self.identity = GameIdentity(self.query.text().strip(),
                                         '품번 없는 게임 · 이름으로 검색', None, 0.5, False)
            self.status.setText('품번 없음으로 저장했어. 제목에 품번을 자동으로 붙이지 않아.')
        self.identity_note.setText(self.identity.source)
        self.applied.emit('identity')

    def clear_code(self):
        self.code_input.clear()
        self.save_code()

    def _initial_search(self):
        # Resolve a concrete product code before searching rather than
        # querying a misspelled local translation/patch filename.
        if self.identity.verified and self.identity.title:
            self.search()
        elif self.identity.code:
            self.resolve_identity('code', automatic=True)
        elif self.identity.title:
            # No number is normal for many games. Search by reviewed game name
            # without inventing or forcing a product code.
            self.search()

    def resolve_identity(self, mode, automatic=False):
        if self._busy():
            return
        provider, model = '', ''
        code = extract_code(self.code_input.text().strip())
        if mode == 'code' and (not code or code != self.code_input.text().strip().upper()):
            self.status.setText('RJ/VJ/BJ/EJ로 시작하는 올바른 작품 코드를 입력해 주세요.')
            return
        if mode == 'ai':
            provider = current_provider(self.library)
            model = current_models(self.library, provider)[0]
            # Text-only calls may cost money; never silently consume API quota.
            if QMessageBox.question(self, 'AI 게임명 확인',
                                    f'{provider_details(provider)["name"]}의 {model} 텍스트 모델로 '
                                    '게임명을 추천받을까요?\nAPI 요금 또는 사용량 제한이 적용될 수 있습니다. '
                                    '이미지 생성은 하지 않습니다.') != QMessageBox.StandardButton.Yes:
                return
        self._automatic_code_lookup = bool(automatic and mode == 'code')
        self.code_button.setEnabled(False)
        self.discover_button.setEnabled(False)
        self.ai_button.setEnabled(False)
        self.search_btn.setEnabled(False)
        self.status.setText({'code':'품번으로 작품 정보 확인 중…', 'discover':'공개 검색으로 작품 코드 교차 확인 중…', 'ai':'AI로 게임명 추천받는 중…'}.get(mode, '작품 확인 중…'))
        self._identity_job = IdentityJob(mode, self.library, self.game,
                                         code or self.identity.code, self.query.text().strip(),
                                         provider, model)
        self._identity_job.ready.connect(self.identity_ready)
        self._identity_job.failed.connect(self.identity_failed)
        self._identity_job.finished.connect(self.identity_finished)
        self._identity_job.start()

    def identity_ready(self, identity):
        self.identity = identity
        self.code_input.setText(identity.code or '')
        self.query.setText(identity.title)
        if identity.verified and identity.code:
            # Keep verified identity across runs; do not rename actual game files.
            try:
                self.library.update_meta(self.game, artwork_identity_code=identity.code,
                                         artwork_identity_title=identity.title)
                self.library.set_product_code(self.game, identity.code)
                self.applied.emit('identity')
            except (OSError, ValueError):
                pass
        self.identity_note.setText('검색 작품명: ' + identity.title + ' · ' + identity.source)
        self.status.setText('검증된 작품 정보로 이미지를 찾습니다.' if identity.verified else
                            'AI 추천은 미검증입니다. 제목을 확인한 뒤 이미지 검색을 눌러 주세요.')
        # Only verified public metadata can start candidate search automatically.
        self._identity_search_pending = bool(identity.verified)

    def identity_failed(self, reason):
        self.identity_note.setText('정확한 작품 코드가 확인되지 않았습니다. 작품 코드나 원제를 입력할 수 있어요.')
        self.status.setText('게임 정체 확인 실패: ' + str(reason)[:350])
        # Never downgrade failed code verification into a blind image search.
        # The user can change the title or explicitly click Image Search.

    def identity_finished(self):
        self.code_button.setEnabled(True)
        self.discover_button.setEnabled(True)
        self.ai_button.setEnabled(True)
        self.search_btn.setEnabled(True)
        job, self._identity_job = self._identity_job, None
        if job is not None:
            job.deleteLater()
        if self._identity_search_pending:
            self._identity_search_pending = False
            QTimer.singleShot(0, self.search)

    def open_web_search(self):
        query = self.query.text().strip()
        if not query:
            return
        code = self.identity.code if self.identity.verified and self.identity.title == query else ''
        QDesktopServices.openUrl(QUrl('https://www.google.com/search?tbm=isch&q='
                                      + quote_plus((code + ' ' + query).strip() + ' cover artwork')))

    def _busy(self):
        return ((self._search_job is not None and self._search_job.isRunning())
                or (self._download_job is not None and self._download_job.isRunning())
                or (self._identity_job is not None and self._identity_job.isRunning()))

    def reject(self):
        if self._busy():
            self.status.setText('검색/다운로드 중에는 창을 닫을 수 없습니다. 작업이 끝난 뒤 닫아 주세요.')
            return
        super().reject()

    def closeEvent(self, event):
        if self._busy():
            event.ignore()
            self.status.setText('검색/다운로드가 끝난 후 창을 닫을 수 있습니다.')
            return
        super().closeEvent(event)

    def _clear(self):
        while self.items_grid.count():
            item = self.items_grid.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self._preview_rows.clear()

    def search(self):
        if self._busy():
            return
        self._clear()
        self.search_btn.setEnabled(False)
        confirmed_code = (self.identity.code if self.identity.verified and
                          self.query.text().strip() == self.identity.title and
                          self.code_input.text().strip().upper() == self.identity.code else None)
        self.identity_note.setText('검색 기준: ' + self.query.text().strip()
                                   + (' · ' + confirmed_code if confirmed_code else ' · 작품 코드 미확인')
                                   + ' · 사용자 검토 필요')
        self.status.setText('확인된 작품 코드와 정확한 제목을 우선 검색 중… 무관한 이미지는 표시하지 않습니다.')
        self._search_job = SearchJob(self.query.text().strip(), self.kind.currentData(), confirmed_code)
        self._search_job.ready.connect(self.show_results)
        self._search_job.failed.connect(self._error)
        self._search_job.finished.connect(self._search_finished)
        self._search_job.start()

    def _search_finished(self):
        self.search_btn.setEnabled(True)
        job, self._search_job = self._search_job, None
        if job:
            job.deleteLater()

    def _error(self, error):
        self.status.setText('이미지 검색 실패: ' + str(error)[:500])

    def show_results(self, candidates, previews):
        self._clear()
        self.status.setText(f'{len(candidates)}개 작품명 일치 후보 · 검색어와의 문자 일치 결과이며 실제 작품 이미지는 직접 확인하세요.')
        for i, (candidate, preview) in enumerate(zip(candidates, previews)):
            card = QFrame()
            card.setObjectName('InfoCard')
            card.setFixedWidth(240)
            card_layout = QVBoxLayout(card)
            card_layout.setContentsMargins(9, 9, 9, 9)
            thumb = QLabel('미리보기 없음')
            thumb.setAlignment(Qt.AlignmentFlag.AlignCenter)
            thumb.setFixedSize(218, 124)
            thumb.setStyleSheet('background:#101923; color:#94a8b8; border-radius:4px;')
            if preview:
                pix = QPixmap()
                if pix.loadFromData(preview):
                    thumb.setPixmap(pix.scaled(214, 120, Qt.AspectRatioMode.KeepAspectRatio,
                                              Qt.TransformationMode.SmoothTransformation))
            card_layout.addWidget(thumb)
            label = QLabel(candidate.title[:85])
            label.setWordWrap(True)
            label.setFixedHeight(47)
            card_layout.addWidget(label)
            source = QLabel(candidate.provider + ((' · ' + candidate.license_label) if candidate.license_label else ''))
            source.setStyleSheet('color:#97bacf; font-size:11px; background:transparent;')
            source.setWordWrap(True)
            card_layout.addWidget(source)
            buttons = QHBoxLayout()
            choose = QPushButton('선택 · 편집')
            choose.clicked.connect(lambda _checked=False, c=candidate: self.choose(c))
            buttons.addWidget(choose)
            if candidate.source_url.startswith('https://'):
                link = QPushButton('출처')
                link.clicked.connect(lambda _checked=False, url=candidate.source_url: QDesktopServices.openUrl(QUrl(url)))
                buttons.addWidget(link)
            card_layout.addLayout(buttons)
            self.items_grid.addWidget(card, i // 3, i % 3)
            self._preview_rows.append(card)

    def choose(self, candidate: Candidate):
        if self._busy():
            return
        self._candidate = candidate
        self._download_job = DownloadJob(candidate)
        self._download_job.ready.connect(self.edit_and_apply)
        self._download_job.failed.connect(lambda err: self.status.setText('원본 이미지 다운로드 실패: ' + err[:450]))
        self._download_job.finished.connect(self._download_finished)
        self.status.setText('원본 이미지 다운로드 중…')
        self._download_job.start()

    def _download_finished(self):
        job, self._download_job = self._download_job, None
        if job:
            job.deleteLater()

    def edit_and_apply(self, image_data: bytes):
        candidate = self._candidate
        if candidate is None:
            return
        kind = self.kind.currentData()
        editor = CropEditor(image_data, kind, self)
        if editor.exec() != QDialog.DialogCode.Accepted:
            self.status.setText('편집 취소 · 기존 이미지 유지')
            return
        target = self.library.art_dir(self.game) / f'{kind}.png'
        if target.exists():
            if self.confirm_replace is None or not self.confirm_replace(kind):
                self.status.setText('기존 이미지가 있어 변경하지 않았어.')
                return
        try:
            if target.exists():
                backup = self.library.store / 'backups' / 'artwork' / self.game.id
                backup.mkdir(parents=True, exist_ok=True)
                saved = backup / f'{kind}_{datetime.now().strftime("%Y%m%d_%H%M%S_%f")}.png'
                shutil.copy2(target, saved)
            save_selected_art(image_data, target, kind, editor.x.value(), editor.y.value(), editor.zoom.value())
            metadata = self.library.meta(self.game)
            sources = metadata.get('artwork_sources')
            sources = dict(sources) if isinstance(sources, dict) else {}
            sources[kind] = {'url': candidate.image_url, 'page': candidate.source_url,
                             'source': candidate.provider, 'license': candidate.license_label}
            self.library.update_meta(self.game, artwork_source='인터넷 검색 · 사용자가 선택함', artwork_sources=sources)
            self.status.setText('저장 완료! ' + ('배너' if kind == 'hero' else '아이콘') + '이(가) 게임 캐시에 저장됐어.')
            self.applied.emit(kind)
        except Exception as exc:
            self.status.setText('이미지 저장 실패: ' + str(exc)[:400])
