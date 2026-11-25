"""Shared QSS themes for the main PlayDock app and title editor.

Keep color and widget state presentation here; business rules remain out of UI.
"""

MAIN_STYLESHEET = (
    # 기본 위젯과 공통 입력 컨트롤
    """
QWidget { background:#171719; color:#dddfe2; font-family:'Malgun Gothic','Segoe UI',sans-serif; font-size:13px; }
QLabel { background:transparent; }
QComboBox { background:#25272b; color:#ebedf0; padding:8px 10px;
    border:1px solid #505256; border-radius:5px; min-height:20px; }
QComboBox:hover { border-color:#8c8e91; }
QComboBox::drop-down { border:none; width:25px; }
QComboBox QAbstractItemView { background:#232529; color:#ebedf0;
    border:1px solid #606266; selection-background-color:#35313f;
    selection-color:#ffffff; outline:none; }

"""
    # 메인 레이아웃과 주요 컨트롤
    """QMainWindow, QScrollArea { background:#171719; border:none; }
QFrame#Sidebar { background:#1d1d20; border-right:1px solid #343438; }
QFrame#TopBar { background:#171719; border-bottom:1px solid #303034; }
QLabel#TopTitle { font-size:17px; font-weight:800; color:#e4d7ff; }
QLabel#Subtle { color:#939598; }
QLabel#Heading { font-size:20px; font-weight:700; }
QLabel#StatusChip { background:#302d37; padding:7px 13px; border-radius:5px; color:#ccced1; }
QLineEdit { background:#18181b; color:white; padding:8px 11px; border:1px solid #3b3b40; border-radius:5px; selection-background-color:#594b75; }
QLineEdit:focus { border-color:#ae98e8; }
QListWidget { border:none; background:#212124; outline:none; }
QListWidget::item { margin:2px 7px; padding:11px 10px; border-radius:5px; color:#cfd1d4; }
QListWidget::item:hover { background:#3f4145; }
QListWidget::item:selected { background:#383243; color:white; }
QPushButton { border:1px solid #414147; background:#252529; border-radius:5px; padding:9px 13px; color:#eaecef; }
QPushButton:hover { background:#38383e; }
QPushButton:disabled { color:#72777e; background:#25282c; }
QPushButton#Primary { background:#393143; color:#f1eaff; border:1px solid #a28acb; border-radius:7px; font-size:16px; font-weight:bold; padding:11px 25px; }
QPushButton#Primary:hover { background:#4a3e59; border-color:#c5aef5; }
QPushButton#Primary:disabled { background:#323039; color:#99a6b1; }
QPushButton#Blue { background:#302a3a; color:#e5d8ff; border:1px solid #786694; font-weight:bold; }
QPushButton#Blue:hover { background:#41364f; border-color:#b19bd9; }
QProgressBar { border:1px solid #4e5054; background:#14161a; height:11px; border-radius:5px; color:transparent; }
QProgressBar::chunk { background:#ae98e8; border-radius:5px; }
QFrame#Panel { background:#202023; border:1px solid #38383e; border-radius:8px; }
QFrame#InfoCard { background:#222225; border:1px solid #38383e; border-radius:8px; }
"""
    # 스크롤바 및 목록 공통 스타일
    """/* A clean track: Qt's default scroll buttons produced tiny square glyphs. */
QScrollBar:vertical { background:#1d1d20; border:none; width:9px; margin:0; }
QScrollBar::handle:vertical { background:#54565a; border:none; border-radius:5px; min-height:30px; }
QScrollBar::handle:vertical:hover { background:#717377; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
    background:transparent; border:none; height:0px; width:0px; }
QScrollBar::up-arrow:vertical, QScrollBar::down-arrow:vertical {
    background:transparent; border:none; width:0px; height:0px; image:none; }
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background:transparent; border:none; }
QAbstractScrollArea::corner { background:#1d1d20; border:none; }
QDialog { background:#212124; }
QCheckBox { spacing:8px; }
QTableWidget { background:#1b1b1e; alternate-background-color:#242427; color:#e8e6ed; gridline-color:#36363c; border:1px solid #38383e; selection-background-color:#393344; selection-color:#ffffff; }
QHeaderView::section { background:#29292e; color:#dedbe6; border:0; border-bottom:1px solid #414147; padding:7px; }
QPlainTextEdit, QTextEdit { background:#19191c; color:#e8e6ed; border:1px solid #3b3b40; border-radius:5px; selection-background-color:#594b75; }
/* Match the collection title to the sidebar; no dark rectangle around the text. */
QLabel#SectionTitle { background:transparent; border:none; font-size:13px; font-weight:700; color:#c4c6c9; padding:0px 2px; }
QLabel#ActivityNotice { background:#323438; border:1px solid #4b4d51; border-radius:5px; color:#d4d6d9; padding:7px 10px; }
QPushButton#Tiny { padding:6px 9px; min-width:24px; }
QPushButton#LibraryAdd { color:#f5f7fa; background:#302c39; border:1px solid #75648e; font-weight:600; padding:8px 10px; }
QPushButton#LibraryAdd:hover { background:#40364f; border-color:#9a9c9f; }
QTreeWidget#GameTree { background:#1d1d20; border:none; outline:none; color:#d2d4d7; }
QTreeWidget#GameTree::item { height:29px; border-left:3px solid transparent; padding:1px 0px; }
QTreeWidget#GameTree::item:hover { background:#383a3e; }
QTreeWidget#GameTree::item:selected { background:#35313f; border-left:3px solid #b9a5ed; color:#f2eaff; }
QTreeWidget#GameTree::branch { background:#1d1d20; }
"""
    # 메뉴 및 탐색 버튼
    """QMenu { background:#242428; color:#e6e8eb; border:1px solid #4f5155; padding:5px; font-size:13px; }
QMenu::item { padding:9px 20px 9px 22px; border-radius:5px; margin:2px; }
QMenu::item:selected { background:#393344; color:#ffffff; }
QMenu::item:checked { color:#c6b3fb; }
QMenu::item:disabled { color:#7e8083; background:transparent; }
QMenu::separator { height:1px; background:#424448; margin:5px 8px; }
QPushButton#Soft { background:#202023; border:1px solid #3b3b41; }
QPushButton#Soft:hover { background:#303036; }
QPushButton#TopNavigation { background:transparent; border:1px solid transparent; border-bottom:2px solid transparent; border-radius:0px; color:#bcbac4; }
QPushButton#TopNavigation:hover { background:#27252d; color:#f5f0ff; }
QPushButton#TopNavigation:checked { background:transparent; border:1px solid transparent; border-bottom:2px solid #b9a5ed; border-radius:0px; color:#dfd1fa; font-weight:700; }
QPushButton#TopNavigation:checked:hover { background:#27252d; }
QPushButton#MenuChevron { background:#27272a; border:1px solid #3b3b41; border-radius:5px;
    padding:9px 29px 9px 12px; color:#eaecef; }
QPushButton#MenuChevron:hover { background:#303036; border-color:#65676b; }
QPushButton#MenuChevron:pressed, QPushButton#MenuChevron[menuOpen="true"] {
    background:#34303e; border-color:#ac96e6; }
QPushButton#MenuChevron:disabled { background:#27292d; border:1px solid #3a3c40; color:#7f8184; }
QListWidget#CollectionsList { background:#212327; border:1px solid #35373b; border-radius:5px; }
QListWidget#CollectionsList::item { padding:7px 10px; }
"""
    # 모음집 화면과 하단 영역
    """/* Steam-like collection overview and clean, deliberately empty footer. */
QFrame#FooterBar { background:#171719; border-top:1px solid #303034; }
QWidget#CollectionBoardRoot { background:#19191c; }
QScrollArea#CollectionBoard { background:#19191c; border:none; }
QLabel#BoardHeading { background:transparent; color:#f2f4f7; font-size:20px; font-weight:700; }
QLabel#BoardSubtle { background:transparent; color:#a8aaad; font-size:12px; }
QWidget#BoardRule { background:#525458; }
QPushButton#BoardBack { background:transparent; border:none; text-align:left;
    padding:5px 9px; color:#bec0c3; }
QPushButton#BoardBack:hover { background:#424448; }
QPushButton#SectionLink { background:transparent; color:#c4c6c9; font-size:13px;
    font-weight:700; border:none; padding:0px 2px; text-align:left; }
QPushButton#SectionLink:hover { color:#ffffff; }

"""
    # 공통 대화상자
    """QFrame#DialogShell { background:#212124; border:1px solid #414147; border-radius:7px; }
QFrame#DialogHeader { background:#171719; border-bottom:1px solid #383d43; border-top-left-radius:7px; border-top-right-radius:7px; }
QLabel#DialogTitle { color:#eef0f3; font-size:13px; font-weight:700; }
QPushButton#DialogClose { background:transparent; border:none; color:#e3e5e8; min-width:30px; min-height:26px; padding:0; font-size:16px; }
QPushButton#DialogClose:hover { background:#383243; border-radius:5px; }
QLabel#DialogHeading { color:#f3f5f8; font-size:15px; font-weight:700; }

"""
)


EDITOR_STYLESHEET = """
QWidget { background:#171719; color:#dddfe2; font:13px 'Malgun Gothic'; }
QMainWindow { background:#171719; }
QFrame#Header { background:#171719; border-bottom:1px solid #404246; }
QFrame#Panel { background:#26282c; border:1px solid #46484c; border-radius:5px; }
QLabel { background:transparent; }
QLabel#Heading { color:#f3f5f8; font-size:19px; font-weight:700; }
QLabel#Muted { color:#abadb0; }
QLabel#SimpleValue { font-size:18px; color:#f3f5f8; font-weight:700; }
QFrame#SimplePanel { background:#26282c; border:1px solid #46484c; border-radius:5px; }
QLineEdit { background:#181a1e; border:1px solid #54565a; border-radius:5px;
    color:white; padding:9px; selection-background-color:#393344; }
QLineEdit:focus { border-color:#9ea0a3; }
QListWidget { background:#1d1d20; border:1px solid #3b3d41; border-radius:5px;
    outline:none; }
QListWidget::item { padding:9px; }
QListWidget::item:selected { background:#393344; color:#ffffff; }
QListWidget::item:hover { background:#383a3e; }
QPushButton { background:#3b3d41; color:#eef0f3; border:1px solid #5a5c60;
    border-radius:5px; padding:9px 12px; }
QPushButton:hover { background:#505256; }
QPushButton:disabled { color:#848689; background:#292b2f; }
QPushButton#Save { background:#393143; color:#f1eaff; border:1px solid #a28acb; font-weight:700; }
QPushButton#Save:hover { background:#4a3e59; }
QTableWidget { background:#181a1e; color:#dddfe2; gridline-color:#424448; border:1px solid #45474b; }
QHeaderView::section { background:#383a3e; color:#f2f4f7; border:0; padding:7px; }
QTextEdit { background:#181a1e; border:1px solid #45474b; color:#dddfe2; border-radius:5px; }
QScrollBar:vertical { background:#1f2125; width:9px; border:none; }
QScrollBar::handle:vertical { background:#626468; min-height:30px; border-radius:5px; }
QScrollBar::add-line:vertical,QScrollBar::sub-line:vertical { height:0; }
QScrollBar::add-page:vertical,QScrollBar::sub-page:vertical { background:transparent; }
"""


# Scoped to Qt file/folder dialogs; native window frame remains resizable.
FILE_DIALOG_STYLESHEET = """
QFileDialog { background:#212124; color:#ebedf0; }
QFileDialog QLabel { color:#ebedf0; }
QFileDialog QTreeView, QFileDialog QListView {
    background:#171719; alternate-background-color:#1c1f23; color:#f2f4f7;
    border:1px solid #55575b; border-radius:5px; outline:none;
    selection-background-color:#383243; selection-color:#ffffff;
}
QFileDialog QTreeView::item, QFileDialog QListView::item { min-height:26px; padding:2px 4px; }
QFileDialog QTreeView::item:selected, QFileDialog QListView::item:selected { background:#383243; color:#fff; }
QFileDialog QHeaderView::section { background:#3d3f43; color:#f5f7fa; padding:7px; border:0; border-right:1px solid #54565a; }
QFileDialog QToolButton { background:#3b3d41; border:1px solid #57595d; border-radius:5px; padding:5px; }
QFileDialog QToolButton:hover { background:#515357; }
QFileDialog QToolButton:disabled { background:#292b2f; border-color:#3e4044; }
QFileDialog QPushButton { min-width:78px; padding:8px 12px; }
QFileDialog QPushButton:default { background:#514568; color:#fff; border-color:#7b7d80; }
QFileDialog QPushButton:disabled { background:#303236; color:#8f9194; border-color:#424448; }
QFileDialog QSizeGrip { background:transparent; width:0px; height:0px; }
"""


# Scoped selector styles; separate from the main-window QMenu rules.
DARK_POPUP_STYLE = """
QMenu {
    background-color:#242428;
    color:#f1eff4;
    border:1px solid #64666a;
    padding:5px;
    font-family:'Malgun Gothic','Segoe UI',sans-serif;
    font-size:13px;
}
QMenu::item {
    color:#f1eff4;
    background-color:#242428;
    padding:9px 18px 9px 25px;
    margin:2px 1px;
    min-height:20px;
}
QMenu::item:selected { background-color:#393344; color:#ffffff; }
QMenu::item:disabled { color:#8d8f92; }
QMenu::indicator:checked { image:none; }
"""

DARK_SELECTOR_STYLESHEET = '''
            QPushButton#DarkMenuSelect {
                background-color:#262629; color:#f5f7fa;
                border:1px solid #636569; border-radius:5px;
                padding:8px 31px 8px 11px;
                text-align:left;
            }
            QPushButton#DarkMenuSelect:hover { background-color:#3f4145; border-color:#9c9ea1; }
            QPushButton#DarkMenuSelect:pressed { background-color:#4c4e52; }
        '''


# Keep the disabled override local to dialog action buttons.
DIALOG_ACTION_DISABLED_STYLE = "QPushButton#{role}:disabled {{ color:#72777e; background:#25282c; }}"
