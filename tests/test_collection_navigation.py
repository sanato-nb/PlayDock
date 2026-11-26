"""Collection overview and member navigation with actual Qt clicks."""
from PySide6.QtCore import Qt, QPoint
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
from core import Library


def test_collection_overview_includes_unassigned_and_opens_exact_members(tmp_path, monkeypatch):
    import app as launcher
    qt = QApplication.instance() or QApplication([])
    archives = tmp_path / "archives"
    archives.mkdir()
    installed = tmp_path / "installed"
    installed.mkdir()
    for name in ("Alpha", "Beta", "Gamma"):
        (archives / f"{name}.zip").write_bytes(b"synthetic")
    library = Library(tmp_path / "data")
    library.change_archive_root(archives)
    library.change_root(installed)
    library.settings["first_run_complete"] = True
    library.save_settings()
    monkeypatch.setattr(launcher, "Library", lambda: library)
    window = launcher.MainWindow()
    try:
        games = {g.name: g for g in window.games}
        a = window.collections.create("Group A")
        b = window.collections.create("Group B")
        window.collections.create("Empty group")
        window.collections.set_game_memberships(games["Alpha"].id, {a, b})
        window.collections.set_game_memberships(games["Beta"].id, {b})
        window.reload()
        window.resize(1280, 800)
        window.show()
        qt.processEvents()
        board = window.collections_board
        def cards():
            return {card.title: card for card in board._cards if hasattr(card, "title")}
        def click_card(name):
            card = cards()[name]
            board.ensureWidgetVisible(card)
            qt.processEvents()
            QTest.mouseClick(card, Qt.MouseButton.LeftButton)
            qt.processEvents()
        def overview():
            QTest.mouseClick(window.collections_nav_btn, Qt.MouseButton.LeftButton)
            qt.processEvents()
            assert window.main_stack.currentWidget() is board
            assert board._active_collection is None
            assert board.heading.text() == "내 모음집"
            assert set(cards()) == {"새 모음집 만들기", "Group A", "Group B", "Empty group", "미분류"}
            assert board.count.text() == "4개 모음집"
            assert cards()["미분류"].count == "1개 게임"
            assert cards()["Group A"].count == "1개 게임"
            assert cards()["Group B"].count == "2개 게임"
            assert cards()["Empty group"].count == "0개 게임"

        overview()
        click_card("미분류")
        assert board._active_collection == "__uncategorized__"
        assert board.heading.text() == "미분류"
        assert set(cards()) == {"Gamma"}
        QTest.mouseClick(board.back, Qt.MouseButton.LeftButton)
        qt.processEvents()
        assert board._active_collection is None
        assert "미분류" in cards()

        click_card("Group A")
        assert board._active_collection == a and set(cards()) == {"Alpha"}
        # The top navigation must always reset to the collection overview,
        # without first rendering the previous member grid.
        refresh = board.refresh
        visits = []
        def counted_refresh():
            visits.append(board._active_collection)
            return refresh()
        with monkeypatch.context() as patch:
            patch.setattr(board, "refresh", counted_refresh)
            overview()
            assert visits == [None]

        click_card("Group B")
        assert board._active_collection == b and set(cards()) == {"Alpha", "Beta"}
        click_card("Beta")
        assert window.main_stack.currentWidget() is window.scroll
        assert window.selected_id == games["Beta"].id
        overview()
        click_card("Empty group")
        assert not cards() and board.count.text() == "0개 게임"

        # Sidebar group name opens the same member grid, not the overview.
        for cid, expected in (("__uncategorized__", {"Gamma"}), (a, {"Alpha"})):
            group = next(window.tree.topLevelItem(i) for i in range(window.tree.topLevelItemCount())
                         if window.tree_identity(window.tree.topLevelItem(i))[1] == cid)
            window.tree.scrollToItem(group)
            qt.processEvents()
            rect = window.tree.visualItemRect(group)
            was_expanded = group.isExpanded()
            QTest.mouseClick(window.tree.viewport(), Qt.MouseButton.LeftButton,
                             pos=QPoint(rect.left()+60, rect.center().y()))
            qt.processEvents()
            assert board._active_collection == cid and set(cards()) == expected
            assert group.isExpanded() == was_expanded

        window.collections.set_game_memberships(games["Gamma"].id, {a})
        window.reload()
        QTest.mouseClick(window.collections_nav_btn, Qt.MouseButton.LeftButton)
        qt.processEvents()
        assert cards()["미분류"].count == "0개 게임"
        click_card("미분류")
        assert board._active_collection == "__uncategorized__"
        assert not cards() and board.count.text() == "0개 게임"
        assert all(p.read_bytes() == b"synthetic" for p in archives.glob("*.zip"))
    finally:
        window.close()
