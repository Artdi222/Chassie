"""Speech bubble above the avatar: a cream card with a soft shadow and a tail pointing at her.

The window keeps one size and never moves while she talks; the card is drawn inside it and animates
itself (pop in, resize between sentences, fade out), so it looks the same whether or not the
compositor supports window opacity or animations.
"""
from PySide6.QtCore import QEasingCurve, QPointF, QRectF, Qt, QVariantAnimation
from PySide6.QtGui import QColor, QFont, QFontMetrics, QPainter, QPainterPath
from PySide6.QtWidgets import QGraphicsDropShadowEffect, QWidget

SURFACE, LINE, INK = QColor('#fffcf9'), QColor('#e3d2cc'), QColor('#2e2124')  # --surface, --line-2, --ink
SHADOW, TAIL, RADIUS, PAD_X, PAD_Y, MAX_TEXT, MAX_LINES = 16, 10, 18, 18, 12, 300, 7
TEXT_FLAGS = Qt.AlignmentFlag.AlignCenter | Qt.TextFlag.TextWordWrap


def _mix(a, b, t):
    return a + (b - a) * t


class SpeechBubble(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent, Qt.WindowType.Tool | Qt.WindowType.FramelessWindowHint
                         | Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.WindowTransparentForInput)
        self.setWindowTitle('Chassie subtitle')
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.font_ = QFont('Outfit'); self.font_.setPixelSize(15); self.font_.setWeight(QFont.Weight.Medium)
        self.metrics = QFontMetrics(self.font_)
        # Room for the longest card: the window itself never resizes or moves between sentences.
        self.resize(MAX_TEXT + 2 * (PAD_X + SHADOW), self.metrics.lineSpacing() * MAX_LINES + 2 * (PAD_Y + SHADOW) + TAIL)
        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(24); shadow.setOffset(0, 6); shadow.setColor(QColor(58, 36, 48, 46))  # Like --shadow-2.
        self.setGraphicsEffect(shadow)
        self.text, self.reveal, self.morph, self.showing = '', 0.0, 1.0, False
        self.size_from = self.size_to = (60.0, float(self.metrics.lineSpacing()))
        self.reveal_anim = QVariantAnimation(self)
        self.reveal_anim.valueChanged.connect(self._set_reveal)
        self.reveal_anim.finished.connect(lambda: not self.showing and super(SpeechBubble, self).setVisible(False))
        self.morph_anim = QVariantAnimation(self, startValue=0.0, endValue=1.0, duration=200)
        self.morph_anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self.morph_anim.valueChanged.connect(self._set_morph)

    def _set_reveal(self, value):
        self.reveal = value; self.update()

    def _set_morph(self, value):
        self.morph = value; self.update()

    def _text_size(self, text):
        width = min(MAX_TEXT, max(40, self.metrics.horizontalAdvance(text) + 2))  # Short lines: a small card.
        height = self.metrics.boundingRect(0, 0, width, 10_000, TEXT_FLAGS, text).height()
        return float(width), float(min(height, self.metrics.lineSpacing() * MAX_LINES))

    def _current_size(self):
        return tuple(_mix(a, b, self.morph) for a, b in zip(self.size_from, self.size_to))

    def setText(self, text):
        if text == self.text: return
        current = self._current_size()
        self.text, self.size_to = text, self._text_size(text)
        if self.showing and self.reveal > 0:  # Next sentence: the card grows or shrinks to it smoothly.
            self.size_from = current; self.morph_anim.stop(); self.morph = 0.0; self.morph_anim.start()
        else:
            self.size_from, self.morph = self.size_to, 1.0
        self.update()

    def setVisible(self, visible):
        if visible == self.showing: return
        self.showing = visible
        self.reveal_anim.stop()
        if visible: super().setVisible(True)
        self.reveal_anim.setStartValue(self.reveal); self.reveal_anim.setEndValue(1.0 if visible else 0.0)
        self.reveal_anim.setDuration(220 if visible else 170)
        self.reveal_anim.setEasingCurve(QEasingCurve.Type.OutCubic if visible else QEasingCurve.Type.InCubic)
        self.reveal_anim.start()

    def isVisible(self):
        return self.showing

    def paintEvent(self, _event):
        if self.reveal <= 0: return
        width, height = self._current_size()
        tip = QPointF(self.width() / 2, self.height() - SHADOW)  # Tail tip: bottom centre, pointing at her.
        body = QRectF(tip.x() - width / 2 - PAD_X, tip.y() - TAIL - height - 2 * PAD_Y, width + 2 * PAD_X, height + 2 * PAD_Y)
        path = QPainterPath(); path.addRoundedRect(body, RADIUS, RADIUS)
        tail = QPainterPath()
        tail.moveTo(QPointF(tip.x() - TAIL, body.bottom() - 1)); tail.lineTo(tip); tail.lineTo(QPointF(tip.x() + TAIL, body.bottom() - 1))
        path = path.united(tail)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setOpacity(self.reveal)
        scale = 0.94 + 0.06 * self.reveal  # Pops up from her head: grows from the tail and rises a little.
        painter.translate(tip.x(), tip.y() + (1 - self.reveal) * 8); painter.scale(scale, scale); painter.translate(-tip.x(), -tip.y())
        painter.setBrush(SURFACE); painter.setPen(LINE)
        painter.drawPath(path)
        painter.setOpacity(self.reveal * min(1.0, 0.25 + self.morph))  # A new sentence fades in as the card settles.
        painter.setPen(INK); painter.setFont(self.font_)
        painter.setClipRect(body.adjusted(PAD_X / 2, PAD_Y / 2, -PAD_X / 2, -PAD_Y / 2))
        final = QRectF(0, 0, *self.size_to); final.moveCenter(body.center())  # Wrapped once, at its final width.
        painter.drawText(final, TEXT_FLAGS, self.text)
