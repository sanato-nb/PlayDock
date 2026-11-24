"""Test-only helpers for source structure checks after module separation.

Concatenate *actual* classes and functions from each source module; do not
replicate logic or substitute fake source strings. The parser omits import
statements so tests can safely parse the combined declarations.
"""
from pathlib import Path
import ast

ROOT = Path(__file__).resolve().parent / "src" / "playdock"

MAIN_MODULES = (
    "ui/launcher_layout.py", "ui/widgets/launcher.py",
    "ui/dialogs/common.py", "ui/dialogs/library.py",
    "services/workers.py",
    "controllers/library.py", "controllers/game_actions.py",
    "controllers/metadata.py", "controllers/window_actions.py",
)
EDITOR_MODULES = (
    "ui/editor_layout.py", "ui/dialogs/title.py",
    "services/title_workers.py", "controllers/title_editor.py",
)

def declared_source(filename: str) -> str:
    source = (ROOT / filename).read_text(encoding="utf-8")
    parsed = ast.parse(source)
    chunks = [ast.get_source_segment(source, node) for node in parsed.body
              if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef))]
    return "\n\n" + "\n\n".join(c for c in chunks if c) + "\n"

def launcher_source() -> str:
    return "\n".join(declared_source(name) for name in MAIN_MODULES)

def editor_source() -> str:
    return "\n".join(declared_source(name) for name in EDITOR_MODULES)
