"""Shared QSS themes for the main PlayDock app and title editor.

Keep color and widget state presentation here; business rules remain out of UI.
"""

MAIN_STYLESHEET = (
    # 기본 위젯과 공통 입력 컨트롤
    """
QWidget { background:#15171a; color:#dddfe2; font-family:'Malgun Gothic','Segoe UI',sans-serif; font-size:13px; }
QLabel { background:transparent; }
QComboBox { background:#25272b; color:#ebedf0; padding:8px 10px;
    border:1px solid #505256; border-radius:5px; min-height:20px; }
QComboBox:hover { border-color:#8c8e91; }
QComboBox::drop-down { border:none; width:25px; }
QComboBox QAbstractItemView { background:#232529; color:#ebedf0;
    border:1px solid #606266; selection-background-color:#23445e;
    selection-color:#ffffff; outline:none; }

"""
    # 메인 레이아웃과 주요 컨트롤
    """QMainWindow, QScrollArea { background:#15171a; border:none; }
QFrame#Sidebar { background:#1b1e22; border-right:1px solid #101113; }
QFrame#TopBar { background:#121416; border-bottom:1px solid #30343a; }
QLabel#TopTitle { font-size:17px; font-weight:800; color:#edeff2; }
QLabel#Subtle { color:#939598; }
QLabel#Heading { font-size:20px; font-weight:700; }
QLabel#StatusChip { background:#393b3f; padding:7px 13px; border-radius:5px; color:#ccced1; }
QLineEdit { background:#131518; color:white; padding:8px 11px; border:1px solid #3b4047; border-radius:5px; selection-background-color:#176ba7; }
QLineEdit:focus { border-color:#8e9093; }
QListWidget { border:none; background:#202327; outline:none; }
QListWidget::item { margin:2px 7px; padding:11px 10px; border-radius:5px; color:#cfd1d4; }
QListWidget::item:hover { background:#3f4145; }
QListWidget::item:selected { background:#233d52; color:white; }
QPushButton { border:1px solid #434951; background:#292d32; border-radius:5px; padding:9px 13px; color:#eaecef; }
QPushButton:hover { background:#363b42; }
QPushButton:disabled { color:#72777e; background:#25282c; }
QPushButton#Primary { background:#096bb2; color:white; border:none; font-size:16px; font-weight:bold; padding:11px 25px; }
QPushButton#Primary:hover { background:#1684cf; }
QPushButton#Primary:disabled { background:#263c4d; color:#99a6b1; }
QPushButton#Blue { background:#126fb6; border:none; font-weight:bold; }
QPushButton#Blue:hover { background:#1985d3; }
QProgressBar { border:1px solid #4e5054; background:#14161a; height:11px; border-radius:5px; color:transparent; }
QProgressBar::chunk { background:#2796df; border-radius:5px; }
QFrame#Panel { background:#202328; border:1px solid #363b42; border-radius:5px; }
QFrame#InfoCard { background:#1e2125; border:1px solid #363b42; border-radius:5px; }
"""
    # 스크롤바 및 목록 공통 스타일
    """/* A clean track: Qt's default scroll buttons produced tiny square glyphs. */
QScrollBar:vertical { background:#1b1e22; border:none; width:9px; margin:0; }
QScrollBar::handle:vertical { background:#54565a; border:none; border-radius:5px; min-height:30px; }
QScrollBar::handle:vertical:hover { background:#717377; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
    background:transparent; border:none; height:0px; width:0px; }
QScrollBar::up-arrow:vertical, QScrollBar::down-arrow:vertical {
    background:transparent; border:none; width:0px; height:0px; image:none; }
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background:transparent; border:none; }
QAbstractScrollArea::corner { background:#1b1e22; border:none; }
QDialog { background:#202327; }
QCheckBox { spacing:8px; }
/* Match the collection title to the sidebar; no dark rectangle around the text. */
QLabel#SectionTitle { background:transparent; border:none; font-size:13px; font-weight:700; color:#c4c6c9; padding:0px 2px; }
QLabel#ActivityNotice { background:#323438; border:1px solid #4b4d51; border-radius:5px; color:#d4d6d9; padding:7px 10px; }
QPushButton#Tiny { padding:6px 9px; min-width:24px; }
QPushButton#LibraryAdd { color:#f5f7fa; background:#264b66; border:1px solid #416b8b; font-weight:600; padding:8px 10px; }
QPushButton#LibraryAdd:hover { background:#315c7b; border-color:#9a9c9f; }
QTreeWidget#GameTree { background:#1b1e22; border:none; outline:none; color:#d2d4d7; }
QTreeWidget#GameTree::item { height:29px; border:none; padding:1px 2px; }
QTreeWidget#GameTree::item:hover { background:#383a3e; }
QTreeWidget#GameTree::item:selected { background:#23445e; color:white; }
QTreeWidget#GameTree::branch { background:#1b1e22; }
"""
    # 메뉴 및 탐색 버튼
    """QMenu { background:#22252a; color:#e6e8eb; border:1px solid #4f5155; padding:5px; font-size:13px; }
QMenu::item { padding:9px 20px 9px 22px; border-radius:5px; margin:2px; }
QMenu::item:selected { background:#264961; color:#ffffff; }
QMenu::item:checked { color:#74c3fc; }
QMenu::item:disabled { color:#7e8083; background:transparent; }
QMenu::separator { height:1px; background:#424448; margin:5px 8px; }
QPushButton#Soft { background:#272b30; border:1px solid #3b4148; }
QPushButton#Soft:hover { background:#343b43; }
QPushButton#TopNavigation { background:#272b30; border:1px solid #3b4148; }
QPushButton#TopNavigation:hover { background:#343b43; }
QPushButton#TopNavigation:checked { background:#126fb6; border:1px solid #126fb6; color:#fff; font-weight:700; }
QPushButton#TopNavigation:checked:hover { background:#1985d3; }
QPushButton#MenuChevron { background:#272b30; border:1px solid #3b4148; border-radius:5px;
    padding:9px 29px 9px 12px; color:#eaecef; }
QPushButton#MenuChevron:hover { background:#343b43; border-color:#65676b; }
QPushButton#MenuChevron:pressed, QPushButton#MenuChevron[menuOpen="true"] {
    background:#263a4b; border-color:#369be1; }
QPushButton#MenuChevron:disabled { background:#27292d; border:1px solid #3a3c40; color:#7f8184; }
QListWidget#CollectionsList { background:#212327; border:1px solid #35373b; border-radius:5px; }
QListWidget#CollectionsList::item { padding:7px 10px; }
"""
    # 모음집 화면과 하단 영역
    """/* Steam-like collection overview and clean, deliberately empty footer. */
QFrame#FooterBar { background:#121416; border-top:1px solid #30343a; }
QWidget#CollectionBoardRoot { background:#191b1f; }
QScrollArea#CollectionBoard { background:#191b1f; border:none; }
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
    """QFrame#DialogShell { background:#202327; border:1px solid #434951; border-radius:7px; }
QFrame#DialogHeader { background:#121416; border-bottom:1px solid #383d43; border-top-left-radius:7px; border-top-right-radius:7px; }
QLabel#DialogTitle { color:#eef0f3; font-size:13px; font-weight:700; }
QPushButton#DialogClose { background:transparent; border:none; color:#e3e5e8; min-width:30px; min-height:26px; padding:0; font-size:16px; }
QPushButton#DialogClose:hover { background:#233d52; border-radius:5px; }
QLabel#DialogHeading { color:#f3f5f8; font-size:15px; font-weight:700; }

"""
)


EDITOR_STYLESHEET = """
QWidget { background:#15171a; color:#dddfe2; font:13px 'Malgun Gothic'; }
QMainWindow { background:#15171a; }
QFrame#Header { background:#121416; border-bottom:1px solid #404246; }
QFrame#Panel { background:#26282c; border:1px solid #46484c; border-radius:5px; }
QLabel { background:transparent; }
QLabel#Heading { color:#f3f5f8; font-size:19px; font-weight:700; }
QLabel#Muted { color:#abadb0; }
QLabel#SimpleValue { font-size:18px; color:#f3f5f8; font-weight:700; }
QFrame#SimplePanel { background:#26282c; border:1px solid #46484c; border-radius:5px; }
QLineEdit { background:#181a1e; border:1px solid #54565a; border-radius:5px;
    color:white; padding:9px; selection-background-color:#28495e; }
QLineEdit:focus { border-color:#9ea0a3; }
QListWidget { background:#1b1e22; border:1px solid #3b3d41; border-radius:5px;
    outline:none; }
QListWidget::item { padding:9px; }
QListWidget::item:selected { background:#28495e; color:#ffffff; }
QListWidget::item:hover { background:#383a3e; }
QPushButton { background:#3b3d41; color:#eef0f3; border:1px solid #5a5c60;
    border-radius:5px; padding:9px 12px; }
QPushButton:hover { background:#505256; }
QPushButton:disabled { color:#848689; background:#292b2f; }
QPushButton#Save { background:#126fb6; color:white; border:none; font-weight:700; }
QPushButton#Save:hover { background:#1985d3; }
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
QFileDialog { background:#202327; color:#ebedf0; }
QFileDialog QLabel { color:#ebedf0; }
QFileDialog QTreeView, QFileDialog QListView {
    background:#15171a; alternate-background-color:#1c1f23; color:#f2f4f7;
    border:1px solid #55575b; border-radius:5px; outline:none;
    selection-background-color:#234d6b; selection-color:#ffffff;
}
QFileDialog QTreeView::item, QFileDialog QListView::item { min-height:26px; padding:2px 4px; }
QFileDialog QTreeView::item:selected, QFileDialog QListView::item:selected { background:#234d6b; color:#fff; }
QFileDialog QHeaderView::section { background:#3d3f43; color:#f5f7fa; padding:7px; border:0; border-right:1px solid #54565a; }
QFileDialog QToolButton { background:#3b3d41; border:1px solid #57595d; border-radius:5px; padding:5px; }
QFileDialog QToolButton:hover { background:#515357; }
QFileDialog QToolButton:disabled { background:#292b2f; border-color:#3e4044; }
QFileDialog QPushButton { min-width:78px; padding:8px 12px; }
QFileDialog QPushButton:default { background:#126fb6; color:#fff; border-color:#7b7d80; }
QFileDialog QPushButton:disabled { background:#303236; color:#8f9194; border-color:#424448; }
QFileDialog QSizeGrip { background:transparent; width:0px; height:0px; }
"""


# Scoped selector styles; separate from the main-window QMenu rules.
DARK_POPUP_STYLE = """
QMenu {
    background-color:#22252a;
    color:#f1f3f6;
    border:1px solid #64666a;
    padding:5px;
    font-family:'Malgun Gothic','Segoe UI',sans-serif;
    font-size:13px;
}
QMenu::item {
    color:#f1f3f6;
    background-color:#22252a;
    padding:9px 18px 9px 25px;
    margin:2px 1px;
    min-height:20px;
}
QMenu::item:selected { background-color:#28495e; color:#ffffff; }
QMenu::item:disabled { color:#8d8f92; }
QMenu::indicator:checked { image:none; }
"""

DARK_SELECTOR_STYLESHEET = '''
            QPushButton#DarkMenuSelect {
                background-color:#24282d; color:#f5f7fa;
                border:1px solid #636569; border-radius:5px;
                padding:8px 31px 8px 11px;
                text-align:left;
            }
            QPushButton#DarkMenuSelect:hover { background-color:#3f4145; border-color:#9c9ea1; }
            QPushButton#DarkMenuSelect:pressed { background-color:#4c4e52; }
        '''


# Keep the disabled override local to dialog action buttons.
DIALOG_ACTION_DISABLED_STYLE = "QPushButton#{role}:disabled {{ color:#72777e; background:#25282c; }}"


def configure_wizard_style(root):
    """Apply the same Flat Dark palette to Tk setup/uninstall without Qt."""
    from tkinter import ttk
    style = ttk.Style(root)
    if "clam" in style.theme_names():
        style.theme_use("clam")
    style.configure("TButton", background="#292d32", foreground="#eaecef",
                    bordercolor="#434951", lightcolor="#434951", darkcolor="#434951",
                    padding=(12, 6), font=("Malgun Gothic", 10))
    style.map("TButton", background=[("disabled", "#25282c"), ("pressed", "#202327"), ("active", "#363b42")],
              foreground=[("disabled", "#72777e")])
    style.configure("Primary.TButton", background="#126fb6", foreground="#ffffff",
                    bordercolor="#126fb6", lightcolor="#126fb6", darkcolor="#126fb6")
    style.map("Primary.TButton", background=[("disabled", "#263c4d"), ("pressed", "#096bb2"), ("active", "#1985d3")],
              foreground=[("disabled", "#99a6b1")])
    style.configure("TEntry", fieldbackground="#131518", foreground="#eaecef",
                    insertcolor="#ffffff", bordercolor="#434951", lightcolor="#434951",
                    darkcolor="#434951", selectbackground="#176ba7", selectforeground="#ffffff")
    style.map("TEntry", bordercolor=[("focus", "#2796df")])
    style.configure("Wizard.Horizontal.TProgressbar", thickness=14, troughcolor="#131518",
                    background="#2796df", bordercolor="#434951", lightcolor="#2796df", darkcolor="#2796df")
    return style
