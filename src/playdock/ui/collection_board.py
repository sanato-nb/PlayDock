"""Steam-style collection cards and collection-member browsing.

The board is strictly a view over existing CollectionStore data: it never
moves archives, alters installations, or requires network / API calls.
"""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, QRectF, QRect, QEvent, Signal
from PySide6.QtGui import QColor, QFont, QPainter, QPainterPath, QPixmap, QLinearGradient, QPen, QBrush
from PySide6.QtWidgets import (
    QWidget, QFrame, QScrollArea, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLabel, QPushButton, QMenu,
)

from models.collection_board import (list_collection_cards, member_games, unassigned_games,
                                     partition_collection_games)

PALETTES = [
    ("#294a67", "#47677e"), ("#35445c", "#665069"),
    ("#253e49", "#3f6669"), ("#735042", "#ad745c"),
    ("#524321", "#ad7929"), ("#454859", "#626a87"),
    ("#384827", "#758048"), ("#625054", "#976b75"),
]


class ArtworkTile(QPushButton):
    """A self-painted card, with a subtle game-art collage when cached art exists."""

    def __init__(self, title: str, count: str, artwork: list[Path], index: int = 0,
                 *, is_create: bool = False, parent=None):
        super().__init__(parent)
        self.title = title
        self.count = count
        self.is_create = is_create
        self.artwork = [QPixmap(str(p)) for p in artwork[:5] if p.is_file()]
        self.artwork = [img for img in self.artwork if not img.isNull()]
        self.palette = PALETTES[index % len(PALETTES)]
        self.setFixedSize(186, 220)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setToolTip("")
        self.setStyleSheet("border:0; background:transparent; padding:0;")

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        w, h = self.width(), self.height()
        if self.is_create:
            p.setPen(QPen(QColor('#455669'), 2))
            p.setBrush(QColor('#202b39'))
            p.drawRoundedRect(QRectF(2, 2, w - 4, h - 4), 5, 5)
            p.setPen(QPen(QColor('#edf6fb'), 4))
            cx, cy = w // 2, 78
            p.drawLine(cx - 13, cy, cx + 13, cy)
            p.drawLine(cx, cy - 13, cx, cy + 13)
            p.setPen(QColor('#f1f6fb'))
            p.setFont(QFont('Malgun Gothic', 11, QFont.Weight.DemiBold))
            p.drawText(QRect(10, 126, w - 20, 60), Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter,
                       self.title)
            p.end()
            return
        a, b = self.palette
        bg = QLinearGradient(0, 0, w, h)
        bg.setColorAt(0, QColor(a))
        bg.setColorAt(1, QColor(b))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(bg))
        p.drawRoundedRect(QRectF(1, 1, w - 2, h - 2), 5, 5)
        clip = QPainterPath()
        clip.addRoundedRect(QRectF(2, 2, w - 4, h - 4), 5, 5)
        p.save()
        p.setClipPath(clip)
        if self.artwork:
            # A visual collage, using only previously cached local images.
            positions = [(8, 5, 82, 97), (96, 7, 85, 99),
                         (20, 110, 92, 87), (110, 104, 73, 87)]
            for (x, y, tw, th), image in zip(positions, self.artwork):
                p.save()
                p.setOpacity(0.68)
                scale = max(tw / image.width(), th / image.height())
                src = QRectF((image.width() - tw / scale) / 2,
                             (image.height() - th / scale) / 2,
                             tw / scale, th / scale)
                p.drawPixmap(QRectF(x, y, tw, th), image, src)
                p.restore()
        else:
            p.setPen(QPen(QColor(255, 255, 255, 19), 3))
            for i in range(-2, 6):
                x = i * 65 - 25
                p.drawLine(x, 0, x + 135, 168)
            p.setBrush(QColor(255, 255, 255, 12))
            p.setPen(Qt.PenStyle.NoPen)
            p.drawRoundedRect(QRectF(20, 26, 62, 89), 3, 3)
            p.drawRoundedRect(QRectF(100, 12, 55, 94), 3, 3)
        shade = QLinearGradient(0, 82, 0, h)
        shade.setColorAt(0, QColor(15, 24, 34, 0))
        shade.setColorAt(0.7, QColor(12, 19, 29, 148))
        shade.setColorAt(1, QColor(11, 17, 25, 215))
        p.fillRect(QRect(0, 79, w, h - 79), shade)
        p.restore()
        p.setPen(QColor('#f6faff'))
        p.setFont(QFont('Malgun Gothic', 11, QFont.Weight.Bold))
        p.drawText(QRect(10, 142, w - 20, 51), Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter
                   | Qt.TextFlag.TextWordWrap, self.title)
        p.setFont(QFont('Malgun Gothic', 10))
        p.setPen(QColor('#e0e9f0'))
        p.drawText(QRect(8, 191, w - 16, 22), Qt.AlignmentFlag.AlignCenter, self.count)
        if self.underMouse():
            p.setPen(QPen(QColor('#79badf'), 2))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawRoundedRect(QRectF(2, 2, w - 4, h - 4), 5, 5)
        p.end()


class CollectionBoard(QScrollArea):
    collectionOpened = Signal(str)
    gameOpened = Signal(str)
    createRequested = Signal()
    renameRequested = Signal(str)
    deleteRequested = Signal(str)
    backRequested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName('CollectionBoard')
        self.setWidgetResizable(True)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.library = None
        self.games = []
        self.collections = None
        self._active_collection: str | None = None
        self._cards: list[QPushButton] = []
        self._column_count = 0
        root = QWidget()
        root.setObjectName('CollectionBoardRoot')
        self.setWidget(root)
        column = QVBoxLayout(root)
        column.setContentsMargins(24, 20, 24, 18)
        column.setSpacing(12)
        nav = QHBoxLayout()
        self.back = QPushButton('‹  내 모음집')
        self.back.setObjectName('BoardBack')
        self.back.clicked.connect(self._go_back)
        nav.addWidget(self.back)
        self.heading = QLabel('내 모음집')
        self.heading.setObjectName('BoardHeading')
        nav.addWidget(self.heading)
        nav.addStretch(1)
        self.count = QLabel('')
        self.count.setObjectName('BoardSubtle')
        nav.addWidget(self.count)
        column.addLayout(nav)
        line = QWidget()
        line.setObjectName('BoardRule')
        line.setFixedHeight(1)
        column.addWidget(line)
        self.cards_container = QWidget()
        self.cards_container.setObjectName('CollectionBoardRoot')
        self.grid = QGridLayout(self.cards_container)
        self.grid.setContentsMargins(0, 5, 0, 0)
        self.grid.setHorizontalSpacing(16)
        self.grid.setVerticalSpacing(18)
        self.grid.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        column.addWidget(self.cards_container, 0, Qt.AlignmentFlag.AlignTop)
        column.addStretch(1)
        self.viewport().installEventFilter(self)

    def set_data(self, library, games, collections):
        self.library, self.games, self.collections = library, list(games), collections
        self.refresh()

    def show_overview(self):
        self._active_collection = None
        self.refresh()

    def show_collection(self, cid: str):
        self._active_collection = cid
        self.refresh()

    def _go_back(self):
        self.show_overview()
        self.backRequested.emit()

    def _tile_art(self, games):
        paths = []
        if self.library is None:
            return paths
        for game in list(games)[:5]:
            base = self.library.art_dir(game)
            for kind in ('hero.png', 'icon.png'):
                path = base / kind
                if path.is_file():
                    paths.append(path)
                    break
        return paths

    def refresh(self):
        if self.collections is None or self.library is None:
            return
        for card in self._cards:
            self.grid.removeWidget(card)
            card.deleteLater()
        self._cards = []
        records = list_collection_cards(self.collections.list(), self.games)
        record_map = {row['id']: row for row in records}
        if self._active_collection is not None and self._active_collection != '__uncategorized__' \
                and self._active_collection not in record_map:
            self._active_collection = None
        overview = self._active_collection is None
        self.back.setVisible(not overview)
        if overview:
            self.heading.setText('내 모음집')
            self.count.setText(f'{len(records)}개 모음집')
            create = ArtworkTile('새 모음집 만들기', '', [], is_create=True)
            create.clicked.connect(lambda _checked=False: self.createRequested.emit())
            self._cards.append(create)
            buckets, _unassigned = partition_collection_games(self.games, records)
            for idx, (record, members) in enumerate(zip(records, buckets)):
                tile = ArtworkTile(record['name'], f"{len(members)}개 게임", self._tile_art(members), idx)
                tile.clicked.connect(lambda checked=False, cid=record['id']: self.collectionOpened.emit(cid))
                tile.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
                tile.customContextMenuRequested.connect(
                    lambda pos, cid=record['id'], card=tile: self._card_context(cid, card, pos))
                self._cards.append(tile)
        else:
            cid = self._active_collection
            if cid == '__uncategorized__':
                members = unassigned_games(self.games, records)
                name = '미분류'
            else:
                record = record_map[cid]
                members = member_games(self.games, record['game_ids'])
                name = record['name']
            self.heading.setText(name)
            self.count.setText(f'{len(members)}개 게임')
            if not members:
                hint = QPushButton('아직 등록된 게임이 없습니다. 왼쪽에서 게임을 선택해 모음집에 추가하세요.')
                hint.setEnabled(False)
                hint.setFixedHeight(64)
                hint.setMinimumWidth(400)
                self._cards.append(hint)
            titled = [(self.library.title(game), game) for game in members]
            titled.sort(key=lambda row: row[0].casefold())
            for idx, (title, game) in enumerate(titled):
                tile = ArtworkTile(title, '설치됨' if game.installed else '미설치',
                                   self._tile_art([game]), idx)
                tile.clicked.connect(lambda checked=False, gid=game.id: self.gameOpened.emit(gid))
                self._cards.append(tile)
        self._column_count = 0
        self._reflow()

    def _card_context(self, cid: str, tile: QWidget, point):
        menu = QMenu(tile)
        rename = menu.addAction('모음집 이름 변경')
        delete = menu.addAction('모음집 삭제')
        selected = menu.exec(tile.mapToGlobal(point))
        if selected == rename:
            self.renameRequested.emit(cid)
        elif selected == delete:
            self.deleteRequested.emit(cid)

    def _reflow(self):
        columns = max(1, (max(self.viewport().width(), 230) - 48 + 16) // (186 + 16))
        if columns == self._column_count:
            return
        while self.grid.count():
            self.grid.takeAt(0)
        for i, card in enumerate(self._cards):
            self.grid.addWidget(card, i // columns, i % columns,
                                Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        self._column_count = columns

    def eventFilter(self, watched, event):
        if watched is self.viewport() and event.type() == QEvent.Type.Resize:
            self._reflow()
        return super().eventFilter(watched, event)
