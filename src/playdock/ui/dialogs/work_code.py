"""Single-game work code settings; registration is not verification."""
from PySide6.QtWidgets import QLabel, QLineEdit, QHBoxLayout, QPushButton
from ui.dialogs.common import ThemedDialog
from ui.selectors import DarkMenuSelect
from ui.widgets.buttons import configure_action_button
from services.manual_work_identity import normalize_manual_identity


class WorkCodeDialog(ThemedDialog):
    def __init__(self, title, store, code, verified, parent=None):
        super().__init__("작품 코드 설정", parent, 480)
        self.original = (store, code)
        self.verified = verified
        label = QLabel(title)
        label.setWordWrap(True)
        self.body.addWidget(label)
        self.body.addWidget(QLabel("공식 판매처"))
        self.store = DarkMenuSelect()
        for text, value in (("DLsite", "dlsite"), ("Steam", "steam"), ("없음 (연결 해제)", "none")):
            self.store.addItem(text, value)
        self.store.setCurrentIndex(max(0, self.store.findData(store)))
        self.body.addWidget(self.store)
        self.body.addWidget(QLabel("작품 품번 / Steam App ID"))
        self.code = QLineEdit(code)
        self.body.addWidget(self.code)
        self.status = QLabel()
        self.status.setWordWrap(True)
        self.body.addWidget(self.status)
        note = QLabel("게임 정보 수집에서 공식 작품을 확인하세요. 기존 이름·이미지와 실제 게임 파일은 변경하지 않습니다.")
        note.setWordWrap(True)
        self.body.addWidget(note)
        row = QHBoxLayout()
        row.addStretch()
        self.apply = QPushButton("적용")
        configure_action_button(self.apply, "Save")
        self.apply.clicked.connect(self.accept)
        row.addWidget(self.apply)
        close = QPushButton("닫기")
        close.clicked.connect(self.reject)
        row.addWidget(close)
        self.body.addLayout(row)
        self.store.currentIndexChanged.connect(self.store_changed)
        self.code.textChanged.connect(self.update_status)
        self.update_status()

    def store_changed(self, *_):
        self.code.clear()
        self.update_status()

    def selection(self):
        return normalize_manual_identity(self.store.currentData(), self.code.text())

    def update_status(self, *_):
        store = self.store.currentData()
        self.code.setEnabled(store != "none")
        self.code.setPlaceholderText("RJ123456" if store == "dlsite" else "1234560" if store == "steam" else "")
        try:
            normalized = self.selection()
        except ValueError as exc:
            self.status.setText(str(exc))
            self.apply.setEnabled(False)
            return
        if store == "none":
            self.status.setText("작품 코드 연결 해제 · 자동 파일명 조회 제외")
        elif self.verified and normalized == self.original:
            self.status.setText("공식 작품 확인 완료")
        else:
            self.status.setText("미확인 · 게임 정보 수집 필요")
        self.apply.setEnabled(True)

    def accept(self):
        try:
            self.selection()
        except ValueError:
            return
        super().accept()
