"""Optional Qt/Cubism renderer. All OpenGL work stays on the GUI thread."""
import json
import logging
from pathlib import Path
import time

from PySide6.QtCore import Qt, QTimer, QUrl, Signal
from PySide6.QtGui import QAction, QSurfaceFormat, QIcon, QCursor
from PySide6.QtOpenGLWidgets import QOpenGLWidget
from PySide6.QtWebSockets import QWebSocket
from PySide6.QtWidgets import (QApplication, QCheckBox, QLabel, QMenu, QMessageBox,
                               QPushButton, QStyle, QSystemTrayIcon, QVBoxLayout, QWidget)

from desktop.motion import HeadMotion
from desktop.attention import Attention, direction
from desktop.model import prepare_entry, CatalogModelDriver
# Load Qt's C++ runtime before the Live2D wheel. Importing _v3cpp first
# interposes its std::filesystem symbols into Qt WebEngine and aborts when
# the first panel creates a Chromium profile (std::bad_alloc, not RAM exhaustion).
import live2d.v3 as live2d

from desktop.state import OverlayState, Rect, Framing, bottom_right, fit_to_screens
from desktop.compositor import APPLICATION_ID, configure_hyprland
from desktop.pointer import PointerInteraction


def screens():
    return [Rect(r.x(), r.y(), r.width(), r.height())
            for screen in QApplication.screens() for r in [screen.availableGeometry()]]


class AvatarWindow(QOpenGLWidget):
    failed = Signal(str)
    readiness_changed = Signal(bool)
    clicked = Signal()
    relocated = Signal()

    def __init__(self, model_path, state, fps):
        super().__init__()
        self.model_path, self.state, self.fps = model_path, state, fps
        self.model = self.driver = None
        self.pointer_interaction = None
        self.attention = Attention()
        self.renderer_ready = False
        self.loaded_expressions = ()
        self.drag_offset = None
        self.click_through = False
        self.entry = None
        self.selection = {}
        self.press_position = None
        self.framing = Framing()
        self.setWindowTitle('Chassie')
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.Tool)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, False)
        self.setAutoFillBackground(False)
        self.setMinimumSize(120, 160)
        fmt = QSurfaceFormat()
        fmt.setAlphaBufferSize(8)
        fmt.setDepthBufferSize(24)
        fmt.setStencilBufferSize(8)
        fmt.setVersion(2, 1)
        fmt.setProfile(QSurfaceFormat.OpenGLContextProfile.CompatibilityProfile)
        self.setFormat(fmt)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.tick)

    def initializeGL(self):
        try:
            live2d.glInit()
            self.model = live2d.LAppModel()
            self.model.LoadModelJson(str(self.model_path))
            if self.model.GetParameterCount() <= 0:
                raise RuntimeError('Cubism did not load any model parameters')
            self.model.SetAutoBlinkEnable(True)
            self.model.SetAutoBreathEnable(True)
            self.driver = CatalogModelDriver(self.model,self.entry)
            self.head_motion = HeadMotion(self.model.GetParamIds())
            if self.entry:
                self.pointer_interaction=PointerInteraction(self.model,self.entry.head_parts,self.model_path.parent,
                                                            getattr(self.entry,'aliases',None))
            self.loaded_expressions = tuple(self.model.GetExpressionIds())
            self.context().aboutToBeDestroyed.connect(self.cleanup)
            self.resizeGL(self.width(), self.height())
            self.timer.start(round(1000 / self.fps))
        except Exception as exc:
            self.timer.stop()
            QTimer.singleShot(0, lambda message=str(exc): self.failed.emit(message))

    def attention_target(self):
        """Look at a thought, the chat being typed in, the owner's face, or now and then the screen."""
        centre = self.mapToGlobal(self.rect().center())
        origin = (centre.x(), centre.y())
        screen = self.screen().availableGeometry() if self.screen() else None
        reach = max(screen.width(), screen.height()) / 2 if screen else 800
        controls = getattr(self, 'studio_controls', None)
        chat = controls.focused_chat_centre() if controls and hasattr(controls, 'focused_chat_centre') else None
        return self.attention.look(
            self.state.status, face=self.state.gaze, now=time.monotonic(),
            chat=direction(origin, chat, reach) if chat else None,
            screen=direction(origin, (screen.center().x(), screen.center().y()), reach) if screen else None)

    def resizeGL(self, width, height):
        if self.model:
            ratio = self.devicePixelRatioF()
            self.model.Resize(round(width * ratio), round(height * ratio))

    def paintGL(self):
        if not self.driver:
            return
        try:
            live2d.clearBuffer(0.0, 0.0, 0.0, 0.0)
            if self.entry:
                emotion=self.state.emotion
                if self.entry.generated:
                    emotion={'thinking':'waiting','listening':'curious','idle':'neutral','disconnected':'neutral'}.get(self.state.status,emotion)
                self.driver.apply(self.selection,emotion,self.state.variant if emotion==self.state.emotion else 0)
            self.model.SetScale(self.framing.zoom)
            self.model.SetOffset(0.0, self.framing.vertical)
            if self.pointer_interaction:
                cursor=self.mapFromGlobal(QCursor.pos())
                self.pointer_interaction.update(cursor.x(),cursor.y(),self.width(),self.height(),
                    ratio=self.devicePixelRatioF(),now=time.monotonic(),dragging=self.drag_offset is not None,
                    settings=self.selection.get('interaction'),look=self.attention_target(),hovered=self.underMouse())
            now=time.monotonic()
            self.driver.frame(max(self.state.mouth_at(now),self.selection.get('mouth_preview',0)),
                              self.head_motion.step(self.state.status,now,self.state.nod_at),
                              self.pointer_interaction.look if self.pointer_interaction else None,
                              self.state.status)
            if not self.renderer_ready:
                self.renderer_ready = True
                self.readiness_changed.emit(True)
        except Exception as exc:
            self.timer.stop()
            self.renderer_ready = False
            self.readiness_changed.emit(False)
            self.driver = None
            QTimer.singleShot(0, lambda message=str(exc): self.failed.emit(message))

    def tick(self):
        if self.isVisible():
            self.update()

    def set_click_through(self, enabled):
        self.click_through = enabled
        visible = self.isVisible()
        self.setWindowFlag(Qt.WindowType.WindowTransparentForInput, enabled)
        if visible:
            self.show()

    # Under XWayland a client-side move() races the compositor: X root coordinates jump to
    # the new window position before Hyprland moves the surface, so every drag step was
    # counted twice and the window flew away. Hand the drag to the compositor instead
    # (_NET_WM_MOVERESIZE); it tracks the pointer itself with no feedback loop.
    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.drag_offset = event.globalPosition().toPoint() - self.pos()
            self.press_position = event.globalPosition().toPoint()

    def mouseMoveEvent(self, event):
        if self.drag_offset is None or not event.buttons() & Qt.MouseButton.LeftButton:
            return
        if (event.globalPosition().toPoint() - self.press_position).manhattanLength() <= 6:
            return
        handle = self.windowHandle()
        if handle is not None and handle.startSystemMove():
            self.drag_offset = self.press_position = None  # The compositor owns the drag now.
            return
        self.move(event.globalPosition().toPoint() - self.drag_offset)

    def moveEvent(self, event):
        super().moveEvent(event)
        self.relocated.emit()  # Keep the bubbles beside the avatar however it moved.

    def mouseReleaseEvent(self, event):
        if self.press_position is not None and (event.globalPosition().toPoint()-self.press_position).manhattanLength()<=6:
            self.clicked.emit()
        self.drag_offset = None
        self.press_position = None

    def select_entry(self, entry, selection, cache_dir):
        self.selection = selection
        if self.entry and self.entry.id == entry.id:
            self.update()
            return
        prepared = prepare_entry(entry, cache_dir)
        self.entry = entry
        self.model_path = prepared
        if self.model:
            self.makeCurrent()
            self.timer.stop()
            self.model.DestroyRenderer()
            self.model = self.driver = None
            self.renderer_ready = False
            self.initializeGL()
            self.doneCurrent()
        self.update()

    def cleanup(self):
        self.timer.stop()
        self.renderer_ready = False
        self.loaded_expressions = ()
        self.readiness_changed.emit(False)
        if self.model:
            self.makeCurrent()
            self.model.DestroyRenderer()
            self.model = self.driver = None
            live2d.glRelease()
            self.doneCurrent()


class Controls(QWidget):
    def __init__(self, window, state, endpoint, settings_path):
        super().__init__()
        self.window, self.state = window, state
        self.settings_path, self.endpoint = settings_path, endpoint
        self.connected = False
        self.setWindowTitle('Chassie controls')
        layout = QVBoxLayout(self)
        self.status = QLabel('Connecting…')
        layout.addWidget(self.status)
        toggle = QPushButton('Show / hide avatar')
        toggle.clicked.connect(lambda: window.setVisible(not window.isVisible()))
        layout.addWidget(toggle)
        self.click = QCheckBox('Click through avatar')
        self.click.toggled.connect(window.set_click_through)
        layout.addWidget(self.click)
        for label, action in [('Larger window', lambda: self.scale(1.1)), ('Smaller window', lambda: self.scale(0.9)),
                              ('Move to bottom right', self.reset_position)]:
            button = QPushButton(label)
            button.clicked.connect(action)
            layout.addWidget(button)
        for label, action in [('Zoom in', lambda: self.adjust_framing(zoom=0.1)),
                              ('Zoom out', lambda: self.adjust_framing(zoom=-0.1)),
                              ('Frame higher', lambda: self.adjust_framing(vertical=0.1)),
                              ('Frame lower', lambda: self.adjust_framing(vertical=-0.1)),
                              ('Reset waist-up framing', self.reset_framing)]:
            button = QPushButton(label)
            button.clicked.connect(action)
            layout.addWidget(button)
        self.mute = QPushButton('Microphone status unavailable')
        self.mute.setEnabled(False)
        self.mute.clicked.connect(self.toggle_mic)
        layout.addWidget(self.mute)
        self.stop = QPushButton('Stop speaking')
        self.stop.setEnabled(False)
        self.stop.clicked.connect(lambda: self.send({'type': 'stop'}))
        layout.addWidget(self.stop)
        quit_button = QPushButton('Quit overlay')
        quit_button.clicked.connect(QApplication.instance().quit)
        layout.addWidget(quit_button)
        self.tray = QSystemTrayIcon(self)
        self.tray.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_ComputerIcon))
        self.tray.setToolTip('Chassie — avatar controls')
        menu = QMenu(self)
        for label, callback in [('Controls', self.show), ('Show / hide avatar', toggle.click),
                                ('Stop speaking', self.stop.click), ('Quit overlay', QApplication.instance().quit)]:
            action = QAction(label, menu)
            action.triggered.connect(callback)
            menu.addAction(action)
        self.tray.setContextMenu(menu)
        self.tray.activated.connect(lambda reason: self.show() if reason == QSystemTrayIcon.ActivationReason.Trigger else None)
        if QSystemTrayIcon.isSystemTrayAvailable():
            self.tray.show()
        # Controls remain accessible even if no tray is provided by the desktop.
        self.socket = QWebSocket()
        self.socket.connected.connect(self.on_connected)
        self.socket.disconnected.connect(self.on_disconnected)
        self.socket.textMessageReceived.connect(self.receive)
        self.socket.errorOccurred.connect(lambda _: self.on_disconnected())
        window.readiness_changed.connect(self.announce_renderer)
        self.retry = QTimer(self)
        self.retry.setSingleShot(True)
        self.retry.timeout.connect(lambda: self.socket.open(QUrl(endpoint)))
        self.socket.open(QUrl(endpoint))
        self.save_timer = QTimer(self)
        self.save_timer.timeout.connect(self.save_geometry)
        self.save_timer.start(2000)
        for screen in QApplication.screens():
            screen.availableGeometryChanged.connect(self.recover_geometry)
        QApplication.instance().screenRemoved.connect(self.recover_geometry)
        self.restore_geometry()

    def on_connected(self):
        self.connected = True
        self.retry.stop()
        self.status.setText('Connected')
        self.stop.setEnabled(True)
        self.send({'type': 'hello', 'client': 'overlay'})
        self.announce_renderer()

    def announce_renderer(self, *_):
        self.send({'type': 'overlay_ready', 'ready': self.window.renderer_ready,
                   'model_id': self.window.entry.id if self.window.entry else None,
                   'expressions': list(self.window.loaded_expressions)})

    def on_disconnected(self):
        self.connected = False
        self.state.disconnected()
        self.status.setText('Assistant disconnected — reconnecting…')
        self.mute.setEnabled(False)
        self.stop.setEnabled(False)
        if not self.retry.isActive():
            self.retry.start(2000)

    def receive(self, raw):
        try:
            data = json.loads(raw)
            if not isinstance(data, dict):
                return
            self.state.receive(data, time.monotonic())
        except (ValueError, TypeError):
            return
        if self.state.mic_enabled is not None:
            self.mute.setEnabled(self.connected)
            self.mute.setText('Mute microphone' if self.state.mic_enabled else 'Enable microphone')

    def send(self, data):
        if self.connected:
            self.socket.sendTextMessage(json.dumps(data))

    def toggle_mic(self):
        if self.state.mic_enabled is not None:
            self.send({'type': 'set_mic', 'enabled': not self.state.mic_enabled})
            self.mute.setEnabled(False)  # Updated only by the backend acknowledgement.

    def apply_rect(self, rect):
        self.window.setGeometry(rect.x, rect.y, rect.width, rect.height)

    def reset_position(self):
        self.apply_rect(bottom_right(screens()[0], self.window.width(), self.window.height()))

    def scale(self, factor):
        self.apply_rect(bottom_right(screens()[0], max(120, round(self.window.width() * factor)),
                                     max(160, round(self.window.height() * factor))))
        self.save_geometry()

    def adjust_framing(self, **changes):
        self.window.framing = self.window.framing.adjust(**changes)
        self.window.update()
        self.save_geometry()

    def reset_framing(self):
        self.window.framing = Framing()
        self.window.update()
        self.save_geometry()

    def restore_geometry(self):
        rect = bottom_right(screens()[0])
        try:
            data = json.loads(self.settings_path.read_text())
            self.window.framing = Framing.from_settings(data)
            values = [data[k] for k in ('x', 'y', 'width', 'height')]
            if all(type(v) is int for v in values) and values[2] >= 120 and values[3] >= 160:
                rect = fit_to_screens(Rect(*values), screens())
        except (OSError, ValueError, KeyError, TypeError):
            pass
        self.apply_rect(rect)

    def recover_geometry(self, *_):
        if screens():
            r = self.window.geometry()
            self.apply_rect(fit_to_screens(Rect(r.x(), r.y(), r.width(), r.height()), screens()))

    def save_geometry(self):
        r = self.window.geometry()
        try:
            self.settings_path.write_text(json.dumps({'x': r.x(), 'y': r.y(), 'width': r.width(), 'height': r.height(),
                                                      'zoom': self.window.framing.zoom, 'vertical': self.window.framing.vertical}))
        except OSError:
            self.status.setText('Could not save avatar position')

    def closeEvent(self, event):
        if self.tray.isVisible():
            event.ignore()
            self.hide()
        else:
            event.ignore()  # Keep a recovery control available without a tray.
            self.showMinimized()

    def shutdown(self):
        self.save_geometry()
        self.save_timer.stop()
        self.retry.stop()
        self.socket.blockSignals(True)
        self.socket.close()
        self.tray.hide()


def run(args):
    app = QApplication([APPLICATION_ID])
    app.setApplicationName(APPLICATION_ID)
    app.setWindowIcon(QIcon(str(Path(__file__).resolve().parents[1]/'ui/public/chassie-icon.png')))
    app.setQuitOnLastWindowClosed(False)
    platform = app.platformName().lower()
    if platform not in ('xcb', 'windows'):
        raise RuntimeError(f'Overlay positioning/transparency is not verified for Qt platform {platform}; use X11/XWayland (QT_QPA_PLATFORM=xcb) or Windows')
    compositor_warning = None
    if platform == 'xcb':
        try:
            configure_hyprland()
        except RuntimeError as exc:
            compositor_warning = str(exc)
            logging.getLogger('overlay').warning(compositor_warning)
    from avatar.catalog import ModelCatalog, ModelSelection
    from desktop.studio import StudioControls
    catalog = ModelCatalog(args.model_dir)
    if not catalog.models: raise ValueError('No Live2D model found: put one inside model/ (see model/README.md)')
    selection = ModelSelection(catalog,Path(__file__).resolve().parents[1]/'.chassie/model-selection.json')
    selected = catalog.get(selection.state['model_id'])
    prepared = prepare_entry(selected,args.cache_dir)
    live2d.init()
    state = OverlayState()
    window = AvatarWindow(prepared, state, args.fps)
    window.entry = selected
    window.selection = selection.state
    controls = StudioControls(window,state,args.endpoint,args.cache_dir,catalog)
    from desktop.activation import activation_path, listen_for_activation
    activation = listen_for_activation(activation_path(Path(__file__).resolve().parents[1]),
                                       controls.activate_desktop, app)
    if compositor_warning:
        controls.status.setText(compositor_warning)

    def fail(message):
        QMessageBox.critical(window, 'Avatar renderer failed', message)
        app.exit(2)

    window.failed.connect(fail)
    window.show()
    try:
        return app.exec()
    finally:
        activation.close()
        controls.shutdown()
        window.cleanup()
        window.close()
        live2d.dispose()
