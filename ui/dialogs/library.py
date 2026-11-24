"""PlayDock — Windows-friendly Steam-like launcher for local ZIP/7z/RAR/RAR games."""
from __future__ import annotations

import os
from pathlib import Path
import sys

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QWidget,
    QHBoxLayout,
    QVBoxLayout,
    QFrame,
    QLabel,
    QPushButton,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QFileDialog,
    QFormLayout,
    QCheckBox,
    QDialogButtonBox,
    QTabWidget,
)

from core import Game, Library
from game_collections import CollectionStore
from cache_management import image_stats, recycle_images
from data_management import inventory, backup_data, inspect_backup, restore_data
from artwork import get_secret, set_secret
from ui.selectors import DarkMenuSelect
from ai_providers import PROVIDERS, current_provider, current_models, save_provider_settings
from setup_paths import save_folder_settings, proposed_paths


from ui.dialogs.common import ThemedDialog, ask_text, ask_yes_no, show_message
from ui.widgets.launcher import friendly_bytes


class SettingsDialog(ThemedDialog):
    """Provider selector shared with the separate Title Editor via settings.json."""
    def __init__(self, library: Library, parent=None):
        super().__init__("AI 서비스 설정", parent, 520)
        self.library = library
        layout = self.body
        heading = QLabel("AI 서비스 선택")
        heading.setObjectName("Heading")
        layout.addWidget(heading)
        hint = QLabel("이 AI 설정은 별도 게임 이름 관리자의 이름 추천에만 사용됩니다.\n"
                      "인터넷 이미지 검색·후보 선택·자르기는 API 키 없이 무료로 사용할 수 있습니다.\n"
                      "API 키는 Windows 자격 증명 저장소에 저장하며 프로그램 폴더에 저장하지 않습니다.")
        hint.setObjectName("Subtle")
        hint.setWordWrap(True)
        layout.addWidget(hint)
        form = QFormLayout()
        self.provider = DarkMenuSelect()
        for provider_id, record in PROVIDERS.items():
            self.provider.addItem(record["name"], provider_id)
        form.addRow("AI 서비스", self.provider)
        self.text_model = QLineEdit()
        form.addRow("게임 이름 모델", self.text_model)
        self.api_key = QLineEdit()
        self.api_key.setEchoMode(QLineEdit.EchoMode.Password)
        form.addRow("API 키", self.api_key)
        layout.addLayout(form)
        self.delete_key = QCheckBox("선택한 서비스의 저장된 API 키 삭제")
        layout.addWidget(self.delete_key)
        self.help_label = QLabel()
        self.help_label.setObjectName("Subtle")
        self.help_label.setWordWrap(True)
        layout.addWidget(self.help_label)
        note = QLabel("게임 이미지 검색은 생성형 AI 서비스를 호출하지 않습니다.\n"
                      "게임 이름 추천 기능을 쓸 때만 선택한 텍스트 모델의 API 사용료나 요청 제한이 적용될 수 있습니다.")
        note.setObjectName("Subtle")
        note.setWordWrap(True)
        layout.addWidget(note)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QDialogButtonBox.StandardButton.Save).setText("저장")
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText("취소")
        buttons.accepted.connect(self.save)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        provider_id = current_provider(library)
        self.provider.setCurrentIndex(self.provider.findData(provider_id))
        self.provider.currentIndexChanged.connect(self.on_provider_changed)
        self.on_provider_changed()

    def on_provider_changed(self, _index=None):
        provider = self.provider.currentData() or "openai"
        details = PROVIDERS[provider]
        text, _unused_image_model = current_models(self.library, provider)
        self.text_model.setText(text)
        self.api_key.clear()
        self.delete_key.setChecked(False)
        if provider == "ollama":
            self.api_key.setEnabled(False)
            self.delete_key.setEnabled(False)
            self.api_key.setPlaceholderText("필요 없음")
        else:
            self.api_key.setEnabled(True)
            self.delete_key.setEnabled(True)
            self.api_key.setPlaceholderText("등록됨" if get_secret(provider) else "API 키 입력")
        self.help_label.setText(details["hint"])

    def save(self):
        try:
            provider = self.provider.currentData() or "openai"
            # Validate models before modifying saved credentials.
            if not self.text_model.text().strip() or len(self.text_model.text().strip()) > 160:
                raise ValueError("게임 이름 모델을 입력해 주세요.")
            if provider != "ollama":
                if self.delete_key.isChecked():
                    set_secret(provider, "")
                elif self.api_key.text().strip():
                    set_secret(provider, self.api_key.text())
            # Keep the previous image-model field in settings for compatibility;
            # no image-generation action is available in this application.
            saved_image_model = current_models(self.library, provider)[1]
            save_provider_settings(self.library, provider, self.text_model.text(), saved_image_model)
            self.accept()
        except Exception as exc:
            show_message(self, "AI 설정 저장 실패", str(exc))


class FirstRunDialog(ThemedDialog):
    def __init__(self, library: Library, parent=None):
        self.library = library
        super().__init__("PlayDock · 폴더 설정 마법사", parent, 690)
        layout = self.body
        heading = QLabel("게임 라이브러리를 시작하기")
        heading.setObjectName("Heading")
        layout.addWidget(heading)
        msg = QLabel("처음 한 번만 게임 압축파일 보관 위치와 설치 위치를 선택하세요.\n"
                     "기존 게임 파일을 삭제하거나 이동하지 않습니다.")
        msg.setObjectName("Subtle")
        layout.addWidget(msg)
        default_archive, default_game = proposed_paths()
        current_archive = library.archive_root if library.config_path.exists() else default_archive
        current_game = library.root if library.config_path.exists() else default_game
        self.fields = []
        for title, default in (("① ZIP / 7z 압축파일 폴더", current_archive),
                               ("② 설치된 게임 폴더", current_game)):
            label = QLabel(title)
            layout.addWidget(label)
            line = QHBoxLayout()
            entry = QLineEdit(str(default))
            choose = QPushButton("찾아보기...")
            choose.clicked.connect(lambda _checked=False, edit=entry: self.choose_directory(edit))
            line.addWidget(entry, 1)
            line.addWidget(choose)
            layout.addLayout(line)
            self.fields.append(entry)
        info = QLabel("선택한 폴더가 없으면 자동으로 생성합니다. 언제든 상단 '폴더 설정'에서 변경할 수 있어요.")
        info.setWordWrap(True)
        info.setObjectName("Subtle")
        layout.addWidget(info)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("설정 완료")
        buttons.accepted.connect(self.save)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def choose_directory(self, edit: QLineEdit):
        starting = Path(edit.text()).expanduser()
        while not starting.is_dir() and starting != starting.parent:
            starting = starting.parent
        folder = QFileDialog.getExistingDirectory(
            self, "폴더 선택", str(starting),
            options=QFileDialog.Option.DontUseNativeDialog)
        if folder:
            edit.setText(folder)

    def save(self):
        try:
            save_folder_settings(self.fields[0].text(), self.fields[1].text())
            self.accept()
        except Exception as exc:
            show_message(self, "폴더 설정 실패", str(exc))


class GameCollectionsDialog(ThemedDialog):
    """Checkbox-based many-to-many collection organizer for one game."""
    def __init__(self, collections: CollectionStore, game: Game, title: str, parent=None):
        self.collections = collections
        self.game = game
        super().__init__("게임을 모음집에 추가 / 제거", parent, 440)
        layout = self.body
        heading = QLabel(f"{title} · 모음집")
        heading.setObjectName("Heading")
        heading.setWordWrap(True)
        layout.addWidget(heading)
        info = QLabel("여러 모음집에 동시에 추가할 수 있습니다. 게임 파일은 이동하지 않습니다.")
        info.setObjectName("Subtle")
        info.setWordWrap(True)
        layout.addWidget(info)
        self.check_area = QVBoxLayout()
        self.checkboxes: dict[str, QCheckBox] = {}
        layout.addLayout(self.check_area)
        for col in collections.list():
            self.append_choice(col["id"], col["name"], game.id in col["game_ids"])
        if not self.checkboxes:
            hint = QLabel("아직 모음집이 없습니다. 아래 버튼으로 첫 모음집을 만들어 보세요.")
            hint.setObjectName("Subtle")
            self.check_area.addWidget(hint)
        add = QPushButton("＋ 새 모음집 만들기")
        add.clicked.connect(self.new_collection)
        layout.addWidget(add)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QDialogButtonBox.StandardButton.Save).setText("적용")
        buttons.accepted.connect(self.apply_changes)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def append_choice(self, cid: str, name: str, checked: bool):
        checkbox = QCheckBox(name)
        checkbox.setChecked(checked)
        self.checkboxes[cid] = checkbox
        self.check_area.addWidget(checkbox)

    def new_collection(self):
        name, ok = ask_text(self, "모음집 만들기", "모음집 이름:")
        if not ok:
            return
        try:
            cid = self.collections.create(name)
        except ValueError as exc:
            show_message(self, "모음집 생성 실패", str(exc))
            return
        self.append_choice(cid, name.strip(), True)

    def apply_changes(self):
        chosen = {cid for cid, checkbox in self.checkboxes.items() if checkbox.isChecked()}
        try:
            self.collections.set_game_memberships(self.game.id, chosen)
            self.accept()
        except Exception as exc:
            show_message(self, "모음집 저장 실패", str(exc))


class CacheManagerDialog(ThemedDialog):
    """Manage artwork cache only, without deleting game metadata or settings."""

    def __init__(self, library: Library, games: list[Game], parent=None):
        super().__init__("이미지 캐시 관리", parent, 610)
        self.library = library
        self.games = list(games)
        heading = QLabel("이미지 캐시 관리")
        heading.setObjectName("Heading")
        self.body.addWidget(heading)
        note = QLabel(
            "배너 및 게임 아이콘 캐시만 정리합니다.\n"
            "게임 이름, 실행 파일 선택, 모음집, ZIP·7z·RAR 및 설치된 게임은 유지됩니다."
        )
        note.setObjectName("Subtle")
        note.setWordWrap(True)
        self.body.addWidget(note)
        self.summary = QLabel("")
        self.summary.setObjectName("DialogHeading")
        self.body.addWidget(self.summary)
        label = QLabel("게임별 이미지 캐시")
        self.body.addWidget(label)
        self.game_search = QLineEdit()
        self.game_search.setPlaceholderText('게임 이름 검색...')
        self.game_search.setClearButtonEnabled(True)
        self.game_search.textChanged.connect(self.filter_games)
        self.body.addWidget(self.game_search)
        self.game_list = QListWidget()
        self.game_list.setMinimumHeight(190)
        self.game_list.setMaximumHeight(240)
        for game in sorted(self.games, key=lambda g: self.library.title(g).casefold()):
            item = QListWidgetItem(self.library.title(game))
            item.setData(Qt.ItemDataRole.UserRole, game.id)
            self.game_list.addItem(item)
        self.game_list.currentItemChanged.connect(self.refresh)
        self.body.addWidget(self.game_list)
        self.selected_size = QLabel("")
        self.selected_size.setObjectName('Subtle')
        self.body.addWidget(self.selected_size)
        row = QHBoxLayout()
        one = QPushButton("선택 게임 이미지 정리")
        one.clicked.connect(self.clear_selected)
        row.addWidget(one)
        all_button = QPushButton("전체 이미지 캐시 정리")
        all_button.clicked.connect(self.clear_all)
        row.addWidget(all_button)
        self.body.addLayout(row)
        warn = QLabel(
            "이미지는 휴지통으로 이동합니다. 직접 지정하거나 GPT로 만든 이미지도 포함되며, "
            "원본이 없다면 자동 복구되지 않을 수 있습니다. "
            "EXE 아이콘 등 일부 이미지는 다음 조회 시 자동 재생성됩니다."
        )
        warn.setObjectName("Subtle")
        warn.setWordWrap(True)
        self.body.addWidget(warn)
        bottom = QHBoxLayout()
        folder = QPushButton("캐시 폴더 열기")
        folder.clicked.connect(self.open_cache_folder)
        bottom.addWidget(folder)
        bottom.addStretch(1)
        close = QPushButton("닫기")
        close.clicked.connect(self.accept)
        bottom.addWidget(close)
        self.body.addLayout(bottom)
        self.refresh()

    def filter_games(self, query: str):
        key = query.strip().casefold()
        for i in range(self.game_list.count()):
            item = self.game_list.item(i)
            item.setHidden(key not in item.text().casefold())

    def selected_game_id(self):
        item = self.game_list.currentItem()
        return item.data(Qt.ItemDataRole.UserRole) if item and not item.isHidden() else None

    def refresh(self, *_args):
        overall = image_stats(self.library.cache)
        self.summary.setText(
            f"이미지 캐시: {overall.files}개 · {friendly_bytes(overall.bytes)}"
        )
        cid = self.selected_game_id()
        selected = image_stats(self.library.cache, [cid]) if cid else None
        self.selected_size.setText(
            f"선택 게임: {selected.files}개 · {friendly_bytes(selected.bytes)}"
            if selected else "정리할 게임을 선택해 주세요."
        )

    def clear_selected(self):
        cid = self.selected_game_id()
        if not cid:
            show_message(self, "게임 선택", "먼저 게임을 선택해 주세요.")
            return
        self.clear_images([cid])

    def clear_all(self):
        self.clear_images(None)

    def clear_images(self, ids):
        stats = image_stats(self.library.cache, ids)
        if not stats.files:
            show_message(self, "이미지 캐시", "정리할 이미지 파일이 없습니다.")
            return
        if not ask_yes_no(self, "이미지 캐시 정리",
              f"이미지 {stats.files}개 ({friendly_bytes(stats.bytes)})를 휴지통으로 이동할까요?\n\n"
              "직접 지정한 이미지도 포함됩니다. 게임 정보·설정·모음집은 삭제되지 않습니다.",
              "정리", "취소"):
            return
        try:
            result = recycle_images(self.library.cache, ids)
        except Exception as exc:
            show_message(self, "정리 실패", f"이미지 이동에 실패했습니다.\n{exc}")
            self.refresh()
            return
        self.refresh()
        show_message(self, "캐시 정리 완료", f"이미지 {result.files}개를 휴지통으로 이동했습니다.")

    def open_cache_folder(self):
        path = self.library.cache
        if sys.platform == "win32":
            os.startfile(str(path))
        else:
            from PySide6.QtGui import QDesktopServices
            from PySide6.QtCore import QUrl
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))


class DataManagerDialog(ThemedDialog):
    """One place to manage library refresh, collections, metadata, artwork and backups."""

    def __init__(self, parent):
        super().__init__("라이브러리 데이터 관리", parent, 690)
        self.owner = parent
        self.setMinimumWidth(690)
        heading = QLabel("라이브러리 데이터 관리")
        heading.setObjectName("Heading")
        self.body.addWidget(heading)
        tip = QLabel("게임 목록 · 모음집 · 게임별 설정 · 이미지 캐시 · 작품명 조회 정보를 각각 관리합니다.\n"
                     "게임 ZIP/7z/RAR와 설치된 게임 파일은 여기서 삭제하지 않습니다.")
        tip.setWordWrap(True)
        tip.setObjectName("Subtle")
        self.body.addWidget(tip)
        self.tabs = QTabWidget()
        self.tabs.setStyleSheet("""
            QTabWidget::pane { border:1px solid #324a60; background:#1d2835; }
            QTabBar::tab { padding:9px 13px; background:#233547; border:1px solid #354b5c;
                           color:#b9c8d9; margin-right:3px; }
            QTabBar::tab:selected { background:#34526a; color:#fff; }
        """)
        self.body.addWidget(self.tabs)
        self._create_inventory_tab()
        self._create_collections_tab()
        self._create_cache_tab()
        self._create_backup_tab()
        bottom = QHBoxLayout()
        bottom.addStretch(1)
        close = QPushButton("닫기")
        close.clicked.connect(self.accept)
        bottom.addWidget(close)
        self.body.addLayout(bottom)
        self.refresh_all()

    def _tab(self, title):
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(15, 16, 15, 16)
        layout.setSpacing(10)
        self.tabs.addTab(widget, title)
        return layout

    def _create_inventory_tab(self):
        layout = self._tab("게임 목록")
        self.inventory_label = QLabel("")
        self.inventory_label.setWordWrap(True)
        self.inventory_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(self.inventory_label)
        info = QLabel("게임 목록은 지정한 압축파일 폴더와 설치 폴더에서 다시 검색합니다. "
                      "모음집과 게임명 설정은 별도 파일에 저장되므로 목록 새로고침으로 삭제되지 않습니다.")
        info.setWordWrap(True)
        info.setObjectName("Subtle")
        layout.addWidget(info)
        refresh = QPushButton("게임 목록 다시 검색")
        refresh.clicked.connect(self.rescan)
        layout.addWidget(refresh)
        layout.addStretch(1)

    def _create_collections_tab(self):
        layout = self._tab("모음집")
        label = QLabel("저장된 모음집 (실제 게임 파일 이동 없음)")
        label.setObjectName("DialogHeading")
        layout.addWidget(label)
        self.collection_list = QListWidget()
        self.collection_list.setMinimumHeight(185)
        layout.addWidget(self.collection_list)
        self.collection_info = QLabel("")
        self.collection_info.setObjectName("Subtle")
        self.collection_info.setWordWrap(True)
        layout.addWidget(self.collection_info)
        row = QHBoxLayout()
        for name, fn in (("+ 만들기", self.create_collection), ("이름 변경", self.rename_collection),
                         ("모음집 삭제", self.delete_collection)):
            button = QPushButton(name)
            button.clicked.connect(fn)
            row.addWidget(button)
        layout.addLayout(row)

    def _create_cache_tab(self):
        layout = self._tab("설정 · 캐시")
        self.cache_info = QLabel("")
        self.cache_info.setWordWrap(True)
        layout.addWidget(self.cache_info)
        explanation = QLabel("게임별 meta.json에는 표시 이름, 선택한 EXE, 첫 실행 승인 정보가 들어 있습니다. "
                             "이미지 캐시만 삭제해도 이 정보는 유지됩니다.")
        explanation.setWordWrap(True)
        explanation.setObjectName("Subtle")
        layout.addWidget(explanation)
        button = QPushButton("게임별 이미지 캐시 관리...")
        button.clicked.connect(self.manage_images)
        layout.addWidget(button)
        layout.addStretch(1)

    def _create_backup_tab(self):
        layout = self._tab("백업 · 복원")
        caption = QLabel("프로그램 데이터 전체 백업")
        caption.setObjectName("DialogHeading")
        layout.addWidget(caption)
        details = QLabel("포함: 폴더 설정, 모음집, 게임별 이름·실행파일 설정, 배너·아이콘, "
                         "작품명 조회 캐시, 현재 목록의 스냅샷.\n"
                         "제외: 실제 게임 압축파일/설치 파일/세이브, Windows에 보관된 AI API 키.\n"
                         "복원 시 게임 파일은 다시 검색하며, 백업에 있는 설정만 덮어씁니다.")
        details.setWordWrap(True)
        details.setObjectName("Subtle")
        layout.addWidget(details)
        backup = QPushButton("전체 데이터 ZIP 백업...")
        backup.clicked.connect(self.export_backup)
        layout.addWidget(backup)
        restore = QPushButton("백업 ZIP 복원...")
        restore.clicked.connect(self.import_backup)
        layout.addWidget(restore)
        hint = QLabel("복원 전에 현재 데이터를 자동으로 다시 백업합니다. "
                      "본체와 이름 관리자를 동시에 실행 중이면, 이름 관리자를 종료한 뒤 복원하세요.")
        hint.setObjectName("Subtle")
        hint.setWordWrap(True)
        layout.addWidget(hint)
        layout.addStretch(1)

    def refresh_all(self):
        lib = self.owner.library
        games = self.owner.games
        cols = self.owner.collections
        stats = inventory(lib, games, cols)
        self.inventory_label.setText(
            f"현재 게임 목록: {stats.games}개\n"
            f"설치된 게임: {stats.installed}개 · 압축파일 있는 게임: {stats.archives}개\n"
            f"모음집 연결: {stats.collection_memberships}개 "
            f"(현재 목록에 없는 연결 {stats.missing_memberships}개)"
        )
        self.collection_list.clear()
        for col in cols.list():
            item = QListWidgetItem(f"{col['name']}  ({len(col['game_ids'])}개 게임)")
            item.setData(Qt.ItemDataRole.UserRole, col['id'])
            self.collection_list.addItem(item)
        self.collection_info.setText(
            f"모음집 {stats.collections}개 · 게임 연결 {stats.collection_memberships}개\n"
            "현재 검색에서 누락된 게임은 일시적으로 분리된 드라이브에 있을 수 있어 자동 삭제하지 않습니다."
        )
        self.cache_info.setText(
            f"게임별 설정(meta.json): {stats.metadata}개\n"
            f"현재 게임 목록과 연결되지 않은 설정: {stats.orphaned_metadata}개 (삭제하지 않음)\n"
            f"배너·아이콘: {stats.images}개 · {friendly_bytes(stats.image_bytes)}\n"
            f"작품명 조회 기록: {stats.product_titles}개"
        )

    def rescan(self):
        self.owner.reload()
        self.refresh_all()

    def _selected_collection(self):
        item = self.collection_list.currentItem()
        if item is None:
            show_message(self, "모음집 선택", "먼저 모음집을 선택해 주세요.")
            return None
        return item.data(Qt.ItemDataRole.UserRole)

    def create_collection(self):
        name, ok = ask_text(self, "새 모음집", "모음집 이름:")
        if not ok:
            return
        try:
            self.owner.collections.create(name)
            self.owner.reload()
            self.refresh_all()
        except ValueError as exc:
            show_message(self, "모음집 생성 실패", str(exc))

    def rename_collection(self):
        cid = self._selected_collection()
        if not cid:
            return
        col = next((x for x in self.owner.collections.list() if x['id'] == cid), None)
        if col is None:
            return
        name, ok = ask_text(self, "모음집 이름 변경", "새 이름:", text=col['name'])
        if not ok:
            return
        try:
            self.owner.collections.rename(cid, name)
            self.owner.reload()
            self.refresh_all()
        except ValueError as exc:
            show_message(self, "변경 실패", str(exc))

    def delete_collection(self):
        cid = self._selected_collection()
        if not cid:
            return
        col = next((x for x in self.owner.collections.list() if x['id'] == cid), None)
        if col and ask_yes_no(self, "모음집 삭제",
                              f"'{col['name']}' 모음집만 삭제할까요?\n"
                              "게임 압축파일과 설치된 게임은 삭제되지 않습니다.\n"
                              "삭제하기 전에 '백업 · 복원'에서 백업하는 것을 권장합니다.", "삭제", "취소"):
            self.owner.collections.delete(cid)
            self.owner.reload()
            self.refresh_all()

    def manage_images(self):
        CacheManagerDialog(self.owner.library, self.owner.games, self).exec()
        self.owner.reload()
        self.refresh_all()

    def export_backup(self):
        name = 'PlayDock_Data_Backup.zip'
        default_folder = self.owner.library.store / 'backups'
        default_folder.mkdir(parents=True, exist_ok=True)
        chosen, _ = QFileDialog.getSaveFileName(
            self, "게임 라이브러리 데이터 백업", str(default_folder / name),
            "ZIP 백업 (*.zip)", options=QFileDialog.Option.DontUseNativeDialog)
        if not chosen:
            return
        target = Path(chosen)
        if target.exists() and not ask_yes_no(self, "백업 파일 덮어쓰기",
                                                "이미 있는 백업 파일을 덮어쓸까요?", "덮어쓰기", "취소"):
            return
        try:
            count = backup_data(self.owner.library.store, self.owner.games, target)
            show_message(self, "백업 완료", f"설정·모음집·목록 스냅샷·캐시 백업 완료\n"
                                             f"데이터 파일 {count}개\n{target}")
        except Exception as exc:
            show_message(self, "백업 실패", str(exc))

    def import_backup(self):
        selected, _ = QFileDialog.getOpenFileName(
            self, "라이브러리 데이터 백업 선택", str(self.owner.library.store / 'backups'),
            "ZIP 백업 (*.zip)", options=QFileDialog.Option.DontUseNativeDialog)
        if not selected:
            return
        try:
            files = inspect_backup(Path(selected))
        except Exception as exc:
            show_message(self, "백업 검사 실패", str(exc))
            return
        if not ask_yes_no(self, "데이터 복원 확인",
                          f"백업의 설정·모음집·캐시 {len(files)}개 파일을 현재 데이터에 복원할까요?\n"
                          "동일 파일은 덮어쓰지만 게임 파일은 변경하지 않습니다.\n"
                          "현재 데이터는 복원 직전에 자동 백업됩니다.", "복원", "취소"):
            return
        try:
            count, safety = restore_data(self.owner.library.store, Path(selected))
            self.owner.refresh_all_data()
            self.refresh_all()
            show_message(self, "복원 완료", f"{count}개 데이터 파일 복원\n복원 전 백업: {safety}")
        except Exception as exc:
            show_message(self, "복원 실패", str(exc))


class LibraryInfoDialog(ThemedDialog):
    def __init__(self, library: Library, games: list[Game], parent=None):
        super().__init__("라이브러리 속성", parent, 620)
        layout = self.body
        heading = QLabel("라이브러리 속성")
        heading.setObjectName("Heading")
        layout.addWidget(heading)
        hint = QLabel("메인 화면에는 경로를 숨기고, 여기에서만 자세한 정보를 볼 수 있습니다.")
        hint.setObjectName("Subtle")
        hint.setWordWrap(True)
        layout.addWidget(hint)
        installed = sum(1 for g in games if g.installed)
        meta_root = library.store
        rows = [
            ("압축파일 폴더", str(library.archive_root)),
            ("게임 설치 폴더", str(library.root)),
            ("캐시 / 설정 폴더", str(meta_root)),
            ("총 게임 수", f"{len(games)}개"),
            ("설치된 게임", f"{installed}개"),
            ("미설치 게임", f"{len(games) - installed}개"),
        ]
        info = QLabel()
        from html import escape
        table = ''.join(
            '<tr><td style="padding:6px 18px 6px 0; color:#8ea7b9; white-space:nowrap; vertical-align:top;">'
            + escape(a) + '</td><td style="padding:6px; color:#dceaf6;">' + escape(b) + '</td></tr>'
            for a, b in rows
        )
        info.setText('<table cellspacing="0" cellpadding="0">' + table + '</table>')
        info.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        info.setWordWrap(True)
        panel = QFrame()
        panel.setObjectName("InfoCard")
        pv = QVBoxLayout(panel)
        pv.setContentsMargins(16, 14, 16, 14)
        pv.addWidget(info)
        layout.addWidget(panel)
        data_btn = QPushButton("데이터 관리 (목록 · 모음집 · 캐시 · 백업)...")
        data_btn.setObjectName("Soft")
        data_btn.clicked.connect(lambda: parent.data_manager_dialog() if parent else None)
        layout.addWidget(data_btn)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.reject)
        buttons.accepted.connect(self.accept)
        buttons.button(QDialogButtonBox.StandardButton.Close).setText("닫기")
        layout.addWidget(buttons)

