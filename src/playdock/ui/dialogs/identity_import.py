"""Plain JSON input and explicit preview for external AI suggestions."""
from pathlib import Path
from PySide6.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPlainTextEdit, QPushButton
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
    def __init__(self, proposals, rejected, parent=None):
        super().__init__(parent)
        self.setWindowTitle("품번 등록 후보 확인")
        self.resize(780, 500)
        layout = QVBoxLayout(self)
        label = QLabel(f"등록 후보 {len(proposals)}개 · 제외 {len(rejected)}개\n"
                       "AI가 찾은 작품이 실제 보유 게임과 같은지 확인하세요. "
                       "공식 사이트 재조회에 성공한 품번만 등록합니다. 원본 파일명은 유지합니다.")
        label.setWordWrap(True)
        layout.addWidget(label)
        preview = QPlainTextEdit()
        preview.setReadOnly(True)
        preview.setPlainText("\n".join(
            [f"{p.filename}\n  → {p.store.upper()} {p.code} · {p.title}\n  {p.url}" for p in proposals]
            + ["\n[제외]"] + list(rejected)))
        layout.addWidget(preview,1)
        row = QHBoxLayout()
        row.addStretch()
        confirm = QPushButton("확인한 후보 공식 조회 및 등록")
        confirm.setEnabled(bool(proposals))
        confirm.clicked.connect(self.accept)
        row.addWidget(confirm)
        cancel = QPushButton("취소")
        cancel.clicked.connect(self.reject)
        row.addWidget(cancel)
        layout.addLayout(row)
