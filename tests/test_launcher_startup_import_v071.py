"""Prevent the missing load_json import from crashing MainWindow.reload()."""
import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_launcher_imports_load_json_from_core():
    tree = ast.parse((ROOT / "controllers/library.py").read_text(encoding="utf-8"))
    assert any(
        isinstance(node, ast.ImportFrom)
        and node.module == "core"
        and any(alias.name == "load_json" for alias in node.names)
        for node in tree.body
    ), "library controller must import load_json before reload uses it"


def test_launcher_reload_uses_imported_load_json():
    tree = ast.parse((ROOT / "controllers/library.py").read_text(encoding="utf-8"))
    classes = [n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "LibraryControllerMixin"]
    assert len(classes) == 1
    reloads = [n for n in classes[0].body if isinstance(n, ast.FunctionDef) and n.name == "reload"]
    assert len(reloads) == 1
    calls = [n for n in ast.walk(reloads[0]) if isinstance(n, ast.Call)]
    assert any(isinstance(c.func, ast.Name) and c.func.id == "load_json" for c in calls)


def test_core_exports_load_json():
    import sys
    sys.path.insert(0, str(ROOT))
    from core import load_json
    assert callable(load_json)
