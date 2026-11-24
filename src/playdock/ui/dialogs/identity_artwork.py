"""PlayDock identity verification result: opt-in official banner/icon checkboxes.

No image is applied when the dialog opens. Both checkboxes start unchecked;
one can be applied without changing the other. The caller owns persistence.
"""
from __future__ import annotations

import webbrowser

from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QCheckBox, QDialog, QFrame, QHBoxLayout, QLabel, QPushButton,
    QVBoxLayout, QWidget,
)


class IdentityArtworkDialog(QDialog):
    def __init__(self, work, images: dict, *, existing_kinds=(), warnings=(), parent=None):
        super().__init__(parent)
        self.work = work
        self.images = images
        self.setWindowTitle("배너·아이콘 설정 · 공식 이미지")
        self.resize(790, 560)
        self.setMinimumWidth(680)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 18, 20, 18)
        layout.setSpacing(13)

        heading = QLabel("공식 작품 이미지 설정")
        heading.setObjectName("Heading")
        heading.setStyleSheet("font-size:19px; font-weight:700;")
        layout.addWidget(heading)
        site = "DLsite" if work.store == "dlsite" else "Steam"
        details = QLabel()
        details.setTextFormat(Qt.TextFormat.PlainText)
        details.setText(f"{work.title}\n{site} · {work.code} · {work.category or '분류 없음'}")
        details.setWordWrap(True)
        layout.addWidget(details)
        notice = QLabel(
            "공식 페이지에서 가져온 이미지입니다. 배너와 아이콘을 각각 선택하세요.\n"
            "체크하지 않으면 기존 이미지를 그대로 유지합니다. 기본값은 둘 다 적용하지 않음입니다."
        )
        notice.setWordWrap(True)
        notice.setStyleSheet("color:#9db0c3;")
        layout.addWidget(notice)

        panels = QHBoxLayout()
        panels.setSpacing(14)
        self.apply_banner = self._art_panel(panels, "hero", "배너 적용",
                                             images.get("hero"), "hero" in existing_kinds)
        self.apply_icon = self._art_panel(panels, "icon", "아이콘 적용",
                                           images.get("icon"), "icon" in existing_kinds)
        layout.addLayout(panels)

        if warnings:
            message = QLabel("참고: " + " · ".join(str(w) for w in warnings[:2])[:350])
            message.setTextFormat(Qt.TextFormat.PlainText)
            message.setWordWrap(True)
            message.setStyleSheet("color:#a8afbd;")
            layout.addWidget(message)

        link = QPushButton(f"{site} 공식 작품 페이지 열기")
        link.clicked.connect(lambda: webbrowser.open(work.url))
        layout.addWidget(link)
        layout.addStretch(1)

        actions = QHBoxLayout()
        actions.addStretch()
        save = QPushButton("체크한 이미지 적용 · 미선택 유지")
        save.setObjectName("Blue")
        save.clicked.connect(self.accept)
        actions.addWidget(save)
        cancel = QPushButton("취소")
        cancel.clicked.connect(self.reject)
        actions.addWidget(cancel)
        layout.addLayout(actions)

    def _art_panel(self, row, kind, caption, offer, exists):
        frame = QFrame()
        frame.setObjectName("InfoCard")
        card = QVBoxLayout(frame)
        card.setContentsMargins(12, 12, 12, 12)
        card.setSpacing(9)
        title = QLabel("공식 배너 후보" if kind == "hero" else "공식 아이콘 후보")
        title.setStyleSheet("font-weight:600;")
        card.addWidget(title)
        preview = QLabel("공식 이미지를 가져오지 못했습니다")
        preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        preview.setFixedHeight(185)
        preview.setMinimumWidth(230)
        preview.setWordWrap(True)
        preview.setStyleSheet(
            "background:#101923; color:#9aaaba; border:1px solid #344b60; border-radius:6px;"
        )
        if offer is not None and getattr(offer, "preview", None):
            pixmap = QPixmap()
            if pixmap.loadFromData(offer.preview):
                preview.setPixmap(pixmap.scaled(
                    330 if kind == "hero" else 175, 175,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation))
        card.addWidget(preview)
        checkbox = QCheckBox(caption)
        checkbox.setChecked(False)
        checkbox.setEnabled(offer is not None)
        card.addWidget(checkbox)
        state = QLabel("현재 이미지 있음 · 체크 시 교체 확인" if exists
                       else "현재 이미지 없음" if offer is not None
                       else "공식 이미지 없음 · 변경 불가")
        state.setWordWrap(True)
        state.setStyleSheet("color:#9db0c3; font-size:11px;")
        card.addWidget(state)
        row.addWidget(frame, 1)
        return checkbox

    def selected_kinds(self) -> set[str]:
        chosen = set()
        if self.apply_banner.isEnabled() and self.apply_banner.isChecked():
            chosen.add("hero")
        if self.apply_icon.isEnabled() and self.apply_icon.isChecked():
            chosen.add("icon")
        return chosen
