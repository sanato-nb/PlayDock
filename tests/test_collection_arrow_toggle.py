"""Actual Qt pointer events: a collection arrow is not a navigation click."""
from time import perf_counter

import pytest
from PySide6.QtCore import Qt, QPoint
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
from core import Library


@pytest.mark.parametrize("game_count", [129, 1000])
def test_sidebar_arrow_only_toggles_existing_rows(tmp_path, monkeypatch, game_count):
    import app as launcher
    qt = QApplication.instance() or QApplication([])
    archives = tmp_path / "archives"
    archives.mkdir()
    installed = tmp_path / "installed"
    installed.mkdir()
    for i in range(game_count):
        (archives / f"Example {i:04}.zip").write_bytes(b"synthetic")
    library = Library(tmp_path / "data")
    library.change_archive_root(archives)
    library.change_root(installed)
    library.settings["first_run_complete"] = True
    library.save_settings()
    monkeypatch.setattr(launcher, "Library", lambda: library)
    window = launcher.MainWindow()
    try:
        assert len(window.games) == game_count
        selected = window.games[0]
        cid = window.collections.create("Test collection")
        window.collections.set_game_memberships(window.games[-1].id, {cid})
        window.expanded_groups.add(cid)
        window.reload(prefer_id=selected.id)
        window.resize(1280, 800)
        window.show()
        qt.processEvents()
        groups = {window.tree_identity(window.tree.topLevelItem(i))[1]:
                  window.tree.topLevelItem(i) for i in range(window.tree.topLevelItemCount())}
        unassigned = groups["__uncategorized__"]
        named = groups[cid]
        assert unassigned.childCount() == game_count - 1
        assert unassigned.isExpanded() and named.isExpanded()
        original_banner = window.banner.title
        original_item = window.selected_game_item
        before_count = window.tree.topLevelItemCount()
        calls = []
        def forbidden(label):
            def fail(*args, **kwargs):
                calls.append(label)
                pytest.fail("Arrow click triggered expensive operation: " + label)
            return fail
        with monkeypatch.context() as patch:
            for owner, names in (
                (window, ("populate_games", "reload", "present_game", "show_collection")),
                (window.collections_board, ("refresh", "show_collection", "set_data")),
                (library, ("scan", "title", "meta", "art_dir")),
                (window.collections, ("list",)),
            ):
                for name in names:
                    patch.setattr(owner, name, forbidden(name))
            elapsed = []
            for group in (unassigned, named):
                for expected in (False, True, False, True):
                    window.tree.scrollToItem(group)
                    qt.processEvents()
                    rect = window.tree.visualItemRect(group)
                    point = QPoint(rect.left()+12, rect.center().y())
                    start = perf_counter()
                    QTest.mouseClick(window.tree.viewport(), Qt.MouseButton.LeftButton, pos=point)
                    qt.processEvents()
                    elapsed.append((perf_counter()-start)*1000)
                    assert group.isExpanded() is expected
                    assert (window.tree_identity(group)[1] in window.expanded_groups) is expected
                    assert window.selected_id == selected.id
                    assert window.selected_game_item is original_item
                    assert window.main_stack.currentWidget() is window.scroll
                    assert window.banner.title == original_banner
                    assert window.tree.topLevelItemCount() == before_count
            assert not calls
            print(f"COLLECTION_ARROW {game_count} games max {max(elapsed):.1f} ms; zero refresh/scan/title/art calls")
        # Title clicks retain collection browsing but never toggle the tree.
        window.tree.scrollToItem(named)
        qt.processEvents()
        rect = window.tree.visualItemRect(named)
        expanded = named.isExpanded()
        QTest.mouseClick(window.tree.viewport(), Qt.MouseButton.LeftButton,
                         pos=QPoint(rect.left()+60, rect.center().y()))
        qt.processEvents()
        assert named.isExpanded() is expanded
        assert window.main_stack.currentWidget() is window.collections_board
        assert window.collections_board._active_collection == cid
        # While a collection is displayed, another arrow still must not navigate.
        window.tree.scrollToItem(unassigned)
        qt.processEvents()
        rect = window.tree.visualItemRect(unassigned)
        QTest.mouseClick(window.tree.viewport(), Qt.MouseButton.LeftButton,
                         pos=QPoint(rect.left()+12, rect.center().y()))
        qt.processEvents()
        assert not unassigned.isExpanded()
        assert window.collections_board._active_collection == cid
    finally:
        window.close()
