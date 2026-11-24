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
        mod = ast.parse((ROOT / "src/playdock/ui" / file).read_text(encoding="utf-8"))
        assert any(isinstance(item, ast.FunctionDef) and item.name == name for item in mod.body)


def test_canonical_ui_imports_and_retired_compatibility_paths():
    from ui.collection_board import ArtworkTile, CollectionBoard
    from ui.selectors import DarkMenuSelect
    from ui.work_info_dialog import WorkPreviewDialog
    assert all((ArtworkTile, CollectionBoard, DarkMenuSelect, WorkPreviewDialog))
    for old in ("online_art_dialog.py", "collection_board.py",
                "work_db_dialog.py", "dark_selector.py", "ui/artwork_dialog.py",
                "services/artwork_workers.py"):
        assert not (ROOT / "src/playdock" / old).exists(), old


def test_qss_is_separate_and_ui_package_has_no_user_data():
    from ui.styles import MAIN_STYLESHEET, EDITOR_STYLESHEET
    assert "QFrame#Sidebar" in MAIN_STYLESHEET
    assert "QFrame#Panel" in EDITOR_STYLESHEET
    assert not (ROOT / "data").exists()
