"""Settings pop-up and actual, read-only two-database diagnostics (fake data only)."""
from pathlib import Path
import sqlite3

import pytest
from PySide6.QtWidgets import QApplication, QWidget

from database.official_catalog import OfficialWorkCatalog
from database.work_repository import WorkDatabase
from experiments.dlsite_detector.code_only import Result, Work
from services.database_status_service import database_status, format_database_status
from ui.dialogs.database_status import DatabaseStatusDialog
from ui.widgets.launcher import ChevronMenuButton
from controllers.window_actions import WindowActionControllerMixin


@pytest.fixture
def app(monkeypatch):
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    existing = QApplication.instance()
    if existing is None:
        existing = QApplication([])
    yield existing


def scanner_with_two_stores(path):
    store = OfficialWorkCatalog(path)
    verified = [
        Result("RJ123456.zip", "archive", "confirmed", (
            Work("RJ123456", "검증된 DL 게임", "maniax",
                 "https://www.dlsite.com/maniax/work/=/product_id/RJ123456.html",
                 "verified", "dlsite"),), selected_store="dlsite"),
        Result("Steam 1091500.zip", "archive", "confirmed", (
            Work("1091500", "검증된 Steam 게임", "game",
                 "https://store.steampowered.com/app/1091500/",
                 "verified", "steam"),), selected_store="steam"),
    ]
    assert store.save_verified_results(verified) == 2
    return store


def test_db_status_read_only_and_missing_files_do_not_get_created(tmp_path):
    data = tmp_path / "playdock_data"
    source = tmp_path / "scanner.sqlite3"
    report = database_status(data, scanner_path=source)
    assert not report["main"]["ok"] and not report["scanner"]["ok"]
    assert report["main"]["error"] == report["scanner"]["error"] == "파일 없음"
    assert not data.exists() and not source.exists()
    summary = format_database_status(report, live_games=129)
    assert "현재 화면 라이브러리: 129개 게임" in summary
    assert "파일 없음" in summary


def test_db_status_distinguishes_app_db_and_independent_scanner_db(tmp_path):
    source = scanner_with_two_stores(tmp_path / "scanner.sqlite3")
    app_store = tmp_path / "appdata"
    db = WorkDatabase(app_store)
    before_scanner = source.path.read_bytes()
    result = database_status(app_store, scanner_path=source.path)
    assert result["main"]["version"] == 2
    assert result["main"]["counts"]["official_works"] == 0
    assert result["scanner"]["counts"]["official_works"] == 2
    assert result["scanner"]["by_store"] == {"dlsite": 1, "steam": 1}
    assert db.import_scanner_catalog(source.path) == 2
    after = database_status(app_store, scanner_path=source.path)
    assert after["main"]["counts"]["official_works"] == 2
    assert after["main"]["by_store"] == {"dlsite": 1, "steam": 1}
    assert after["main"]["counts"]["works"] == 0
    assert after["main"]["counts"]["library_links"] == 0
    assert source.path.read_bytes() == before_scanner
    message = format_database_status(after, live_games=129)
    assert "PlayDock 본체 DB" in message
    assert "정체 판독기 원본 DB" in message
    assert "SQLite 스키마 버전: 2" in message
    assert "공식 작품정보(official_works): 2건" in message
    assert "DLsite: 1건  /  Steam: 1건" in message
    assert "읽기 전용" in message


def test_db_status_gracefully_reports_corrupt_sqlite(tmp_path):
    source = tmp_path / "corrupt.sqlite3"
    source.write_bytes(b"not a SQLite file")
    report = database_status(tmp_path / "missing_app", scanner_path=source)
    assert not report["scanner"]["ok"]
    assert report["scanner"]["exists"]
    assert "읽기 실패" in report["scanner"]["error"]
    assert source.read_bytes() == b"not a SQLite file"


def test_topbar_contains_only_refresh_and_settings_after_navigation():
    path = Path(__file__).resolve().parents[1] / "src/playdock/ui/launcher_layout.py"
    source = path.read_text(encoding="utf-8")
    top = source.split("outer.addWidget(top)", 1)[0]
    assert 'self.action_button("새로고침", self.reload)' in top
    assert 'ChevronMenuButton("설정")' in top
    assert 'self.settings_menu_btn.clicked.connect(self.show_settings_menu)' in top
    for removed in ("이름 설정", "폴더 설정", "데이터 관리", "속성", "AI 설정"):
        assert f'self.action_button("{removed}"' not in top


def test_popup_collects_every_old_action_plus_read_only_db_status(app, monkeypatch):
    class FakeOwner(WindowActionControllerMixin, QWidget):
        pass
    owner = FakeOwner()
    owner.settings_menu_btn = ChevronMenuButton("설정", owner)
    calls = []
    methods = {
        "open_bulk_name_settings": "bulk",
        "folder_wizard": "folders",
        "data_manager_dialog": "data",
        "library_info_dialog": "properties",
        "settings_dialog": "ai",
        "show_database_status": "db",
    }
    for name, code in methods.items():
        setattr(owner, name, lambda code=code: calls.append(code))
    created = []
    owner.settings_menu_btn.present_popup = lambda menu, right_align=False: (
        created.append((menu, right_align)))
    owner.show_settings_menu()
    assert len(created) == 1 and created[0][1] is True
    actions = [action for action in created[0][0].actions() if not action.isSeparator()]
    assert [x.text() for x in actions] == [
        "이름 설정 (여러 게임)...",
        "폴더 설정...",
        "데이터 관리...",
        "라이브러리 속성...",
        "AI 설정...",
        "DB 상태 확인...",
    ]
    for action in actions:
        action.trigger()
    assert calls == ["bulk", "folders", "data", "properties", "ai", "db"]
    owner.close()


def test_status_dialog_displays_live_counts_without_creating_scanner_file(app, tmp_path):
    store = tmp_path / "data"
    WorkDatabase(store)
    path = tmp_path / "nonexisting-scanner.sqlite3"
    dialog = DatabaseStatusDialog(store, 129, scanner_path=path)
    try:
        content = dialog.details.toPlainText()
        assert "SQLite 스키마 버전: 2" in content
        assert "129개 게임" in content
        assert "정체 판독기 원본 DB" in content
        assert "파일 없음" in content
        assert not path.exists()
        scanner_with_two_stores(path)
        dialog.refresh_status()
        assert "공식 작품정보: 2건" in dialog.details.toPlainText()
    finally:
        dialog.close()
