"""Expose the reorganized code and release scripts to existing unit tests."""
from pathlib import Path
import sys
ROOT = Path(__file__).resolve().parents[1]
for folder in (ROOT / "src" / "playdock", ROOT / "scripts", ROOT):
    if str(folder) not in sys.path:
        sys.path.insert(0, str(folder))


def pytest_sessionfinish(session, exitstatus):
    """Dispose of test-owned Qt widgets while the application still exists."""
    if "PySide6.QtWidgets" not in sys.modules:
        return
    import gc
    from PySide6.QtCore import QCoreApplication, QEvent
    from PySide6.QtGui import QPixmapCache
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance()
    if not isinstance(app, QApplication):
        return
    # Test dialogs may be closed but still retain C++ resources until deferred
    # deletion. Flush them before Qt's native interpreter-shutdown cleanup.
    for widget in QApplication.topLevelWidgets():
        widget.deleteLater()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    QPixmapCache.clear()
    gc.collect()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
