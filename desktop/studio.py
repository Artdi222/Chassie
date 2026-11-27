"""Desktop companion chrome: radial actions and floating local application panels."""
import json
import time
from pathlib import Path

from PySide6.QtCore import Qt, QTimer, QUrl, QSize, QByteArray, QRect, QObject, QEvent
from PySide6.QtGui import QAction, QIcon, QPixmap, QPainter, QColor, QPen, QShortcut, QKeySequence
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWebSockets import QWebSocket
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWidgets import (QApplication, QWidget, QVBoxLayout, QHBoxLayout, QLabel,
                               QPushButton, QToolButton, QAbstractButton, QSystemTrayIcon, QMenu)

from desktop.state import Rect, bottom_right, fit_to_screens, Framing, left_arc, scaled_window

ICON_PATHS = {
    'chat':'<path d="M20 11a8 8 0 0 1-8 8H5l-3 3V11a9 9 0 0 1 18 0Z"/><path d="M7 10h8m-8 4h5"/>',
    'settings':'<path d="M9 3h6l1 3 3 1 2 5-2 5-3 1-1 3H9l-1-3-3-1-2-5 2-5 3-1Z"/><circle cx="12" cy="12" r="3"/>',
    'models':'<circle cx="12" cy="12" r="9"/><path d="M8 9v1m8-1v1m-8 5q4 4 8 0"/>',
    'mic':'<rect x="9" y="3" width="6" height="11" rx="3"/><path d="M5 11a7 7 0 0 0 14 0m-7 7v3"/>',
    'mic_off':'<path d="M15 9.5V6a3 3 0 0 0-5.6-1.5M9 9v2a3 3 0 0 0 4.7 2.5M5 11a7 7 0 0 0 11.5 5.4M19 11a7 7 0 0 1-.4 2.3M12 18v3M4 4l16 16"/>',
    'stop':'<rect x="6" y="6" width="12" height="12" rx="3"/>',
    'web':'<rect x="3" y="4" width="18" height="16" rx="3"/><path d="M3 9h18M7 6.5h.1m3 0h.1"/>',
}


def icon(name):
    data=f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="#5e4749" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round">{ICON_PATHS[name]}</svg>'
    pix=QPixmap(48,48); pix.fill(Qt.GlobalColor.transparent)
    painter=QPainter(pix); QSvgRenderer(QByteArray(data.encode())).render(painter); painter.end()
    return QIcon(pix)


def screens():
    return [Rect(r.x(),r.y(),r.width(),r.height()) for s in QApplication.screens() for r in [s.availableGeometry()]]


class FloatingPanel(QWidget):
    def __init__(self,title,url,owner,*,transparent=False):
        super().__init__(owner, Qt.WindowType.Tool)
        self.setWindowTitle('Chassie — '+title)
        self.setWindowFlags(Qt.WindowType.Tool | Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.FramelessWindowHint)
        if transparent:
            self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        background='transparent' if transparent else '#ffffff'
        self.setStyleSheet(f'QWidget{{background:{background};color:#2e2124;font-size:14px;}}'
                           'QLabel#panelTitle{font-size:13px;font-weight:600;color:#6a5559;}'
                           'QPushButton#panelClose{border:0;border-radius:14px;min-width:28px;max-width:28px;min-height:28px;max-height:28px;'
                           'background:transparent;color:#6a5559;font-size:15px;}'
                           'QPushButton#panelClose:hover{background:#f6e9ee;color:#2e2124;}')
        self.drag = None
        layout=QVBoxLayout(self);layout.setContentsMargins(1,1,1,1);layout.setSpacing(0)
        if not transparent:
            bar=QHBoxLayout();bar.setContentsMargins(20,10,10,0)  # Drag the panel by this strip.
            bar.addStretch()  # The page shows the title; this strip is for dragging and closing.
            close=QPushButton('✕');close.setObjectName('panelClose');close.setToolTip('Close');close.setAccessibleName('Close')
            close.setCursor(Qt.CursorShape.PointingHandCursor);close.clicked.connect(self.hide);bar.addWidget(close)
            layout.addLayout(bar)
        else:
            self.close_shortcut=QShortcut(QKeySequence('Escape'),self)
            self.close_shortcut.activated.connect(self.hide)
        self.web=QWebEngineView(self)
        if transparent:
            self.web.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
            self.web.page().setBackgroundColor(QColor(Qt.GlobalColor.transparent))
        self.web.setUrl(QUrl(url))
        layout.addWidget(self.web)

    def mousePressEvent(self,event):
        if event.button()==Qt.MouseButton.LeftButton:self.drag=event.globalPosition().toPoint()-self.pos()

    def mouseMoveEvent(self,event):
        if self.drag is None or not event.buttons()&Qt.MouseButton.LeftButton:return
        # Same XWayland race as the avatar: let the compositor move the panel.
        handle=self.windowHandle()
        if handle is not None and handle.startSystemMove():self.drag=None;return
        self.move(event.globalPosition().toPoint()-self.drag)

    def mouseReleaseEvent(self,event):self.drag=None


class BubbleButton(QAbstractButton):
    """An independent alpha window; there is no rectangular menu surface."""
    def __init__(self,name,title,owner):
        super().__init__(None)
        self.setWindowFlags(Qt.WindowType.Tool | Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setWindowTitle('Chassie bubble '+name)
        self.setObjectName(name)
        self.setFixedSize(44,44)
        self.setIcon(icon(name));self.setIconSize(QSize(20,20))
        self.setToolTip(title);self.setAccessibleName(title)
        self.setMouseTracking(True)
        self.on_hover=None
        self.winId()
        self.windowHandle().setTransientParent(owner.windowHandle())

    def hitButton(self,pos):
        return (pos.x()-22)**2+(pos.y()-22)**2<=21**2

    def paintEvent(self,event):
        painter=QPainter(self)
        painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Source)
        painter.fillRect(self.rect(),Qt.GlobalColor.transparent)
        painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(QPen(QColor('#efe2dc'),1))
        painter.setBrush(QColor('#f1e5e0' if self.underMouse() or self.isDown() else '#ffffff'))
        painter.drawEllipse(self.rect().adjusted(1,1,-1,-1))
        self.icon().paint(painter,QRect(12,12,20,20))

    def enterEvent(self,event):
        self.update()
        if self.on_hover:self.on_hover(self)
    def leaveEvent(self,event):
        self.update()
        if self.on_hover:self.on_hover(None)


class BubbleHint(QLabel):
    """What a bubble does, shown beside it while hovered; never takes the mouse."""
    def __init__(self):
        super().__init__(None)
        self.setWindowFlags(Qt.WindowType.Tool | Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint
                            | Qt.WindowType.WindowTransparentForInput)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setWindowTitle('Chassie hint')
        # Stylesheet backgrounds are skipped on translucent top-level windows: paint the pill.
        self.setStyleSheet('QLabel{background:transparent;color:#f8eee8;padding:6px 13px;font-size:13px;font-weight:500;}')

    def paintEvent(self,event):
        painter=QPainter(self)
        painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Source)
        painter.fillRect(self.rect(),Qt.GlobalColor.transparent)
        painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(Qt.PenStyle.NoPen);painter.setBrush(QColor(43,31,34,240))
        radius=self.height()/2;painter.drawRoundedRect(self.rect(),radius,radius)
        painter.end()
        super().paintEvent(event)

    def show_beside(self,button,text):
        self.setText(text);self.adjustSize()
        r=button.geometry();screen=button.screen().availableGeometry()
        x=r.x()-self.width()-8
        if x<screen.x()+4:x=r.right()+8  # Bubbles hug the screen edge: show on the other side.
        self.move(x,r.center().y()-self.height()//2)
        self.show();self.raise_()


class StudioControls(QObject):
    def __init__(self,window,state,endpoint,cache_dir,catalog):
        super().__init__(window)
        window.studio_controls=self
        self.window,self.state,self.endpoint,self.cache_dir,self.catalog=window,state,endpoint,cache_dir,catalog
        self.base_url=endpoint.replace('ws://','http://').removesuffix('/ws')
        self.connected=False
        self.panels={}
        self.model_frames={}
        self.settings_path=cache_dir/'window.json'
        self.bubbles={}
        window.winId()
        self.hint=BubbleHint()
        for name,title in [('chat','Conversation'),('mic','Microphone'),('models','Customize her look'),('settings','Settings'),('stop','Stop her reply')]:
            b=BubbleButton(name,title,window)
            b.on_hover=self.show_hint
            b.clicked.connect(lambda checked=False,n=name:self.action(n));self.bubbles[name]=b
        self.update_mic()
        self.status=QLabel('')
        from desktop.bubble import SpeechBubble
        self.subtitle=SpeechBubble(window)
        self.tray=QSystemTrayIcon(QIcon(str(Path(__file__).resolve().parents[1]/'ui/public/chassie-icon.png')),self);self.tray.setToolTip('Chassie')
        menu=QMenu();self.tray_menu=menu
        for title,callback in [('Show controls',self.toggle),('Conversation',lambda:self.action('chat')),('Customize',lambda:self.action('models')),('Settings',lambda:self.action('settings')),('Add a model…',lambda:self.action('models')),('Open web studio',self.open_web),('Show / hide model',lambda:window.setVisible(not window.isVisible())),('Click through avatar',self.click_through),('Stop reply',lambda:self.send({'type':'stop'})),('Quit Chassie',QApplication.instance().quit)]:
            action=QAction(title,menu);action.triggered.connect(callback);menu.addAction(action)
        self.tray.setContextMenu(menu);self.tray.activated.connect(lambda reason:self.toggle() if reason==QSystemTrayIcon.ActivationReason.Trigger else None);self.tray.show()
        window.installEventFilter(self)
        window.clicked.connect(self.toggle);window.relocated.connect(self.reposition)
        window.readiness_changed.connect(self.announce_renderer)
        self.socket=QWebSocket();self.socket.connected.connect(self.on_connected);self.socket.disconnected.connect(self.on_disconnected)
        self.socket.textMessageReceived.connect(self.receive)
        self.retry=QTimer(self);self.retry.setSingleShot(True);self.retry.timeout.connect(lambda:self.socket.open(QUrl(endpoint)))
        self.socket.open(QUrl(endpoint))
        self.restore_geometry()
        self.timer=QTimer(self);self.timer.timeout.connect(self.save_geometry);self.timer.start(2000)
        self.native_subtitle_generation=-1
        for screen in QApplication.screens():screen.availableGeometryChanged.connect(self.recover_geometry)
        QApplication.instance().screenRemoved.connect(self.recover_geometry)

    def open_web(self):
        from PySide6.QtGui import QDesktopServices
        QDesktopServices.openUrl(QUrl(self.base_url))

    def activate_desktop(self):
        self.window.showNormal()
        self.recover_geometry()
        self.window.raise_()
        self.window.activateWindow()

    def click_through(self):
        # Keep a clickable recovery menu while the avatar stops receiving clicks.
        self.window.set_click_through(not self.window.click_through)
        self.reposition();self.show();self.raise_()

    def eventFilter(self,watched,event):
        if watched is self.window and event.type()==QEvent.Type.Hide:self.hide()
        return False

    def isVisible(self):return any(b.isVisible() for b in self.bubbles.values())

    def setVisible(self,visible):
        if not visible:self.hint.hide()
        for button in self.bubbles.values():
            if visible:button.windowHandle().setTransientParent(self.window.windowHandle())
            button.setVisible(visible)
            if visible:button.raise_()

    def show(self):self.setVisible(True)
    def hide(self):self.setVisible(False)
    def raise_(self):
        for button in self.bubbles.values():button.raise_()

    def toggle(self):
        self.reposition();self.setVisible(not self.isVisible())
        if self.isVisible():self.raise_()

    def reposition(self):
        r=self.window.geometry()
        screen=self.window.screen().availableGeometry()
        rects=left_arc(Rect(r.x(),r.y(),r.width(),r.height()),
                       Rect(screen.x(),screen.y(),screen.width(),screen.height()))
        for button,rect in zip(self.bubbles.values(),rects):
            button.move(rect.x,rect.y)
        if 'chat' in self.panels and self.panels['chat'].isVisible():self.place_panel('chat')
        if self.subtitle.isVisible():self.place_subtitle()

    def hint_text(self,name):
        if name=='mic':
            return {None:'Microphone unavailable',True:'Microphone on · click to mute',
                    False:'Microphone off · click to talk'}[self.state.mic_enabled]
        return self.bubbles[name].accessibleName()

    def show_hint(self,button):
        if button is None or not button.isVisible():self.hint.hide();return
        self.hint.show_beside(button,self.hint_text(button.objectName()))

    def update_mic(self):
        """The mic bubble shows the live microphone state."""
        b=self.bubbles['mic'];text=self.hint_text('mic')
        b.setIcon(icon('mic_off' if self.state.mic_enabled is False else 'mic'));b.setToolTip(text);b.update()
        if self.hint.isVisible() and b.underMouse():self.hint.show_beside(b,text)

    def action(self,name):
        if name=='stop':self.send({'type':'stop'});return
        if name=='mic':
            if self.state.mic_enabled is not None:self.send({'type':'set_mic','enabled':not self.state.mic_enabled})
            return
        if name=='chat' and name in self.panels and self.panels[name].isVisible():
            self.panels[name].hide()
            return
        if name not in self.panels:
            titles={'chat':'Conversation','models':'Customize','settings':'Settings'}
            self.panels[name]=FloatingPanel(titles[name],self.base_url+'/?panel='+name,self.window,transparent=name=='chat')
        self.place_panel(name);self.panels[name].show();self.panels[name].raise_();self.panels[name].activateWindow()

    def resize_window(self,factor):
        """Grow or shrink the avatar's space, keeping its bottom-right corner where the owner put it."""
        r=self.window.geometry();screen=self.window.screen().availableGeometry()
        rect=scaled_window(Rect(r.x(),r.y(),r.width(),r.height()),factor,
                           Rect(screen.x(),screen.y(),screen.width(),screen.height()))
        self.window.setGeometry(rect.x,rect.y,rect.width,rect.height)
        self.reposition();self.save_geometry()

    def adjust_frame(self,**values):
        self.window.framing=self.window.framing.adjust(**values);self.window.update();self.save_geometry()

    def reset_frame(self):
        self.window.framing=Framing.for_model(self.window.entry.id);self.window.update();self.save_geometry()

    def focused_chat_centre(self):
        """Centre of the chat panel while the owner is using it (it has keyboard focus)."""
        panel=self.panels.get('chat')
        if panel is None or not panel.isVisible() or not panel.isActiveWindow(): return None
        c=panel.geometry().center()
        return (c.x(),c.y())

    def place_panel(self,name):
        screen=screens()[0];r=self.window.geometry()
        width=min(380 if name=='chat' else 650,screen.width-32)
        height=min(480 if name=='chat' else 780,screen.height-60)
        if name=='chat':
            x=max(screen.x+16,min(r.x()-width+55,screen.x+screen.width-width-16))
            y=max(screen.y+16,min(r.y()-height+150,screen.y+screen.height-height-16))
        else:x=screen.x+(screen.width-width)//2;y=screen.y+(screen.height-height)//2
        self.panels[name].setGeometry(x,y,width,height)

    def place_subtitle(self):
        r=self.window.geometry();s=screens()[0];w=self.subtitle.width()
        # Centred over her, tail down; kept on screen (it may overlap her head when she fills the screen height).
        self.subtitle.move(max(s.x,min(r.center().x()-w//2,s.x+s.width-w)),max(s.y,r.y()-self.subtitle.height()+6))

    def on_connected(self):
        self.connected=True;self.retry.stop();self.announce_renderer()

    def announce_renderer(self,*_):
        if self.window.entry:self.send({'type':'overlay_ready','ready':self.window.renderer_ready,'model_id':self.window.entry.id,'expressions':list(self.window.loaded_expressions)})

    def on_disconnected(self):
        self.connected=False;self.state.disconnected();self.subtitle.hide();self.native_subtitle_generation=-1;self.update_mic()
        if not self.retry.isActive():self.retry.start(2000)

    def send_appearance(self,model_id):
        """One picture of the avatar alone (transparent window: nothing else on screen) to describe her look."""
        if not self.window.entry or self.window.entry.id!=model_id:return
        from desktop.snapshot import avatar_png
        image=avatar_png(self.window.grabFramebuffer())
        if image:self.send({'type':'avatar_snapshot','model_id':model_id,'image':'data:image/png;base64,'+image})

    def send(self,data):
        if self.connected:self.socket.sendTextMessage(json.dumps(data))

    def receive(self,raw):
        try:
            data=json.loads(raw)
            if not isinstance(data,dict):return
            self.state.receive(data,time.monotonic())
            if data.get('type')=='settings':self.update_mic()
            if data.get('type')=='model_catalog' and {m['id'] for m in data.get('models',[])}!=set(self.catalog.models):
                self.catalog.reload()  # A model was added from the Customize panel.
            if data.get('type')=='model_state':
                if data['model_id'] not in self.catalog.models:self.catalog.reload()
                previous=self.window.entry.id if self.window.entry else None
                if previous != data['model_id']:
                    if previous:self.model_frames[previous]={'zoom':self.window.framing.zoom,'vertical':self.window.framing.vertical}
                    saved=self.model_frames.get(data['model_id'])
                    self.window.framing=Framing.from_settings(saved) if saved else Framing.for_model(data['model_id'])
                self.window.select_entry(self.catalog.get(data['model_id']),data,self.cache_dir)
                self.announce_renderer()
            elif data.get('type')=='appearance_needed' and self.window.entry and data.get('model_id')==self.window.entry.id:
                QTimer.singleShot(2000,lambda model_id=data['model_id']:self.send_appearance(model_id))  # Let her settle first.
            elif data.get('type')=='restart':
                from brain.updates import RESTART_CODE
                QApplication.instance().exit(RESTART_CODE)  # Updated: launch.py starts the new version.
            elif data.get('type')=='avatar_window':
                {'smaller':lambda:self.resize_window(1/1.15),'larger':lambda:self.resize_window(1.15),
                 'zoom_out':lambda:self.adjust_frame(zoom=-.15),'zoom_in':lambda:self.adjust_frame(zoom=.15),
                 'frame_up':lambda:self.adjust_frame(vertical=.15),'frame_down':lambda:self.adjust_frame(vertical=-.15),
                 'reset':self.reset_frame,'click_through':self.click_through}.get(data.get('action'),lambda:None)()
            elif data.get('type')=='subtitle' and data.get('generation',-1)>=self.native_subtitle_generation:
                self.native_subtitle_generation=data['generation'];self.subtitle.setText(data.get('text',''))
                self.subtitle.setVisible(bool(data.get('text')));self.place_subtitle()
        except (ValueError,KeyError,TypeError,OSError) as exc:
            self.status.setText(str(exc))

    def restore_geometry(self):
        rect=bottom_right(screens()[0],400,540)
        self.window.framing=Framing.for_model(self.window.entry.id)
        try:
            data=json.loads(self.settings_path.read_text())
            self.model_frames=data.get('model_frames',{})
            saved=self.model_frames.get(self.window.entry.id)
            if saved:self.window.framing=Framing.from_settings(saved)
            rect=fit_to_screens(Rect(*(data[k] for k in ('x','y','width','height'))),screens())
        except (OSError,ValueError,KeyError,TypeError):pass
        self.window.setGeometry(rect.x,rect.y,rect.width,rect.height)

    def recover_geometry(self,*_):
        r=self.window.geometry();rect=fit_to_screens(Rect(r.x(),r.y(),r.width(),r.height()),screens())
        self.window.setGeometry(rect.x,rect.y,rect.width,rect.height);self.reposition()

    def save_geometry(self):
        r=self.window.geometry()
        if self.window.entry:self.model_frames[self.window.entry.id]={'zoom':self.window.framing.zoom,'vertical':self.window.framing.vertical}
        self.settings_path.write_text(json.dumps({'model_frames':self.model_frames,'x':r.x(),'y':r.y(),'width':r.width(),'height':r.height(),'zoom':self.window.framing.zoom,'vertical':self.window.framing.vertical}))

    def shutdown(self):
        self.save_geometry();self.timer.stop();self.retry.stop();self.socket.blockSignals(True);self.socket.close();self.tray.hide();self.subtitle.close();self.hint.close()
        for panel in self.panels.values():panel.close()
        for button in self.bubbles.values():button.close()
