"""Speech bubble above the avatar: a cream card with a soft shadow and a tail pointing at her."""
from PySide6.QtCore import QPointF, QPropertyAnimation, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QFontMetrics, QPainter, QPainterPath
from PySide6.QtWidgets import QGraphicsDropShadowEffect, QLabel, QWidget

SURFACE, LINE, INK = QColor('#fffcf9'), QColor('#e3d2cc'), '#2e2124'  # --surface, --line-2, --ink (ui/style.css)
SHADOW, TAIL, RADIUS, PAD_X, PAD_Y, MAX_TEXT = 14, 10, 18, 18, 12, 300


class SpeechBubble(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent, Qt.WindowType.Tool | Qt.WindowType.FramelessWindowHint
                         | Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.WindowTransparentForInput)
        self.setWindowTitle('Chassie subtitle')
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.label = QLabel(self)
        self.label.setWordWrap(True)
        self.label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        font = QFont('Outfit'); font.setPixelSize(15); font.setWeight(QFont.Weight.Medium); self.label.setFont(font)
        self.label.setStyleSheet(f'QLabel{{color:{INK};background:transparent;}}')
        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(24); shadow.setOffset(0, 6); shadow.setColor(QColor(58, 36, 48, 46))  # Like --shadow-2.
        self.setGraphicsEffect(shadow)
        self.fade = QPropertyAnimation(self, b'windowOpacity', self)
        self.fade.setDuration(160)
        self.fade.finished.connect(lambda: self.windowOpacity() == 0 and super(SpeechBubble, self).setVisible(False))

    def setText(self, text):
        self.label.setText(text)
        metrics = QFontMetrics(self.label.font())
        width = min(MAX_TEXT, max(60, metrics.horizontalAdvance(text) + 2))  # Short lines get a small bubble.
        height = metrics.boundingRect(0, 0, width, 10_000, Qt.TextFlag.TextWordWrap, text).height()
        self.label.setGeometry(SHADOW + PAD_X, SHADOW + PAD_Y, width, height)
        self.resize(width + 2 * (SHADOW + PAD_X), height + 2 * (SHADOW + PAD_Y) + TAIL)
        self.update()

    def setVisible(self, visible):
        if visible == (self.isVisible() and self.fade.endValue() != 0): return
        self.fade.stop()
        if visible:
            self.setWindowOpacity(0); super().setVisible(True)
        self.fade.setStartValue(self.windowOpacity()); self.fade.setEndValue(1.0 if visible else 0.0); self.fade.start()

    def paintEvent(self, _event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        body = QRectF(SHADOW, SHADOW, self.width() - 2 * SHADOW, self.height() - 2 * SHADOW - TAIL)
        path = QPainterPath(); path.addRoundedRect(body, RADIUS, RADIUS)
        tail = QPainterPath(); x = body.center().x()
        tail.moveTo(QPointF(x - TAIL, body.bottom() - 1)); tail.lineTo(QPointF(x, body.bottom() + TAIL)); tail.lineTo(QPointF(x + TAIL, body.bottom() - 1))
        path = path.united(tail)
        painter.setBrush(SURFACE); painter.setPen(LINE)
        painter.drawPath(path)
