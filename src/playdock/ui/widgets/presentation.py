"""Shared progress and summary display without business state."""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel, QProgressBar


def progress_bar(maximum, *, initial=None):
    bar = QProgressBar()
    bar.setRange(0, maximum)
    if initial is not None:
        bar.setValue(initial)
    return bar


def summary_label(text=""):
    label = QLabel(text)
    label.setTextFormat(Qt.TextFormat.PlainText)
    label.setWordWrap(True)
    return label
