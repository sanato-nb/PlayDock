"""Shared QSS themes for the main PlayDock app and title editor.

Keep color and widget state presentation here; business rules remain out of UI.
"""

MAIN_STYLESHEET = (
    # 기본 위젯과 공통 입력 컨트롤
    """
QWidget { background:#171e28; color:#d8e0e9; font-family:'Malgun Gothic','Segoe UI',sans-serif; font-size:13px; }
QLabel { background:transparent; }
QComboBox { background:#182a3a; color:#e6eef7; padding:8px 10px;
    border:1px solid #3b576b; border-radius:4px; min-height:20px; }
QComboBox:hover { border-color:#6895b2; }
QComboBox::drop-down { border:none; width:25px; }
QComboBox QAbstractItemView { background:#172736; color:#e6eef7;
    border:1px solid #49677d; selection-background-color:#315573;
    selection-color:#ffffff; outline:none; }

"""
    # 메인 레이아웃과 주요 컨트롤
    """QMainWindow, QScrollArea { background:#171e28; border:none; }
QFrame#Sidebar { background:#1b2836; border-right:1px solid #0c1119; }
QFrame#TopBar { background:#111923; border-bottom:1px solid #243747; }
QLabel#TopTitle { font-size:17px; font-weight:800; color:#e5f1ff; }
QLabel#Subtle { color:#8598ab; }
QLabel#Heading { font-size:20px; font-weight:700; }
QLabel#StatusChip { background:#293f4f; padding:7px 13px; border-radius:5px; color:#a9d6f0; }
QLineEdit { background:#101923; color:white; padding:8px 11px; border:1px solid #33465a; border-radius:4px; selection-background-color:#216aa2; }
QLineEdit:focus { border-color:#5a9acb; }
QListWidget { border:none; background:#1d2835; outline:none; }
QListWidget::item { margin:2px 7px; padding:11px 10px; border-radius:4px; color:#c6d3df; }
QListWidget::item:hover { background:#324456; }
QListWidget::item:selected { background:#35506d; color:white; }
QPushButton { border:1px solid #3a5164; background:#2c3c4c; border-radius:3px; padding:9px 13px; color:#e6edf4; }
QPushButton:hover { background:#3c5369; }
QPushButton:disabled { color:#74818c; background:#26313b; }
QPushButton#Primary { background:#248a24; color:white; border:none; font-size:16px; font-weight:bold; padding:11px 25px; }
QPushButton#Primary:hover { background:#34a338; }
QPushButton#Primary:disabled { background:#376347; }
QPushButton#Blue { background:#237cb2; border:none; font-weight:bold; }
QPushButton#Blue:hover { background:#2d91d0; }
QProgressBar { border:1px solid #3d5368; background:#0f1720; height:11px; border-radius:5px; color:transparent; }
QProgressBar::chunk { background:#2a9ad7; border-radius:5px; }
QFrame#Panel { background:#202d3b; border:1px solid #33485d; border-radius:3px; }
QFrame#InfoCard { background:#1c2b39; border:1px solid #2c4152; border-radius:3px; }
"""
    # 스크롤바 및 목록 공통 스타일
    """/* A clean track: Qt's default scroll buttons produced tiny square glyphs. */
QScrollBar:vertical { background:#1b2836; border:none; width:9px; margin:0; }
QScrollBar::handle:vertical { background:#425a6e; border:none; border-radius:4px; min-height:30px; }
QScrollBar::handle:vertical:hover { background:#597892; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
    background:transparent; border:none; height:0px; width:0px; }
QScrollBar::up-arrow:vertical, QScrollBar::down-arrow:vertical {
    background:transparent; border:none; width:0px; height:0px; image:none; }
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background:transparent; border:none; }
QAbstractScrollArea::corner { background:#1b2836; border:none; }
QDialog { background:#1d2835; }
QCheckBox { spacing:8px; }
/* Match the collection title to the sidebar; no dark rectangle around the text. */
QLabel#SectionTitle { background:transparent; border:none; font-size:13px; font-weight:700; color:#b8c8d9; padding:0px 2px; }
QLabel#ActivityNotice { background:#21374a; border:1px solid #345269; border-radius:4px; color:#b8dcee; padding:7px 10px; }
QPushButton#Tiny { padding:6px 9px; min-width:24px; }
QPushButton#LibraryAdd { color:#f2f8ff; background:#2b526d; border:1px solid #50718b; font-weight:600; padding:8px 10px; }
QPushButton#LibraryAdd:hover { background:#386682; border-color:#76a3c1; }
QTreeWidget#GameTree { background:#1b2836; border:none; outline:none; color:#cbd6e1; }
QTreeWidget#GameTree::item { height:29px; border:none; padding:1px 2px; }
QTreeWidget#GameTree::item:hover { background:#2a3d50; }
QTreeWidget#GameTree::item:selected { background:#34536f; color:white; }
QTreeWidget#GameTree::branch { background:#1b2836; }
"""
    # 메뉴 및 탐색 버튼
    """QMenu { background:#192a3a; color:#dfeaf3; border:1px solid #38566c; padding:5px; font-size:13px; }
QMenu::item { padding:9px 20px 9px 22px; border-radius:3px; margin:2px; }
QMenu::item:selected { background:#2e526d; color:#ffffff; }
QMenu::item:checked { color:#7cc7f5; }
QMenu::item:disabled { color:#718295; background:transparent; }
QMenu::separator { height:1px; background:#31485a; margin:5px 8px; }
QPushButton#Soft { background:#253649; border:1px solid #334a60; }
QPushButton#Soft:hover { background:#344b60; }
QPushButton#TopNavigation { background:#253649; border:1px solid #334a60; }
QPushButton#TopNavigation:hover { background:#344b60; }
QPushButton#TopNavigation:checked { background:#237cb2; border:1px solid #237cb2; color:#fff; font-weight:700; }
QPushButton#TopNavigation:checked:hover { background:#2d91d0; }
QPushButton#MenuChevron { background:#253649; border:1px solid #334a60; border-radius:4px;
    padding:9px 29px 9px 12px; color:#e6edf4; }
QPushButton#MenuChevron:hover { background:#344b60; border-color:#506b83; }
QPushButton#MenuChevron:pressed, QPushButton#MenuChevron[menuOpen="true"] {
    background:#1c3448; border-color:#65a1c8; }
QPushButton#MenuChevron:disabled { background:#202b36; border:1px solid #303e4b; color:#738394; }
QListWidget#CollectionsList { background:#192431; border:1px solid #263a4e; border-radius:5px; }
QListWidget#CollectionsList::item { padding:7px 10px; }
"""
    # 모음집 화면과 하단 영역
    """/* Steam-like collection overview and clean, deliberately empty footer. */
QFrame#FooterBar { background:#111923; border-top:1px solid #2d3946; }
QWidget#CollectionBoardRoot { background:#202a38; }
QScrollArea#CollectionBoard { background:#202a38; border:none; }
QLabel#BoardHeading { background:transparent; color:#f0f5fa; font-size:20px; font-weight:700; }
QLabel#BoardSubtle { background:transparent; color:#9bacbd; font-size:12px; }
QWidget#BoardRule { background:#46566a; }
QPushButton#BoardBack { background:transparent; border:none; text-align:left;
    padding:5px 9px; color:#a6c5df; }
QPushButton#BoardBack:hover { background:#31475b; }
QPushButton#SectionLink { background:transparent; color:#b8c8d9; font-size:13px;
    font-weight:700; border:none; padding:0px 2px; text-align:left; }
QPushButton#SectionLink:hover { color:#ffffff; }

"""
    # 공통 대화상자
    """QFrame#DialogShell { background:#1d2835; border:1px solid #35506a; border-radius:7px; }
QFrame#DialogHeader { background:#111923; border-bottom:1px solid #31465a; border-top-left-radius:7px; border-top-right-radius:7px; }
QLabel#DialogTitle { color:#e7f1fb; font-size:13px; font-weight:700; }
QPushButton#DialogClose { background:transparent; border:none; color:#d8e8f4; min-width:30px; min-height:26px; padding:0; font-size:16px; }
QPushButton#DialogClose:hover { background:#35506d; border-radius:3px; }
QLabel#DialogHeading { color:#eef6ff; font-size:15px; font-weight:700; }

"""
)


EDITOR_STYLESHEET = """
QWidget { background:#171e28; color:#d8e0e9; font:13px 'Malgun Gothic'; }
QMainWindow { background:#171e28; }
QFrame#Header { background:#111923; border-bottom:1px solid #2d4659; }
QFrame#Panel { background:#1d2a37; border:1px solid #354b5d; border-radius:5px; }
QLabel { background:transparent; }
QLabel#Heading { color:#f1f5fb; font-size:19px; font-weight:700; }
QLabel#Muted { color:#9bb0c2; }
QLabel#SimpleValue { font-size:18px; color:#f1f5fb; font-weight:700; }
QFrame#SimplePanel { background:#1d2a37; border:1px solid #354b5d; border-radius:5px; }
QLineEdit { background:#101b27; border:1px solid #405a70; border-radius:4px;
    color:white; padding:9px; selection-background-color:#365875; }
QLineEdit:focus { border-color:#77a8c5; }
QListWidget { background:#1b2836; border:1px solid #2c4052; border-radius:4px;
    outline:none; }
QListWidget::item { padding:9px; }
QListWidget::item:selected { background:#365675; color:#ffffff; }
QListWidget::item:hover { background:#293d52; }
QPushButton { background:#2c4054; color:#e8f2fa; border:1px solid #466079;
    border-radius:4px; padding:9px 12px; }
QPushButton:hover { background:#3b5670; }
QPushButton:disabled { color:#73899a; background:#202d39; }
QPushButton#Save { background:#217e32; color:white; border:none; font-weight:700; }
QPushButton#Save:hover { background:#319b44; }
QTableWidget { background:#101b27; color:#d8e0e9; gridline-color:#344758; border:1px solid #334b60; }
QHeaderView::section { background:#263d51; color:#f0f5fb; border:0; padding:7px; }
QTextEdit { background:#101b27; border:1px solid #334b60; color:#d8e0e9; border-radius:4px; }
QScrollBar:vertical { background:#17222f; width:9px; border:none; }
QScrollBar::handle:vertical { background:#50677c; min-height:30px; border-radius:4px; }
QScrollBar::add-line:vertical,QScrollBar::sub-line:vertical { height:0; }
QScrollBar::add-page:vertical,QScrollBar::sub-page:vertical { background:transparent; }
"""


# Scoped to Qt file/folder dialogs; native window frame remains resizable.
FILE_DIALOG_STYLESHEET = """
QFileDialog { background:#1d2835; color:#e5eef7; }
QFileDialog QLabel { color:#e5eef7; }
QFileDialog QTreeView, QFileDialog QListView {
    background:#141e29; alternate-background-color:#1b2938; color:#edf5fc;
    border:1px solid #405b70; border-radius:3px; outline:none;
    selection-background-color:#315d7f; selection-color:#ffffff;
}
QFileDialog QTreeView::item, QFileDialog QListView::item { min-height:26px; padding:2px 4px; }
QFileDialog QTreeView::item:selected, QFileDialog QListView::item:selected { background:#315d7f; color:#fff; }
QFileDialog QHeaderView::section { background:#2b4358; color:#f3f7fc; padding:7px; border:0; border-right:1px solid #415a70; }
QFileDialog QToolButton { background:#2b4053; border:1px solid #415e74; border-radius:4px; padding:5px; }
QFileDialog QToolButton:hover { background:#3a5871; }
QFileDialog QToolButton:disabled { background:#202d39; border-color:#304352; }
QFileDialog QPushButton { min-width:78px; padding:8px 12px; }
QFileDialog QPushButton:default { background:#237cb2; color:#fff; border-color:#378bc0; }
QFileDialog QPushButton:disabled { background:#263440; color:#8493a1; border-color:#344756; }
QFileDialog QSizeGrip { background:transparent; width:0px; height:0px; }
"""


# Scoped selector styles; separate from the main-window QMenu rules.
DARK_POPUP_STYLE = """
QMenu {
    background-color:#182a3b;
    color:#ecf4fc;
    border:1px solid #4b6b85;
    padding:5px;
    font-family:'Malgun Gothic','Segoe UI',sans-serif;
    font-size:13px;
}
QMenu::item {
    color:#ecf4fc;
    background-color:#182a3b;
    padding:9px 18px 9px 25px;
    margin:2px 1px;
    min-height:20px;
}
QMenu::item:selected { background-color:#365a76; color:#ffffff; }
QMenu::item:disabled { color:#8092a2; }
QMenu::indicator:checked { image:none; }
"""

DARK_SELECTOR_STYLESHEET = '''
            QPushButton#DarkMenuSelect {
                background-color:#1e3143; color:#f3f8fc;
                border:1px solid #496b82; border-radius:4px;
                padding:8px 31px 8px 11px;
                text-align:left;
            }
            QPushButton#DarkMenuSelect:hover { background-color:#28465e; border-color:#76a6c2; }
            QPushButton#DarkMenuSelect:pressed { background-color:#31546e; }
        '''


# Keep the disabled override local to dialog action buttons.
DIALOG_ACTION_DISABLED_STYLE = "QPushButton#{role}:disabled {{ color:#74818c; background:#26313b; }}"
