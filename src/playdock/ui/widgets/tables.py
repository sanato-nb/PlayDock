"""Common review table style; column layout stays local."""
from PySide6.QtWidgets import QAbstractItemView, QHeaderView


def configure_review_table(table, *, fixed_rows=False, row_selection=False):
    style = "QTableWidget { alternate-background-color:#1c2b39; gridline-color:#304253; }"
    if row_selection:
        style += "QTableWidget::item:selected { background:#31526b; color:#fff; }"
    header = "QHeaderView::section { background:#25394a; color:#e2edf6; padding:5px;"
    style += header + (" border:1px solid #344b60; }" if row_selection else " }")
    table.setStyleSheet(style)
    table.setAlternatingRowColors(True)
    if row_selection:
        table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
    table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
    vertical = table.verticalHeader()
    vertical.hide()
    if fixed_rows:
        vertical.setSectionResizeMode(QHeaderView.ResizeMode.Fixed)
    vertical.setDefaultSectionSize(44)
