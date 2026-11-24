"""Plain JSON input and explicit preview for external AI suggestions."""
from pathlib import Path
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPlainTextEdit,
    QPushButton, QTableWidget, QTableWidgetItem, QHeaderView)
from ui.dialogs.file_dialog import PlayDockFileDialog as QFileDialog
from ui.dialogs.common import show_message
from services.identity_import_service import MAX_BYTES


class IdentityImportDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("AI 품번 결과 가져오기")
        self.resize(720, 490)
        layout = QVBoxLayout(self)
        hint = QLabel("AI가 반환한 PlayDock JSON 파일을 선택하거나 내용을 붙여넣으세요.\n"
                      "실행 코드가 아닌 데이터만 읽으며, 다음 화면에서 등록 후보를 확인합니다.")
        hint.setWordWrap(True)
        layout.addWidget(hint)
        self.edit = QPlainTextEdit()
        self.edit.setPlaceholderText("PlayDock_Identity_Import JSON")
        layout.addWidget(self.edit, 1)
        row = QHBoxLayout()
        load = QPushButton("JSON/TXT 파일 선택")
        load.clicked.connect(self.load_file)
        row.addWidget(load)
        row.addStretch()
        confirm = QPushButton("결과 확인")
        confirm.clicked.connect(self.accept)
        row.addWidget(confirm)
        cancel = QPushButton("취소")
        cancel.clicked.connect(self.reject)
        row.addWidget(cancel)
        layout.addLayout(row)

    def load_file(self):
        filename, _ = QFileDialog.getOpenFileName(self,"AI 품번 결과 파일 선택","","JSON/TXT (*.json *.txt)")
        if not filename:
            return
        try:
            with Path(filename).open("rb") as f:
                raw = f.read(MAX_BYTES+1)
            if len(raw)>MAX_BYTES:
                raise ValueError("최대 2MB까지 지원합니다.")
            self.edit.setPlainText(raw.decode("utf-8-sig"))
        except (OSError,ValueError) as exc:
            show_message(self,"파일 읽기 실패",str(exc))


class IdentityImportPreviewDialog(QDialog):
    """Explicit per-game approval. Never trust an AI candidate automatically."""
    def __init__(self, proposals, rejected, parent=None, *, official_titles=None):
        super().__init__(parent)
        self.proposals = list(proposals)
        verified = official_titles is not None
        self.setWindowTitle("공식 조회 결과 확인" if verified else "품번 등록 후보 확인")
        self.resize(980, 590)
        layout = QVBoxLayout(self)
        label = QLabel(f"{'공식 확인' if verified else '조회 후보'} {len(proposals)}개 · 제외 {len(rejected)}개\n"
                       + ("실제 공식 작품명과 원본 게임을 비교하고 등록할 항목을 선택하세요."
                          if verified else "조회할 후보만 선택하세요. 공식 조회 후 다시 등록 여부를 확인합니다."))
        label.setWordWrap(True)
        layout.addWidget(label)
        self.table = QTableWidget(len(proposals), 5)
        self.table.setHorizontalHeaderLabels(["선택", "원본 파일명", "품번 / 상태", "공식 작품명" if verified else "AI 후보 작품명", "조사 근거"])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeMode.Stretch)
        self.table.setWordWrap(True)
        for i, p in enumerate(self.proposals):
            check = QTableWidgetItem()
            check.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsUserCheckable)
            check.setCheckState(Qt.CheckState.Unchecked)
            self.table.setItem(i,0,check)
            title = official_titles.get(p.game.id, "") if verified else p.title
            state = "공식 확인" if verified else "검토 필요" if p.status == "needs_review" else "AI 확인"
            for col, value in enumerate((p.filename, f"{p.store.upper()} {p.code}\n{state}", title, p.reason or "근거 미제공"), 1):
                item = QTableWidgetItem(value)
                item.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
                self.table.setItem(i,col,item)
        self.table.resizeRowsToContents()
        layout.addWidget(self.table, 3)
        layout.addWidget(QLabel("미확인 / 제외 사유"))
        details = QPlainTextEdit()
        details.setReadOnly(True)
        details.setPlainText("\n".join(rejected))
        details.setPlaceholderText("제외 항목 없음")
        layout.addWidget(details, 1)
        row = QHBoxLayout()
        select = QPushButton("전체 선택")
        select.clicked.connect(lambda: self.select_all(True))
        row.addWidget(select)
        clear = QPushButton("선택 해제")
        clear.clicked.connect(lambda: self.select_all(False))
        row.addWidget(clear)
        row.addStretch()
        self.confirm = QPushButton("선택 품번 등록" if verified else "선택 후보 공식 조회")
        self.confirm.setEnabled(False)
        self.confirm.clicked.connect(self.accept)
        row.addWidget(self.confirm)
        cancel = QPushButton("취소")
        cancel.clicked.connect(self.reject)
        row.addWidget(cancel)
        layout.addLayout(row)
        self.table.itemChanged.connect(self.refresh_selection)

    def refresh_selection(self, *_):
        self.confirm.setEnabled(bool(self.selected_proposals()))

    def select_all(self, checked):
        old = self.table.blockSignals(True)
        try:
            for i in range(len(self.proposals)):
                self.table.item(i,0).setCheckState(Qt.CheckState.Checked if checked else Qt.CheckState.Unchecked)
        finally:
            self.table.blockSignals(old)
        self.refresh_selection()

    def selected_proposals(self):
        return [p for i,p in enumerate(self.proposals)
                if self.table.item(i,0).checkState() == Qt.CheckState.Checked]
