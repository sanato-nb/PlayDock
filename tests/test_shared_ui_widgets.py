"""Shared UI components and existing selection contracts."""
import pytest
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QPushButton, QTableWidget, QTableWidgetItem, QAbstractItemView, QHeaderView
from ui.widgets.table_checks import StatusCheckDelegate, CandidateCheckDelegate
from ui.widgets.tables import configure_review_table
from ui.widgets.buttons import configure_action_button
from ui.widgets.presentation import progress_bar, summary_label
from ui.dialogs.identity_import import CandidateCheckDelegate as LegacyCandidate


@pytest.fixture
def qapp(monkeypatch):
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    return QApplication.instance() or QApplication([])


@pytest.mark.parametrize("delegate", [StatusCheckDelegate, CandidateCheckDelegate])
def test_shared_check_selection(qapp, delegate):
    table = QTableWidget(2, 1)
    table.setItemDelegateForColumn(0, delegate(table))
    item = QTableWidgetItem("보유" if delegate is StatusCheckDelegate else "")
    item.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsUserCheckable)
    item.setCheckState(Qt.CheckState.Unchecked)
    table.setItem(0, 0, item)
    unavailable = QTableWidgetItem("후보 없음")
    unavailable.setFlags(Qt.ItemFlag.NoItemFlags)
    table.setItem(1, 0, unavailable)
    try:
        table.show()
        qapp.processEvents()
        QTest.mouseClick(table.viewport(), Qt.MouseButton.LeftButton, pos=table.visualItemRect(item).center())
        assert item.checkState() == Qt.CheckState.Checked
        table.setCurrentCell(0, 0)
        table.setFocus()
        QTest.keyClick(table, Qt.Key.Key_Space)
        assert item.checkState() == Qt.CheckState.Unchecked
        QTest.mouseClick(table.viewport(), Qt.MouseButton.LeftButton, pos=table.visualItemRect(unavailable).center())
        assert unavailable.data(Qt.ItemDataRole.CheckStateRole) is None
        assert LegacyCandidate is CandidateCheckDelegate
    finally:
        table.close()


def test_shared_review_style_keeps_selection_modes(qapp):
    bulk, candidate = QTableWidget(1, 2), QTableWidget(1, 2)
    original = (bulk.selectionBehavior(), bulk.selectionMode())
    configure_review_table(bulk)
    configure_review_table(candidate, fixed_rows=True, row_selection=True)
    assert (bulk.selectionBehavior(), bulk.selectionMode()) == original
    assert candidate.selectionBehavior() == QAbstractItemView.SelectionBehavior.SelectRows
    assert candidate.selectionMode() == QAbstractItemView.SelectionMode.SingleSelection
    assert candidate.verticalHeader().sectionResizeMode(0) == QHeaderView.ResizeMode.Fixed
    for table in (bulk, candidate):
        assert table.rowHeight(0) == 44
        assert table.alternatingRowColors()
        assert table.editTriggers() == QAbstractItemView.EditTrigger.NoEditTriggers


def test_shared_button_progress_summary(qapp):
    button = QPushButton("적용")
    configure_action_button(button, "Blue")
    assert button.objectName() == "Blue" and button.isEnabled()
    button.setEnabled(False)
    assert "#Blue:disabled" in button.styleSheet() and not button.isEnabled()
    bar = progress_bar(8, initial=0)
    bar.setValue(3)
    assert (bar.minimum(), bar.maximum(), bar.value()) == (0, 8, 3)
    label = summary_label("<b>원본 텍스트</b>")
    assert label.wordWrap() and label.textFormat() == Qt.TextFormat.PlainText
    assert label.text() == "<b>원본 텍스트</b>"
