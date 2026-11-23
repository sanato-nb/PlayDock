"""Single shared SQLite diagnostics and compact top-right settings pop-up."""
from pathlib import Path
import sqlite3

import pytest
from PySide6.QtWidgets import QApplication, QWidget

from database.work_repository import WorkDatabase
from services.database_status_service import database_status, format_database_status
from ui.dialogs.database_status import DatabaseStatusDialog
from ui.widgets.launcher import ChevronMenuButton
from controllers.window_actions import WindowActionControllerMixin


@pytest.fixture
def app(monkeypatch):
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    instance = QApplication.instance() or QApplication([])
    yield instance


def test_db_status_read_only_missing_db_does_not_get_created(tmp_path):
    store = tmp_path / "data"
    info = database_status(store)
    assert not info["main"]["ok"]
    assert info["main"]["error"] == "파일 없음"
    assert "scanner" not in info
    assert not store.exists()
    summary = format_database_status(info, live_games=129)
    assert "현재 화면 라이브러리: 129개 게임" in summary
    assert "파일 없음" in summary


def test_status_reports_real_store_counts_and_schema_v3(tmp_path):
    data = tmp_path / "data"
    db = WorkDatabase(data)
    report = database_status(data)
    assert report["main"]["version"] == 3
    assert report["main"]["counts"] == {"works": 0, "library_links": 0}
    assert report["main"]["by_store"] == {}
    db._upsert_verified([
        {"store":"dlsite","code":"RJ123456","title":"DL",
         "category":"maniax","page_url":
         "https://www.dlsite.com/maniax/work/=/product_id/RJ123456.html"},
        {"store":"steam","code":"1091500","title":"Steam",
         "category":"game","page_url":"https://store.steampowered.com/app/1091500/"},
    ])
    info = database_status(data)
    assert info["main"]["counts"]["works"] == 2
    assert info["main"]["by_store"] == {"dlsite": 1, "steam": 1}
    output = format_database_status(info, live_games=129)
    assert "통합 PlayDock DB" in output
    assert "SQLite 스키마 버전: 3" in output
    assert "공식 작품정보(works): 2건" in output
    assert "DLsite: 1건" in output and "Steam: 1건" in output
    assert "읽기 전용" in output


def test_corrupt_single_sqlite_reported_without_changing_file(tmp_path):
    root = tmp_path / "data"
    root.mkdir()
    path = root / "playdock.db"
    path.write_bytes(b"not a SQLite file")
    report = database_status(root)
    assert not report["main"]["ok"]
    assert report["main"]["exists"]
    assert "읽기 실패" in report["main"]["error"]
    assert path.read_bytes() == b"not a SQLite file"


def test_topbar_contains_only_refresh_and_settings_after_navigation():
    source = (Path(__file__).resolve().parents[1] /
              "src/playdock/ui/launcher_layout.py").read_text(encoding="utf-8")
    top = source.split("outer.addWidget(top)", 1)[0]
    assert 'self.action_button("새로고침", self.reload)' in top
    assert 'ChevronMenuButton("설정")' in top
    assert 'self.settings_menu_btn.clicked.connect(self.show_settings_menu)' in top
    for removed in ("이름 설정", "폴더 설정", "데이터 관리", "속성", "AI 설정"):
        assert f'self.action_button("{removed}"' not in top


def test_popup_preserves_all_actions_and_database_status(app):
    class Dummy(WindowActionControllerMixin, QWidget):
        pass
    owner = Dummy()
    owner.settings_menu_btn = ChevronMenuButton("설정", owner)
    invoked = []
    paths = {
        "folder_wizard": "folders",
        "data_manager_dialog": "data",
        "library_info_dialog": "properties",
        "settings_dialog": "ai",
        "show_database_status": "db",
    }
    for method, tag in paths.items():
        setattr(owner, method, lambda tag=tag: invoked.append(tag))
    shown = []
    owner.settings_menu_btn.present_popup = lambda menu, right_align=False: shown.append(
        (menu, right_align))
    owner.show_settings_menu()
    assert shown[0][1]
    actions = [x for x in shown[0][0].actions() if not x.isSeparator()]
    assert [x.text() for x in actions] == [
        "폴더 설정...", "데이터 관리...", "라이브러리 속성...",
        "AI 설정...", "DB 상태 확인...",
    ]
    for action in actions:
        action.trigger()
    assert invoked == ["folders", "data", "properties", "ai", "db"]
    owner.close()


def test_status_dialog_displays_one_db_and_can_refresh(app, tmp_path):
    store = tmp_path / "data"
    db = WorkDatabase(store)
    dialog = DatabaseStatusDialog(store, 129)
    try:
        assert "SQLite 스키마 버전: 3" in dialog.details.toPlainText()
        assert "129개 게임" in dialog.details.toPlainText()
        assert "정체 판독기 원본 DB" not in dialog.details.toPlainText()
        db._upsert_verified([{
            "store":"steam","code":"1091500","title":"Example",
            "page_url":"https://store.steampowered.com/app/1091500/",
        }])
        dialog.refresh_status()
        assert "공식 작품정보(works): 1건" in dialog.details.toPlainText()
    finally:
        dialog.close()
