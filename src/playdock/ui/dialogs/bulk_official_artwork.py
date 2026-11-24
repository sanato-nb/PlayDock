"""Whole-library official artwork selection; no downloads or writes before approval."""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog, QLabel, QVBoxLayout, QHBoxLayout, QPushButton, QTableWidget,
    QTableWidgetItem, QHeaderView, QProgressBar,
)


class BulkOfficialArtworkDialog(QDialog):
    def __init__(self, rows, parent=None):
        super().__init__(parent)
        self.rows = list(rows)
        self.setWindowTitle("공식 배너·아이콘 적용 (여러 게임)")
        self.resize(850, 560)
        layout = QVBoxLayout(self)
        heading = QLabel(f"전체 라이브러리 · 공식 이미지 후보 {len(self.rows)}개 게임")
        heading.setObjectName("Heading")
        layout.addWidget(heading)
        hint = QLabel("적용할 게임별 배너·아이콘을 체크하세요. 기존 이미지는 기본적으로 유지됩니다.\n"
                      "비어 있는 이미지만 일괄 선택하거나, 기존 이미지도 직접 선택해 교체할 수 있습니다.")
        hint.setWordWrap(True)
        layout.addWidget(hint)
        self.table = QTableWidget(len(self.rows), 4)
        self.table.setHorizontalHeaderLabels(["게임", "공식 품번", "배너", "아이콘"])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.table.setColumnWidth(1, 140)
        self.table.setColumnWidth(2, 120)
        self.table.setColumnWidth(3, 120)
        for i, (game, record, kinds, existing) in enumerate(self.rows):
            for col, value in enumerate((game.name, f'{record["store"].upper()} {record["code"]}')):
                item = QTableWidgetItem(value)
                item.setFlags(Qt.ItemFlag.ItemIsEnabled)
                self.table.setItem(i, col, item)
            for col, kind in ((2,"hero"),(3,"icon")):
                item = QTableWidgetItem("후보 없음" if kind not in kinds else
                                        "기존 이미지 있음" if kind in existing else "이미지 없음")
                item.setFlags((Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsUserCheckable)
                              if kind in kinds else Qt.ItemFlag.NoItemFlags)
                if kind in kinds:
                    item.setCheckState(Qt.CheckState.Unchecked)
                self.table.setItem(i, col, item)
        layout.addWidget(self.table, 1)
        buttons = QHBoxLayout()
        missing = QPushButton("빈 이미지 전체 선택")
        missing.clicked.connect(self.select_missing)
        buttons.addWidget(missing)
        all_images = QPushButton("전체 선택")
        all_images.clicked.connect(self.select_all)
        buttons.addWidget(all_images)
        clear = QPushButton("선택 해제")
        clear.clicked.connect(self.clear_selection)
        buttons.addWidget(clear)
        buttons.addStretch()
        self.apply_button = QPushButton("선택 이미지 적용")
        self.apply_button.setObjectName("Blue")
        self.apply_button.setEnabled(False)
        self.apply_button.clicked.connect(self.accept)
        buttons.addWidget(self.apply_button)
        cancel = QPushButton("취소")
        cancel.clicked.connect(self.reject)
        buttons.addWidget(cancel)
        layout.addLayout(buttons)
        self.table.itemChanged.connect(lambda *_: self.apply_button.setEnabled(bool(self.selected_jobs())))

    def _select(self, mode):
        previous = self.table.blockSignals(True)
        try:
            for i, (_, _, kinds, existing) in enumerate(self.rows):
                for col, kind in ((2,"hero"),(3,"icon")):
                    if kind in kinds:
                        checked = mode == "all" or (mode == "missing" and kind not in existing)
                        self.table.item(i,col).setCheckState(
                            Qt.CheckState.Checked if checked else Qt.CheckState.Unchecked)
        finally:
            self.table.blockSignals(previous)
        self.apply_button.setEnabled(bool(self.selected_jobs()))

    def select_missing(self):
        self._select("missing")

    def select_all(self):
        self._select("all")

    def clear_selection(self):
        self._select("none")

    def selected_jobs(self):
        jobs = []
        for i, (game, record, kinds, existing) in enumerate(self.rows):
            selected = {kind for col,kind in ((2,"hero"),(3,"icon")) if kind in kinds
                        and self.table.item(i,col).checkState() == Qt.CheckState.Checked}
            if selected:
                jobs.append((game, (record["store"], record["code"]), selected, selected & existing))
        return jobs


class BulkArtworkProgressDialog(QDialog):
    def __init__(self, worker, total, parent=None):
        super().__init__(parent)
        self.worker = worker
        self.running = True
        self.setWindowTitle("공식 이미지 일괄 적용")
        self.resize(530, 150)
        layout = QVBoxLayout(self)
        self.label = QLabel("공식 이미지를 가져오는 중…")
        self.label.setTextFormat(Qt.TextFormat.PlainText)
        layout.addWidget(self.label)
        self.bar = QProgressBar()
        self.bar.setRange(0,total)
        layout.addWidget(self.bar)
        self.stop = QPushButton("중단")
        self.stop.clicked.connect(self.reject)
        layout.addWidget(self.stop)

    def update_progress(self, index, total, name):
        self.bar.setValue(index)
        self.label.setText(f"{index}/{total} · {name}")

    def reject(self):
        if self.running:
            self.worker.requestInterruption()
            self.stop.setEnabled(False)
            self.label.setText("중단 요청 · 현재 이미지 처리 종료 대기")
        else:
            super().reject()

    def closeEvent(self,event):
        if self.running:
            self.reject()
            event.ignore()
        else:
            super().closeEvent(event)

    def finish(self):
        self.running = False
        self.accept()
