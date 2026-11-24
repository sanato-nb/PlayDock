"""The v0.8.1 source move must keep entrypoints and UI links visible."""
from pathlib import Path
import ast

ROOT = Path(__file__).resolve().parents[1]


def test_gui_layouts_are_outside_launcher_and_editor():
    main = (ROOT / "app.py").read_text(encoding="utf-8")
    editor = (ROOT / "title_editor.py").read_text(encoding="utf-8")
    assert "from ui.launcher_layout import build_main_ui" in main
    assert "return build_main_ui(self," in main
    assert "from ui.editor_layout import build_title_editor_ui" in editor
    assert "return build_title_editor_ui(self)" in editor
    for file, name in (("launcher_layout.py", "build_main_ui"),
                       ("editor_layout.py", "build_title_editor_ui")):
        mod = ast.parse((ROOT / "ui" / file).read_text(encoding="utf-8"))
        assert any(isinstance(item, ast.FunctionDef) and item.name == name for item in mod.body)


def test_ui_package_keeps_legacy_imports_working():
    for old, new in (("online_art_dialog.py", "artwork_dialog"),
                     ("collection_board.py", "collection_board"),
                     ("work_db_dialog.py", "work_info_dialog"),
                     ("dark_selector.py", "selectors")):
        source = (ROOT / old).read_text(encoding="utf-8")
        assert f"from ui.{new} import " in source
        assert (ROOT / "ui" / f"{new}.py").is_file()


def test_qss_is_separate_and_ui_package_has_no_user_data():
    from ui.styles import MAIN_STYLESHEET, EDITOR_STYLESHEET
    assert "QFrame#Sidebar" in MAIN_STYLESHEET
    assert "QFrame#Panel" in EDITOR_STYLESHEET
    assert not (ROOT / "data").exists()
