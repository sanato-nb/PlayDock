"""Common UI improvements without changes to main layout or game data."""
from pathlib import Path
from PySide6.QtCore import QStandardPaths, QUrl, QEvent, Qt
from PySide6.QtWidgets import QApplication, QWidget
from ui.dialogs.caption import DarkCaptionEventFilter, DarkDialogCaptionFilter
from ui.dialogs.file_dialog import PlayDockFileDialog, standard_sidebar_urls


def test_known_sidebar_paths_and_redirected_downloads(monkeypatch,tmp_path):
    locations = QStandardPaths.StandardLocation
    desktop=tmp_path/"Desktop";desktop.mkdir()
    downloads=tmp_path/"Redirected"/"Downloads";downloads.mkdir(parents=True)
    home=tmp_path/"Home";home.mkdir()
    paths={locations.DesktopLocation:str(desktop),locations.DownloadLocation:str(downloads),
           locations.DocumentsLocation:str(desktop),locations.HomeLocation:str(home)}
    monkeypatch.setattr(QStandardPaths,"writableLocation",lambda loc:paths.get(loc,str(tmp_path/"missing")))
    urls=standard_sidebar_urls([QUrl.fromLocalFile(str(home))])
    assert [Path(u.toLocalFile()) for u in urls]==[desktop,downloads,home]


def test_file_dialog_adds_shortcuts_without_changing_selected_file(monkeypatch,tmp_path):
    monkeypatch.setenv("QT_QPA_PLATFORM","offscreen")
    app=QApplication.instance() or QApplication([])
    download=tmp_path/"Downloads";download.mkdir()
    locations=QStandardPaths.StandardLocation
    monkeypatch.setattr(QStandardPaths,"writableLocation",lambda loc:str(download) if loc==locations.DownloadLocation else "")
    path=tmp_path/"fixture.json";path.write_text("{}")
    dialog=PlayDockFileDialog(None,"JSON 선택",str(tmp_path),"JSON (*.json)")
    try:
        assert QUrl.fromLocalFile(str(download)) in dialog.sidebarUrls()
        assert dialog.nameFilters()==["JSON (*.json)"]
        dialog.selectFile(str(path))
        assert Path(dialog.selectedFiles()[0])==path
        assert dialog.windowFlags() & Qt.WindowType.FramelessWindowHint
    finally:
        dialog.close()


def test_global_tooltip_filter_preserves_other_events(monkeypatch):
    monkeypatch.setenv("QT_QPA_PLATFORM","offscreen")
    app=QApplication.instance() or QApplication([])
    widget=QWidget()
    for cls in (DarkCaptionEventFilter,DarkDialogCaptionFilter):
        f=cls()
        assert f.eventFilter(widget,QEvent(QEvent.Type.ToolTip))
        assert not f.eventFilter(widget,QEvent(QEvent.Type.Enter))
