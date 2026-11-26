"""PlayDock MainWindow Qt widget tree/layout.

Sections own widget construction only; controllers retain event handling and state.
"""

from PySide6.QtCore import Qt, QTimer, QSize
from PySide6.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QFrame, QLabel, QLineEdit,
    QSplitter, QScrollArea, QProgressBar, QSizePolicy, QTreeWidget,
    QAbstractItemView, QStackedWidget,
)
from ui.collection_board import CollectionBoard
from ui.widgets.launcher import CollectionArrowClickFilter


def build_main_ui(self, *, LibraryFilterButton, ChevronMenuButton, Banner):
    base = QWidget()
    self.setCentralWidget(base)
    outer = QVBoxLayout(base)
    outer.setContentsMargins(0, 0, 0, 0)
    outer.setSpacing(0)

    outer.addWidget(_build_top_bar(self, ChevronMenuButton))

    splitter = QSplitter(Qt.Orientation.Horizontal)
    splitter.setHandleWidth(2)
    splitter.setChildrenCollapsible(False)
    outer.addWidget(splitter, 1)

    splitter.addWidget(_build_sidebar(self, LibraryFilterButton, ChevronMenuButton))

    _build_game_details(self, ChevronMenuButton, Banner)
    splitter.addWidget(_build_content_stack(self))
    splitter.setStretchFactor(0, 0)
    splitter.setStretchFactor(1, 1)
    splitter.setSizes([318, 1062])
    # A clean blank footer, like Steam's bottom breathing room. No buttons,
    # text, install paths, game counts or download-management actions.
    footer = QFrame()
    footer.setObjectName("FooterBar")
    footer.setFixedHeight(42)
    outer.addWidget(footer)


def _build_top_bar(self, ChevronMenuButton):
    top = QFrame()
    top.setObjectName("TopBar")
    top_layout = QHBoxLayout(top)
    top_layout.setContentsMargins(15, 7, 15, 7)
    top_layout.setSpacing(7)
    name = QLabel("◇   PLAYDOCK")
    name.setObjectName("TopTitle")
    top_layout.addWidget(name)
    top_layout.addSpacing(13)
    nav = self.action_button("라이브러리", self.show_all_games)
    nav.setObjectName("TopNavigation")
    nav.setCheckable(True)
    nav.setAutoExclusive(True)
    nav.setChecked(True)
    self.library_nav_btn = nav
    top_layout.addWidget(nav)
    collections_nav = self.action_button("내 모음집", self.show_collections_overview)
    collections_nav.setObjectName("TopNavigation")
    collections_nav.setCheckable(True)
    collections_nav.setAutoExclusive(True)
    self.collections_nav_btn = collections_nav
    top_layout.addWidget(collections_nav)
    top_layout.addStretch(1)
    collect_btn = self.action_button("게임 정보 수집", self.collect_library_information)
    collect_btn.setObjectName("Blue")
    collect_btn.setToolTip("품번이 있는 게임의 공식 작품정보를 확인하고 PlayDock DB에 저장합니다.")
    top_layout.addWidget(collect_btn)
    self.catalog_collection_btn = collect_btn
    refresh_button = self.action_button("새로고침", self.reload)
    refresh_button.setObjectName("Soft")
    top_layout.addWidget(refresh_button)
    self.function_menu_btn = ChevronMenuButton('기능')
    self.function_menu_btn.clicked.connect(self.show_function_menu)
    self.function_menu_btn.setEnabled(False)
    top_layout.addWidget(self.function_menu_btn)
    self.settings_menu_btn = ChevronMenuButton("설정")
    self.settings_menu_btn.clicked.connect(self.show_settings_menu)
    self.support_btn = self.action_button("개발자 후원", self.open_support_page)
    self.support_btn.setObjectName("SupportButton")
    self.support_btn.setStyleSheet(
        "QPushButton#SupportButton { background:#25433f; color:#9de1d6;"
        " border:1px solid #69aaa1; border-radius:4px; padding:9px 10px; font-weight:600; }"
        "QPushButton#SupportButton:hover { background:#315b54; color:#e1fff9; }"
        "QPushButton#SupportButton:pressed { background:#1d3633; }"
        "QPushButton#SupportButton:focus { border-color:#b5f3e6; }"
    )
    top_layout.addWidget(self.support_btn)
    top_layout.addWidget(self.settings_menu_btn)
    self.support_btn.setVisible(self.library.settings.get("show_support_button", True) is not False)
    return top


def _build_sidebar(self, LibraryFilterButton, ChevronMenuButton):
    sidebar = QFrame()
    sidebar.setObjectName("Sidebar")
    sidebar.setMinimumWidth(298)
    sidebar_layout = QVBoxLayout(sidebar)
    sidebar_layout.setContentsMargins(6, 9, 6, 7)
    sidebar_layout.setSpacing(7)
    home = self.action_button("⌂   홈 / 전체 게임", self.show_all_games)
    home.setObjectName("Soft")
    sidebar_layout.addWidget(home)
    self.mode_filter = LibraryFilterButton()
    self.mode_filter.addItem("게임 라이브러리 · 전체", "all")
    self.mode_filter.addItem("설치된 게임만", "installed")
    self.mode_filter.addItem("설치하지 않은 게임만", "uninstalled")
    self.mode_filter.currentIndexChanged.connect(self.populate_games)
    sidebar_layout.addWidget(self.mode_filter)
    self.search = QLineEdit()
    self.search.setPlaceholderText("⌕  게임 검색...")
    self.search.setClearButtonEnabled(True)
    self.search.textChanged.connect(self.populate_games)
    sidebar_layout.addWidget(self.search)
    library_tools = QHBoxLayout()
    library_tools.setSpacing(6)
    add_manual = self.action_button('＋ 게임 등록', self.register_manual_game)
    add_manual.setObjectName('LibraryAdd')
    add_manual.setMinimumWidth(155)
    add_manual.setMinimumHeight(38)
    add_manual.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
    library_tools.addWidget(add_manual, 2)
    self.sort_button = ChevronMenuButton('정렬')
    self.sort_button.setMinimumWidth(95)
    self.sort_button.setMinimumHeight(38)
    self.sort_button.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
    self.sort_button.clicked.connect(self.open_sort_menu)
    library_tools.addWidget(self.sort_button, 1)
    sidebar_layout.addLayout(library_tools)
    collection_header = QHBoxLayout()
    collection_header.setContentsMargins(2, 2, 2, 2)
    collection_header.setSpacing(6)
    collection_label = self.action_button("모음집", self.show_collections_overview)
    collection_label.setObjectName("SectionLink")
    collection_header.addWidget(collection_label)
    collection_header.addStretch()
    add_btn = self.action_button("+ 새 모음집", self.new_collection)
    add_btn.setObjectName("Tiny")
    collection_header.addWidget(add_btn)
    sidebar_layout.addLayout(collection_header)

    self.tree = QTreeWidget()
    self.tree.setObjectName("GameTree")
    self.tree.setHeaderHidden(True)
    self.tree.setColumnCount(1)
    # Root rows start at the left edge; children use just a 10 px offset.
    # RootIsDecorated=False removes the default gutter; group icons are
    # custom anti-aliased chevrons, avoiding distorted triangle glyphs.
    self.tree.setRootIsDecorated(False)
    self.tree.setIndentation(10)
    self.tree.setExpandsOnDoubleClick(False)
    self.tree.setIconSize(QSize(22, 22))
    self.tree.setUniformRowHeights(True)
    self.tree.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
    self.tree.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
    self.tree.setTextElideMode(Qt.TextElideMode.ElideRight)
    self.tree.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
    self.tree.itemSelectionChanged.connect(self.on_tree_select)
    self.tree.itemClicked.connect(self.on_tree_clicked)
    self.collection_arrow_filter = CollectionArrowClickFilter(self.tree)
    self.collection_arrow_filter.toggleRequested.connect(self.toggle_group_expansion)
    self.tree.itemExpanded.connect(self.on_group_expanded)
    self.tree.itemCollapsed.connect(self.on_group_collapsed)
    self.tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
    self.tree.customContextMenuRequested.connect(self.sidebar_context_menu)
    sidebar_layout.addWidget(self.tree, 1)
    return sidebar


def _build_game_details(self, ChevronMenuButton, Banner):
    self.scroll = QScrollArea()
    self.scroll.setWidgetResizable(True)
    self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
    body = QWidget()
    self.scroll.setWidget(body)
    content = QVBoxLayout(body)
    content.setContentsMargins(11, 0, 11, 14)
    content.setSpacing(10)
    self.banner = Banner()
    content.addWidget(self.banner)

    actions = QFrame()
    actions.setObjectName("Panel")
    act = QHBoxLayout(actions)
    act.setContentsMargins(14, 8, 14, 8)
    self.main_button = self.action_button("▶  플레이", self.main_action, True)
    self.main_button.setMinimumWidth(150)
    act.addWidget(self.main_button)
    status_col = QVBoxLayout()
    self.status_title = QLabel("게임을 선택하세요")
    self.status_title.setObjectName("StatusChip")
    status_col.addWidget(self.status_title)
    self.status_detail = QLabel("설치 · 실행 · 모음집 관리")
    self.status_detail.setObjectName("Subtle")
    status_col.addWidget(self.status_detail)
    act.addLayout(status_col, 1)
    self.folder_btn = self.action_button("폴더 열기", self.open_game_folder)
    self.select_exe_btn = self.action_button("EXE 선택", self.pick_exe)
    act.addWidget(self.folder_btn)
    self.uninstall_btn = self.action_button("설치 제거", self.uninstall_game)
    self.uninstall_btn.setObjectName("Soft")
    self.uninstall_btn.setVisible(False)
    act.addWidget(self.uninstall_btn)
    act.addWidget(self.select_exe_btn)
    content.addWidget(actions)

    self.progress = QProgressBar()
    self.progress.setValue(0)
    self.progress.hide()
    content.addWidget(self.progress)

    # In-context, short-lived feedback replaces the permanent bottom
    # status bar. Nothing occupies this space when there is no activity.
    self.message = QLabel("")
    self.message.setObjectName("ActivityNotice")
    self.message.setWordWrap(True)
    self.message.hide()
    content.addWidget(self.message)
    self.message_timer = QTimer(self)
    self.message_timer.setSingleShot(True)
    self.message_timer.timeout.connect(self.message.hide)

    tools = QHBoxLayout()
    collection_button = self.action_button("＋  모음집에 추가 / 제거", self.edit_game_collections)
    tools.addWidget(collection_button)
    tools.addStretch(1)
    self.extra_menu_btn = ChevronMenuButton('게임 관리')
    self.extra_menu_btn.clicked.connect(self.show_extra_menu)
    tools.addWidget(self.extra_menu_btn)
    content.addLayout(tools)

    overview = QFrame()
    overview.setObjectName("InfoCard")
    ov = QVBoxLayout(overview)
    ov.setContentsMargins(20, 15, 20, 16)
    heading = QLabel("게임 정보")
    heading.setObjectName("Heading")
    ov.addWidget(heading)
    self.game_info = QLabel("게임을 선택하면 설치 정보와 파일 위치가 표시됩니다.")
    self.game_info.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
    self.game_info.setWordWrap(True)
    self.game_info.setMinimumHeight(88)
    ov.addWidget(self.game_info)
    content.addWidget(overview)

    content.addStretch()


def _build_content_stack(self):
    self.collections_board = CollectionBoard()
    self.collections_board.collectionOpened.connect(self.show_collection)
    self.collections_board.gameOpened.connect(self.open_game_from_board)
    self.collections_board.createRequested.connect(self.new_collection)
    self.collections_board.renameRequested.connect(self.rename_collection)
    self.collections_board.deleteRequested.connect(self.delete_collection)
    self.main_stack = QStackedWidget()
    self.main_stack.addWidget(self.scroll)
    self.main_stack.addWidget(self.collections_board)
    self.main_stack.currentChanged.connect(self.sync_top_navigation)
    return self.main_stack
