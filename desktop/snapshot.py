"""Crop the avatar out of its transparent frame and encode it as a small PNG."""
import base64

import numpy as np
from PySide6.QtCore import QBuffer, QByteArray, QIODevice, Qt
from PySide6.QtGui import QImage


def avatar_png(image, largest=768):
    """Base64 PNG of the visible (non-transparent) part, or None when nothing is drawn yet."""
    image = image.convertToFormat(QImage.Format.Format_RGBA8888)
    pixels = np.frombuffer(image.constBits(), np.uint8, image.sizeInBytes()).reshape(image.height(), image.bytesPerLine())
    alpha = pixels[:, :image.width() * 4].reshape(image.height(), image.width(), 4)[:, :, 3]
    rows, cols = np.nonzero(alpha.max(axis=1) > 8)[0], np.nonzero(alpha.max(axis=0) > 8)[0]
    if not len(rows) or not len(cols): return None
    image = image.copy(int(cols[0]), int(rows[0]), int(cols[-1] - cols[0] + 1), int(rows[-1] - rows[0] + 1))
    if max(image.width(), image.height()) > largest:
        image = image.scaled(largest, largest, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
    data = QByteArray(); buffer = QBuffer(data); buffer.open(QIODevice.OpenModeFlag.WriteOnly)
    image.save(buffer, 'PNG')
    return base64.b64encode(bytes(data)).decode('ascii')
