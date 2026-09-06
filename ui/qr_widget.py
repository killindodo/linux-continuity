"""
QR Code Renderer Widget for PyQt6.
Uses pure-Python qrcodegen to draw antialiased QR codes on screen.
"""

from PyQt6.QtWidgets import QWidget
from PyQt6.QtCore import Qt, QRectF
from PyQt6.QtGui import QPainter, QColor, QPen, QBrush
from core.qrcodegen import QrCode


class QRWidget(QWidget):
    def __init__(self, text: str = "", parent=None):
        super().__init__(parent)
        self.text = text
        self.qr: QrCode = None
        self.setMinimumSize(180, 180)
        self.set_text(text)

    def set_text(self, text: str):
        self.text = text
        if text:
            try:
                self.qr = QrCode.encode_text(text, QrCode.Ecc.MEDIUM)
            except Exception:
                self.qr = None
        else:
            self.qr = None
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        w = self.width()
        h = self.height()
        side = min(w, h)

        # Background card
        rect_bg = QRectF((w - side) / 2.0, (h - side) / 2.0, side, side)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(255, 255, 255))
        painter.drawRoundedRect(rect_bg, 14, 14)

        if not self.qr:
            painter.end()
            return

        size = self.qr.get_size()
        border = 2
        total_cells = size + border * 2
        cell_size = (side - 16) / float(total_cells)
        offset_x = (w - (cell_size * total_cells)) / 2.0
        offset_y = (h - (cell_size * total_cells)) / 2.0

        painter.setBrush(QColor(18, 22, 32))
        for y in range(size):
            for x in range(size):
                if self.qr.get_module(x, y):
                    rx = offset_x + (x + border) * cell_size
                    ry = offset_y + (y + border) * cell_size
                    painter.drawRect(QRectF(rx, ry, cell_size, cell_size))

        painter.end()
