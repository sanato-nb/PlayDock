"""Stage 9: isolated Windows source runtime measurements, no EXE build."""
from pathlib import Path
from collections import Counter
from contextlib import contextmanager
from io import BytesIO
import argparse
import gc
import hashlib
import json
import os
import platform
import statistics
import subprocess
import sys
import tempfile
import time
import zipfile


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", type=Path, required=True)
    ap.add_argument("--output", type=Path, required=True)
    ap.add_argument("--count", type=int, default=100)
    ap.add_argument("--ui-only", action="store_true")
    ap.add_argument("--endurance", type=int, default=0)
    a = ap.parse_args()
    source = a.source.resolve()
    out = a.output.resolve()
    out.parent.mkdir(parents=True, exist_ok=True)
    sys.path[:0] = [str(source / "src/playdock"), str(source)]
    start_import = time.perf_counter()
    import psutil
    from PySide6.QtCore import QCoreApplication, QEvent, QTimer, QSize, qVersion
    from PySide6.QtGui import QPixmapCache
    from PySide6.QtWidgets import QApplication, QDialog
    from core import Game, Library
    from work_db import WorkDatabase
    from services.bulk_title_service import BulkTitleActions
    from ui.dialogs.common import TextEntryDialog
    from ui.widgets.launcher import collection_chevron
    from PIL import Image
    import artwork
    import app as launcher
    import_ms = (time.perf_counter() - start_import) * 1000
    qt = QApplication([])
    qt.setStyle("Fusion")
    qt.setStyleSheet(launcher.STYLESHEET)
    process = psutil.Process()
    report = {"commit": subprocess.check_output(["git", "-C", str(source), "rev-parse", "HEAD"], text=True).strip(),
              "python": sys.version.split()[0], "qt": qVersion(), "os": platform.platform(),
              "platform": qt.platformName(), "count": a.count, "import_ms": import_ms,
              "scale": os.environ.get("QT_SCALE_FACTOR", "1"),
              "cpu_logical": psutil.cpu_count(), "ram_mb": psutil.virtual_memory().total / 2**20,
              "measurements": {}, "screens": []}

    def rss():
        return process.memory_info().rss / 2**20

    def cpu():
        t = process.cpu_times()
        return t.user + t.system

    def digest(value):
        return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True).encode()).hexdigest()

    def measure(name, fn, signature, setup=lambda: None, repeats=3):
        samples, cpu_samples, memory = [], [], []
        expected = None
        for _ in range(repeats):
            setup()
            qt.processEvents()
            c0, t0 = cpu(), time.perf_counter()
            value = fn()
            qt.processEvents()
            samples.append((time.perf_counter() - t0) * 1000)
            cpu_samples.append((cpu() - c0) * 1000)
            memory.append(rss())
            sig = signature(value)
            if expected is None:
                expected = sig
            else:
                assert sig == expected, name
        report["measurements"][name] = {"median_ms": statistics.median(samples),
            "samples_ms": samples, "cpu_ms": cpu_samples, "rss_mb": memory,
            "digest": digest(expected)}

    with tempfile.TemporaryDirectory(prefix="playdock-stage9-") as directory:
        root = Path(directory)
        archives = root / "archives"; archives.mkdir()
        installed = root / "installed"; installed.mkdir()
        lib = Library(root / "data")
        lib.change_root(installed); lib.change_archive_root(archives)
        lib.settings["first_run_complete"] = True
        lib.save_settings()
        buffer = BytesIO()
        with zipfile.ZipFile(buffer, "w") as z:
            z.writestr("README.txt", "synthetic fixture; no real game")
        payload = buffer.getvalue()
        for i in range(a.count):
            name = f"Stage9 Game {i:05}"
            (archives / (name + ".zip")).write_bytes(payload)
            if i >= a.count - max(1, a.count // 10):
                folder = installed / name; folder.mkdir()
                (folder / "Game.exe").write_bytes(b"MZ synthetic fixture, never executed")
        games = lib.scan()
        assert len(games) == a.count
        ids = [g.id for g in games]
        for game in games[::5]:
            lib.update_meta(game, title=game.name, prefer_manual_title=True)
        from core import save_json
        save_json(lib.store / "collections.json", {"version": 1, "collections": [
            {"id": "sample-a", "name": "Sample A", "game_ids": ids[::2]},
            {"id": "sample-b", "name": "Sample B", "game_ids": ids[::3]}]})
        db = WorkDatabase(lib.store)
        db._upsert_verified([{"store": "dlsite", "code": "RJ123456", "title": "Synthetic official",
                             "page_url": "https://www.dlsite.com/maniax/work/=/product_id/RJ123456.html"}])
        with db.connect() as con:
            con.executemany("INSERT INTO library_links(game_id,store,code) VALUES(?,?,?)",
                            [(gid, "dlsite", "RJ123456") for gid in ids[::20]])
        launcher.Library = lambda: lib
        before = rss(); start = time.perf_counter()
        window = launcher.MainWindow()
        window.show(); qt.processEvents()
        report["startup_window_ms"] = (time.perf_counter()-start)*1000
        report["rss_before_window_mb"] = before
        report["rss_after_window_mb"] = rss()
        assert len(window.games) == a.count

        def tree_signature(_=None):
            rows = []
            for i in range(window.tree.topLevelItemCount()):
                group = window.tree.topLevelItem(i)
                rows.append((window.tree_identity(group)[1], group.text(0),
                             [group.child(j).text(0) for j in range(group.childCount())]))
            return rows

        def select(index):
            window.populate_games(window.games[index].id)
            return window.current().name

        def detail(index):
            window.selected_id = window.games[index].id
            window.selected_game_item = None
            window.present_game()
            return window.current().name

        if not a.ui_only:
            repeats = 2 if a.count >= 5000 else 3
            measure("reload", window.reload, tree_signature, repeats=repeats)
            measure("search", lambda: window.search.setText("Stage9 Game 0000"), tree_signature,
                    setup=lambda: window.search.clear(), repeats=repeats)
            window.search.clear()
            measure("sort_desc", lambda: window.change_sort("name_desc"), tree_signature,
                    setup=lambda: window.change_sort("name"), repeats=repeats)
            window.change_sort("name")
            measure("detail", lambda: detail(0), lambda name: name, repeats=repeats)
            measure("collections", window.show_collections_overview,
                    lambda _: window.main_stack.currentWidget() is window.collections_board,
                    setup=window.show_all_games, repeats=repeats)
            window.show_all_games()
            measure("bulk_name_preview", lambda: BulkTitleActions(lib).preview_changes(games, "manual"),
                    lambda rows: [(r.expected_name, r.proposed_name) for r in rows], repeats=repeats)
            # Count one selected-game rendering without an on-disk cache persisting between runs.
            counts = Counter()
            original_meta = lib.meta
            original_connect = window.work_db.connect
            def counted_meta(game):
                counts["meta_reads"] += 1
                return original_meta(game)
            @contextmanager
            def counted_connect():
                counts["db_connections"] += 1
                with original_connect() as con:
                    yield con
            lib.meta = counted_meta
            window.work_db.connect = counted_connect
            try:
                detail(0)
            finally:
                lib.meta = original_meta
                window.work_db.connect = original_connect
            report["detail_operation_counts"] = dict(counts)

            image_folder = root / "image-fixture"; image_folder.mkdir()
            Image.new("RGB", (800, 400), "red").save(image_folder / "banner.png")
            Image.new("RGB", (128, 128), "blue").save(image_folder / "icon.png")
            image_game = Game("image-fixture", "Image fixture", installed, folder=image_folder)
            dest = lib.art_dir(image_game)
            def clear_art():
                for name in ("hero.png", "icon.png"):
                    (dest / name).unlink(missing_ok=True)
            measure("local_artwork", lambda: artwork.discover_local(lib, image_game),
                    lambda rows: rows, setup=clear_art, repeats=repeats)
            assert (dest / "hero.png").is_file() and (dest / "icon.png").is_file()

        window.show_all_games()
        for width, height in ((950,620), (1280,720), (1920,1080)) if a.ui_only else ((1380,840),):
            window.resize(width, height)
            qt.processEvents()
            pic = window.grab()
            assert not pic.isNull()
            assert window.tree.width() > 0 and window.main_button.width() > 0
            png = out.parent / f"{out.stem}-{width}x{height}.png"
            assert pic.save(str(png))
            report["screens"].append({"requested": [width,height], "window": [window.width(),window.height()],
                                      "captured": [pic.width(),pic.height()], "dpr": pic.devicePixelRatio()})
        # Real event dispatch through the existing button and modal dialog.
        window.settings_menu_btn.click()
        qt.processEvents()
        menu = window.settings_menu_btn._popup_menu
        assert menu is not None and menu.isVisible()
        report["settings_menu"] = [x.text() for x in menu.actions() if not x.isSeparator()]
        expected_settings = ["폴더 설정", "데이터 관리", "라이브러리 속성", "DB 상태 확인"]
        if report["commit"] != "86635400e4c925ddfd63e144112214eaaf27f50b":
            expected_settings.append("개발자 후원 버튼 표시")
            assert menu.actions()[-1].isCheckable() and menu.actions()[-1].isChecked()
        assert report["settings_menu"] == expected_settings
        support = getattr(window, "support_btn", None)
        report["support_button"] = None
        if report["commit"] != "86635400e4c925ddfd63e144112214eaaf27f50b":
            assert support is not None and support.isVisible() and support.isEnabled()
            assert support.text() == "개발자 후원"
            assert support.geometry().right() < window.settings_menu_btn.geometry().left()
            assert support.geometry().right() < support.parentWidget().width()
            report["support_button"] = support.text()
        menu.close(); qt.processEvents()
        dialog = TextEntryDialog("Stage 9", "Synthetic input", window)
        QTimer.singleShot(20, dialog.reject)
        assert dialog.exec() == QDialog.DialogCode.Rejected
        dialog.deleteLater()
        if a.endurance:
            samples = []; started = time.perf_counter(); count = 0
            while time.perf_counter() - started < a.endurance:
                window.search.setText("Stage9 Game 0000")
                window.search.clear()
                window.change_sort("name_desc" if count % 2 else "name")
                expected_name = window.games[count % a.count].name
                assert select(count % a.count) == expected_name
                qt.processEvents()
                samples.append(rss()); count += 1
            report["endurance"] = {"seconds": time.perf_counter() - started, "cycles": count,
                                   "rss_start_mb": samples[0], "rss_end_mb": samples[-1],
                                   "rss_max_sample_mb": max(samples)}
        report["rss_before_close_mb"] = rss()
        QTimer.singleShot(50, window.close)
        QTimer.singleShot(5000, qt.quit)
        assert qt.exec() == 0
        assert not window.isVisible()
        report["event_loop_closed"] = True
        window.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        if hasattr(collection_chevron, "cache_clear"):
            collection_chevron.cache_clear()
        QPixmapCache.clear()
        gc.collect()
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print("STAGE9_RUNTIME", json.dumps(report, ensure_ascii=False))


if __name__ == "__main__":
    main()
