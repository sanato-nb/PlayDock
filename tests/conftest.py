"""Expose the reorganized code and release scripts to existing unit tests."""
from pathlib import Path
import sys
ROOT = Path(__file__).resolve().parents[1]
for folder in (ROOT / "src" / "playdock", ROOT / "scripts", ROOT):
    if str(folder) not in sys.path:
        sys.path.insert(0, str(folder))
