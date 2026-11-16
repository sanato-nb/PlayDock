"""실제 PlayDock PySide6 위젯을 Qt 오프스크린으로 캡처한다.

개인 게임 폴더와 사용자 설정을 열지 않도록 임시 LOCALAPPDATA만 사용한다.
이 파일은 원본 UI를 재구현하지 않는다.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import tempfile
from zipfile import ZipFile


def capture(widget, destination: Path, application):
    application.processEvents()
    pixmap = widget.grab()
    if pixmap.isNull() or pixmap.width() < 100 or pixmap.height() < 100:
        raise RuntimeError(f"UI 캡처 실패: {destination.name}")
    if not pixmap.save(str(destination), "PNG"):
        raise RuntimeError(f"PNG 저장 실패: {destination.name}")
    print(f"CAPTURE_OK {destination} {pixmap.width()}x{pixmap.height()} {destination.stat().st_size} bytes", flush=True)


def main():
    output = Path("ui-preview-output")
    output.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="playdock-qt-preview-") as working:
        root = Path(working)
        appdata = root / "appdata"
        game_root = root / "installed"
        archive_root = root / "archives"
        for directory in (appdata, game_root, archive_root):
            directory.mkdir(parents=True, exist_ok=True)
        os.environ["LOCALAPPDATA"] = str(appdata)
        os.environ["XDG_DATA_HOME"] = str(root / "xdg-data")
        os.environ["XDG_CONFIG_HOME"] = str(root / "xdg-config")
        os.environ["PYTHON_KEYRING_BACKEND"] = "keyring.backends.null.Keyring"

        # 실제로 스캔되는 임시 테스트 ZIP. 개인 게임·경로·API 키는 불러오지 않는다.
        for title in ("샘플 RPG", "샘플 어드벤처", "샘플 퍼즐"):
            with ZipFile(archive_root / f"{title}.zip", "w") as bundle:
                bundle.writestr("readme.txt", "PlayDock UI rendering fixture only.")
        settings_path = appdata / "PlayDock" / "settings.json"
        settings_path.parent.mkdir(parents=True, exist_ok=True)
        settings_path.write_text(json.dumps({
            "first_run_complete": True,
            "library": str(game_root),
            "archives": str(archive_root),
            "auto_art": False,
            "title_language": "ko",
        }, ensure_ascii=False), encoding="utf-8")

        from PySide6.QtWidgets import QApplication
        from app import MainWindow, STYLESHEET
        from ui.dialogs.library import SettingsDialog

        application = QApplication([])
        application.setStyle("Fusion")
        application.setStyleSheet(STYLESHEET)
        window = MainWindow()
        window.resize(1380, 840)
        window.show()
        capture(window, output / "01-main-library.png", application)

        window.show_collections_overview()
        capture(window, output / "02-collections.png", application)

        window.show_all_games()
        dialog = SettingsDialog(window.library, window)
        dialog.show()
        capture(dialog, output / "03-ai-settings.png", application)
        dialog.close()
        window.close()
        print("실제 PySide6 위젯으로 캡처 완료. 개인 데이터 없음.", flush=True)


if __name__ == "__main__":
    main()
