"""High-contrast table checkboxes that preserve adjacent status text."""
from PySide6.QtCore import Qt, QEvent, QRectF, QSize
from PySide6.QtGui import QColor, QPainter, QPen, QPalette
from PySide6.QtWidgets import QApplication, QStyle, QStyleOptionViewItem, QStyledItemDelegate


def _draw_check(painter, box, checked):
    """Shared checkbox palette and geometry."""
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setPen(QPen(QColor("#59b8ee" if checked else "#8bb4ce"), 1.5))
    painter.setBrush(QColor("#207cac" if checked else "#101923"))
    painter.drawRoundedRect(box, 3, 3)
    if checked:
        painter.setPen(QPen(QColor("#ffffff"), 2, Qt.PenStyle.SolidLine,
                            Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
        x, y = box.x(), box.y()
        painter.drawLine(int(x + 4), int(y + 9), int(x + 8), int(y + 13))
        painter.drawLine(int(x + 8), int(y + 13), int(x + 14), int(y + 5))


class StatusCheckDelegate(QStyledItemDelegate):
    """Paint the same bright checkbox palette as the AI candidate review."""
    BOX = 18
    PADDING = 8
    GAP = 7

    @staticmethod
    def _checkable(index):
        flags = index.flags()
        return bool(flags & Qt.ItemFlag.ItemIsEnabled and
                    flags & Qt.ItemFlag.ItemIsUserCheckable)

    def sizeHint(self, option, index):
        size = super().sizeHint(option, index)
        opt = QStyleOptionViewItem(option)
        self.initStyleOption(opt, index)
        width = opt.fontMetrics.horizontalAdvance(opt.text) + self.PADDING * 2
        if self._checkable(index):
            width += self.BOX + self.GAP
        return QSize(max(size.width(), width), max(size.height(), self.BOX + 12))

    def paint(self, painter, option, index):
        if not self._checkable(index):
            super().paint(painter, option, index)
            return
        opt = QStyleOptionViewItem(option)
        self.initStyleOption(opt, index)
        text = opt.text
        opt.text = ""
        opt.features &= ~QStyleOptionViewItem.ViewItemFeature.HasCheckIndicator
        style = opt.widget.style() if opt.widget else QApplication.style()
        # Keep the normal table background, selection and focus painting.
        style.drawControl(QStyle.ControlElement.CE_ItemViewItem, opt, painter, opt.widget)
        checked = index.data(Qt.ItemDataRole.CheckStateRole) == Qt.CheckState.Checked.value
        left = opt.rect.left() + self.PADDING if text else opt.rect.center().x() - self.BOX / 2
        box = QRectF(left,
                     opt.rect.center().y() - self.BOX / 2,
                     self.BOX, self.BOX)
        painter.save()
        painter.setClipRect(opt.rect)
        _draw_check(painter, box, checked)
        text_rect = opt.rect.adjusted(self.PADDING + self.BOX + self.GAP,
                                      0, -self.PADDING, 0)
        role = (QPalette.ColorRole.HighlightedText
                if opt.state & QStyle.StateFlag.State_Selected else QPalette.ColorRole.Text)
        painter.setFont(opt.font)
        painter.setPen(opt.palette.color(role))
        label = opt.fontMetrics.elidedText(text, Qt.TextElideMode.ElideRight,
                                           max(0, text_rect.width()))
        painter.drawText(text_rect, int(Qt.AlignmentFlag.AlignVCenter |
                                       Qt.AlignmentFlag.AlignLeft), label)
        painter.restore()

    def editorEvent(self, event, model, option, index):
        if not self._checkable(index):
            return False
        mouse = (event.type() == QEvent.Type.MouseButtonRelease and
                 event.button() == Qt.MouseButton.LeftButton and
                 option.rect.contains(event.position().toPoint()))
        key = (event.type() == QEvent.Type.KeyPress and
               event.key() in (Qt.Key.Key_Space, Qt.Key.Key_Select))
        if mouse or key:
            checked = index.data(Qt.ItemDataRole.CheckStateRole) == Qt.CheckState.Checked.value
            return model.setData(index, Qt.CheckState.Unchecked.value if checked
                                 else Qt.CheckState.Checked.value, Qt.ItemDataRole.CheckStateRole)
        return False


class CandidateCheckDelegate(StatusCheckDelegate):
    """Readable check marks independent of the operating system's palette."""
    def paint(self, painter, option, index):
        QStyledItemDelegate.paint(self, painter, option, index)
        painter.save()
        painter.fillRect(option.rect, QColor("#1b2836"))
        checked = index.data(Qt.ItemDataRole.CheckStateRole) == Qt.CheckState.Checked.value
        box = QRectF(option.rect.center().x()-9, option.rect.center().y()-9, 18, 18)
        _draw_check(painter, box, checked)
        painter.restore()


