"""PlayDock — Windows-friendly Steam-like launcher for local ZIP/7z/RAR/RAR games."""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, QFileInfo
from PySide6.QtGui import QColor, QFont, QBrush
from PySide6.QtWidgets import (
    QFileDialog,
    QDialog,
    QFileIconProvider,
    QAbstractItemView,
    QMenu,
    QTreeWidgetItem,
)

from core import Game, Library, load_json, chosen_executable
from game_collections import CollectionStore
from game_icons import game_art_icon
from library_tree import make_sidebar_groups
from artwork import discover_local


from ui.widgets.launcher import collection_chevron, friendly_bytes, game_placeholder_icon
from ui.dialogs.common import ask_text, ask_yes_no, show_message
from ui.dialogs.library import GameCollectionsDialog
from services.official_work_service import official_metadata_for_game, official_info_rows


class LibraryControllerMixin:
    """Keep workflow/event handling outside the Qt window layout."""

    def register_manual_game(self):
        path, _ = QFileDialog.getOpenFileName(
            self, '외부 게임 EXE 등록', str(self.library.root), '실행 파일 (*.exe)',
            options=QFileDialog.Option.DontUseNativeDialog)
        if not path:
            return
        try:
            game = self.library.add_manual_executable(Path(path))
            self.main_stack.setCurrentWidget(self.scroll)
            self.reload(prefer_id=game.id)
            self.set_message('외부 게임을 등록했습니다. 게임 파일은 이동하지 않았습니다.')
        except (OSError, ValueError) as exc:
            show_message(self, '게임 등록 실패', str(exc))


    def unregister_manual_game(self):
        game = self.current()
        if not game or not game.external:
            return
        if not ask_yes_no(self, '게임 연결 해제',
                          f'{self.library.title(game)}을(를) 목록에서만 제거할까요?\n'
                          '실제 게임 파일과 캐시는 삭제되지 않습니다.', '연결 해제', '취소'):
            return
        if self.library.remove_manual_executable(game):
            self.selected_id = None
            self.reload()


    def refresh_all_data(self):
        """Reopen saved files after data recovery, including the collections file."""
        self.library = Library(self.library.store)
        self.collections = CollectionStore(self.library.store)
        self.reload()


    def reload(self, prefer_id: str | None = None):
        # The separate Title Editor can change the preferred title language
        # while the launcher is open. Reload only that setting on refresh.
        fresh_config = load_json(self.library.config_path)
        if isinstance(fresh_config, dict):
            self.library.settings['title_language'] = fresh_config.get('title_language', 'ko')
        previous = prefer_id or self.selected_id
        self.games = self.library.scan()
        try:
            self.work_db.import_scanner_catalog()
        except (OSError, ValueError) as exc:
            # A damaged/missing scanner DB must never prevent loading PlayDock.
            self.set_message(f'공식 작품정보 DB 가져오기 실패: {exc}')
        try:
            self.work_db.sync_library(self.library, self.games)
        except Exception as exc:
            # A corrupted/locked catalogue must not prevent game installation.
            self.set_message(f'작품 DB 동기화 실패: {exc}')
        self.populate_games(previous)
        self.collections_board.set_data(self.library, self.games, self.collections)
        self.set_message("")


    def populate_games(self, prefer_id: str | None = None):
        # Qt signals pass an integer or string to this slot; they are not game IDs.
        if not isinstance(prefer_id, str) or not any(g.id == prefer_id for g in self.games):
            prefer_id = self.selected_id
        desired_id = prefer_id or self.selected_id
        query = self.search.text()
        filter_mode = self.mode_filter.currentData()
        rows = make_sidebar_groups(self.games, self.collections.list(), self.library.title,
                                  filter_mode or 'all', query, self.sort_mode)
        self.tree.blockSignals(True)
        self.tree.clear()
        self.selected_game_item = None
        first_game_item = None
        for group in rows:
            header = QTreeWidgetItem(self.tree)
            header.setData(0, Qt.ItemDataRole.UserRole, ("group", group.id))
            font = QFont('Malgun Gothic', 10, QFont.Weight.DemiBold)
            header.setFont(0, font)
            header.setForeground(0, QBrush(QColor('#b9cedf')))
            header.setToolTip(0, "")
            if group.id not in self.expanded_groups and query.strip():
                expanded = True
            else:
                expanded = group.id in self.expanded_groups
            for game in group.games:
                item = QTreeWidgetItem(header, [self.library.title(game)])
                item.setData(0, Qt.ItemDataRole.UserRole, ("game", game.id))
                item.setToolTip(0, "")
                art = self.library.art_dir(game) / 'icon.png'
                item.setIcon(0, game_art_icon(art, game_placeholder_icon()))
                if first_game_item is None:
                    first_game_item = item
                if game.id == desired_id and self.selected_game_item is None:
                    self.selected_game_item = item
            header.setExpanded(expanded)
            self.update_group_label(header)
        selected = self.selected_game_item or first_game_item
        if selected is not None:
            selected.parent().setExpanded(True)
            self.update_group_label(selected.parent())
            _kind, group_id = self.tree_identity(selected.parent())
            if _kind == "group":
                self.expanded_groups.add(group_id)
            self.tree.setCurrentItem(selected)
            self.tree.scrollToItem(selected, QAbstractItemView.ScrollHint.EnsureVisible)
            self.selected_id = self.tree_identity(selected)[1]
        else:
            self.selected_id = None
        self.tree.blockSignals(False)
        visible_ids = {g.id for group in rows for g in group.games}
        # Counts belong to the on-demand Properties dialog, not a footer.
        self.tree.setToolTip("")
        if selected is not None:
            self.present_game()
        else:
            self.banner.set_game('표시할 게임이 없습니다', '검색어나 필터를 변경해 보세요', None)
            self.main_button.setEnabled(False)
            self.status_title.setText('선택된 게임 없음')
            self.status_detail.setText('모음집을 펼쳐 게임을 선택하세요')
            self.game_info.setText('새 모음집을 만들고 게임을 추가하면 이곳에 표시됩니다.')
            self.folder_btn.setEnabled(False)
            self.uninstall_btn.setVisible(False)
            self.select_exe_btn.setEnabled(False)


    def on_tree_select(self):
        item = self.tree.currentItem()
        kind, value = self.tree_identity(item)
        if kind == 'game':
            self.selected_id = value
            self.selected_game_item = item
            self.main_stack.setCurrentWidget(self.scroll)
            self.present_game()


    def on_tree_clicked(self, item, _column):
        kind, _cid = self.tree_identity(item)
        if kind == 'group':
            item.setExpanded(not item.isExpanded())
            self.show_collection(_cid)


    def update_group_label(self, item):
        kind, cid = self.tree_identity(item)
        if kind != 'group':
            return
        if cid == '__uncategorized__':
            name = '미분류'
        else:
            name = next((c['name'] for c in self.collections.list() if c['id'] == cid), '모음집')
        item.setText(0, f"{name}  ({item.childCount()})")
        item.setIcon(0, collection_chevron(item.isExpanded()))


    def on_group_expanded(self, item):
        kind, cid = self.tree_identity(item)
        if kind == 'group':
            self.expanded_groups.add(cid)
            self.update_group_label(item)


    def on_group_collapsed(self, item):
        kind, cid = self.tree_identity(item)
        if kind == 'group':
            self.expanded_groups.discard(cid)
            self.update_group_label(item)


    def show_collections_overview(self):
        self.collections_board.set_data(self.library, self.games, self.collections)
        self.collections_board.show_overview()
        self.main_stack.setCurrentWidget(self.collections_board)


    def show_collection(self, cid: str):
        self.collections_board.show_collection(cid)
        self.main_stack.setCurrentWidget(self.collections_board)


    def open_game_from_board(self, game_id: str):
        self.mode_filter.setCurrentIndex(0)
        self.search.clear()
        self.selected_id = game_id
        self.populate_games(game_id)
        self.main_stack.setCurrentWidget(self.scroll)


    def show_all_games(self):
        self.main_stack.setCurrentWidget(self.scroll)
        self.mode_filter.setCurrentIndex(0)
        self.search.clear()
        self.expanded_groups.update(group['id'] for group in self.collections.list())
        self.expanded_groups.add('__uncategorized__')
        self.populate_games()


    def new_collection(self):
        name, ok = ask_text(self, "새 모음집", "모음집 이름:")
        if not ok:
            return
        try:
            cid = self.collections.create(name)
        except ValueError as exc:
            show_message(self, "모음집 생성 실패", str(exc))
            return
        self.expanded_groups.add(cid)
        self.populate_games()
        self.collections_board.refresh()
        if self.main_stack.currentWidget() is not self.collections_board:
            self.select_group(cid)


    def select_group(self, cid: str):
        for i in range(self.tree.topLevelItemCount()):
            item = self.tree.topLevelItem(i)
            if self.tree_identity(item) == ('group', cid):
                self.tree.setCurrentItem(item)
                item.setExpanded(True)
                return


    def sidebar_context_menu(self, point):
        item = self.tree.itemAt(point)
        if item is None:
            return
        self.tree.setCurrentItem(item)
        kind, value = self.tree_identity(item)
        menu = QMenu(self)
        if kind == 'group':
            if value == '__uncategorized__':
                menu.addAction('새 모음집 만들기', self.new_collection)
                menu.exec(self.tree.viewport().mapToGlobal(point))
                return
            rename = menu.addAction('모음집 이름 변경')
            delete = menu.addAction('모음집 삭제')
            choice = menu.exec(self.tree.viewport().mapToGlobal(point))
            if choice == rename:
                self.rename_collection()
            elif choice == delete:
                self.delete_collection()
        elif kind == 'game':
            choice = menu.addAction('모음집에 추가 / 제거')
            launch = menu.addAction('플레이 / 설치')
            edit_name = menu.addAction('게임 이름 수정...')
            db_lookup = menu.addAction('DLsite 작품 정보 조회·DB 저장...')
            official_page = menu.addAction('저장된 공식 작품 페이지 열기')
            game = self.current()
            remove = None
            if game is not None and game.installed and not game.external:
                menu.addSeparator()
                remove = menu.addAction('설치 제거 (휴지통으로 이동)')
            disconnect = None
            if game is not None and game.external:
                menu.addSeparator()
                disconnect = menu.addAction('외부 게임 연결 해제 (파일 유지)')
            picked = menu.exec(self.tree.viewport().mapToGlobal(point))
            if picked == choice:
                self.edit_game_collections()
            elif picked == launch:
                self.main_action()
            elif picked == edit_name:
                self.open_title_editor()
            elif picked == db_lookup:
                self.lookup_work_database()
            elif picked == official_page:
                self.open_saved_official_page()
            elif remove is not None and picked == remove:
                self.uninstall_game()
            elif disconnect is not None and picked == disconnect:
                self.unregister_manual_game()


    def rename_collection(self, cid: str | None = None):
        cid = cid or self.selected_collection()
        if cid == '__uncategorized__':
            return
        name = next((col['name'] for col in self.collections.list() if col['id'] == cid), '')
        new_name, ok = ask_text(self, '모음집 이름 변경', '새 이름:', text=name)
        if not ok:
            return
        try:
            self.collections.rename(cid, new_name)
        except ValueError as exc:
            show_message(self, '이름 변경 실패', str(exc))
            return
        self.populate_games(self.selected_id)
        self.collections_board.refresh()
        if self.main_stack.currentWidget() is not self.collections_board:
            self.select_group(cid)


    def delete_collection(self, cid: str | None = None):
        cid = cid or self.selected_collection()
        if cid == '__uncategorized__':
            return
        name = next((col['name'] for col in self.collections.list() if col['id'] == cid), '')
        if not ask_yes_no(self, '모음집 삭제', f"'{name}' 모음집을 삭제할까요?\n게임 파일과 캐시는 삭제되지 않습니다.", 'Yes', 'No'):
            return
        self.collections.delete(cid)
        self.expanded_groups.discard(cid)
        self.populate_games(self.selected_id)
        self.collections_board.refresh()


    def edit_game_collections(self):
        game = self.current()
        if not game:
            show_message(self, '게임 선택', '먼저 게임을 선택해 주세요.')
            return
        dialog = GameCollectionsDialog(self.collections, game, self.library.title(game), self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.expanded_groups.update(col['id'] for col in self.collections.for_game(game.id))
            self.populate_games(game.id)
            self.collections_board.refresh()


    def current(self) -> Game | None:
        if not self.selected_id:
            return None
        return next((g for g in self.games if g.id == self.selected_id), None)


    def work_db_info_rows(self, game):
        """Show stored catalogue details without editing user's custom title."""
        rows = []
        code = self.library.product_code(game)
        if code:
            try:
                record = self.work_db.get_work(code)
            except Exception:
                record = None
            if record:
                language = self.library.settings.get('title_language', 'ko')
                title = record['titles'].get(language) or record['fallback_title']
                rows.extend([
                    ('DB 작품명', title),
                    ('제작사', record.get('maker') or '정보 없음'),
                    ('발매일', record.get('release_date') or '정보 없음'),
                    ('장르', ', '.join(record.get('tags', [])[:8]) or '정보 없음'),
                ])
        try:
            official = official_metadata_for_game(self.library, game, self.work_db)
            rows.extend(official_info_rows(official))
        except (OSError, ValueError):
            pass  # Damaged/locked public catalogue must not block the detail UI.
        return rows

    def present_game(self):
        game = self.current()
        if game is None:
            return
        dest = self.library.art_dir(game)
        discover_local(self.library, game)
        title = self.library.title(game)
        exe = chosen_executable(self.library, game)
        if exe and not (dest / "icon.png").exists():
            try:
                provider = QFileIconProvider()
                icon = provider.icon(QFileInfo(str(exe)))
                pix = icon.pixmap(256, 256)
                if not pix.isNull():
                    pix.save(str(dest / "icon.png"))
            except Exception:
                pass
        current_item = self.selected_game_item
        if current_item and self.tree_identity(current_item) == ('game', game.id):
            art_file = dest / 'icon.png'
            current_item.setIcon(0, game_art_icon(art_file, game_placeholder_icon()))
        hero = dest / "hero.png"
        self.banner.set_game(title, "PLAYDOCK · " + game.status, hero if hero.exists() else None)
        self.status_title.setText(game.status)
        if game.installed:
            self.main_button.setText("▶  플레이" if exe else "실행 파일 선택")
            self.status_detail.setText(f"실행 대상: {exe.name if exe else '지정 필요'}")
        else:
            self.main_button.setText("↓  설치")
            self.status_detail.setText("압축을 풀어 설치할 수 있습니다")
        self.main_button.setEnabled(True)
        self.folder_btn.setEnabled(True)
        self.uninstall_btn.setVisible(game.installed and not game.external)
        self.uninstall_btn.setEnabled(game.installed and not game.external and self.install_worker is None and self.uninstall_worker is None)
        self.select_exe_btn.setEnabled(game.installed)
        archive = str(game.archive) if game.archive else "없음"
        size = ""
        if game.archive and game.archive.exists():
            size = f" ({friendly_bytes(game.archive.stat().st_size)})"
        folder = str(game.folder) if game.folder else "미설치"
        source = self.library.meta(game).get("artwork_source", "로컬 파일 / 기본 이미지")
        belonging = self.collections.for_game(game.id)
        collection_names = ", ".join(col["name"] for col in belonging) if belonging else "없음"
        from html import escape
        info_rows = [
            ('모음집', collection_names),
            *([('작품 코드', self.library.product_code(game))] if self.library.product_code(game) else []),
            *self.work_db_info_rows(game),
            *([('등록 방식', '외부 게임 직접 등록')] if game.external else []),
            ('상태', game.status),
            ('압축 파일', archive + size),
            ('설치 폴더', folder),
            ('실행 파일', str(exe) if exe else '미지정'),
            ('이미지', str(source)),
        ]
        rows = ''.join(
            '<tr><td style="padding:5px 18px 5px 0; color:#8ea7b9; white-space:nowrap;">'
            + escape(label) + '</td><td style="padding:5px; color:#dceaf6;">'
            + escape(value) + '</td></tr>'
            for label, value in info_rows
        )
        self.game_info.setText('<table cellspacing="0" cellpadding="0">' + rows + '</table>')

