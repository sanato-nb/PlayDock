"""The standard launcher no longer eagerly imports the legacy title window."""
import os
from pathlib import Path
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[2]

def test_legacy_editor_not_loaded_at_main_import():
    code = """
import sys
import app
assert 'title_editor' not in sys.modules
assert 'controllers.title_editor' not in sys.modules
assert 'ui.editor_layout' not in sys.modules
from ui.dialogs.title import BulkTitleSettingsDialog
assert 'title_editor' not in sys.modules
from title_editor import TitleEditor
assert 'controllers.title_editor' in sys.modules
print('LEGACY_EDITOR_ON_DEMAND_VERIFIED')
"""
    result=subprocess.run([sys.executable,"-c",code],cwd=ROOT,
                          env={**os.environ,"QT_QPA_PLATFORM":"offscreen"},
                          capture_output=True,text=True,encoding="utf-8",timeout=30)
    assert result.returncode==0, result.stdout+result.stderr
    assert "LEGACY_EDITOR_ON_DEMAND_VERIFIED" in result.stdout

def test_runtime_requirements_use_qt_essentials():
    requirements=(ROOT/"requirements.txt").read_text(encoding="utf-8")
    assert "PySide6-Essentials>=6.7,<7" in requirements
    assert not any(line.startswith("PySide6>") for line in requirements.splitlines())
