"""Headless integration: repeated launcher activation restores a hidden Qt window."""
import sys
from pathlib import Path
from types import SimpleNamespace
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import desktop.qt_app  # Preserve production native import order.
from desktop.studio import StudioControls
from desktop.activation import listen_for_activation, request_activation
from PySide6.QtWidgets import QApplication,QWidget
from PySide6.QtCore import QTimer
app=QApplication(['chassie-activation-check']);app.setQuitOnLastWindowClosed(False)
window=QWidget();window.hide();activations=[]
controls=SimpleNamespace(window=window,recover_geometry=lambda:None)
def activate():
    StudioControls.activate_desktop(controls)
    assert window.isVisible()
    activations.append(True)
    if len(activations)==1:
        window.hide()
        QTimer.singleShot(0,request)
    else:
        print('DESKTOP_RESTORED_TWICE',flush=True);app.quit()
server=listen_for_activation(Path(sys.argv[1]),activate,app)
def request():
    if not request_activation(Path(sys.argv[1]),timeout=.2):app.exit(2)
QTimer.singleShot(0,request)
QTimer.singleShot(5000,lambda:app.exit(3))
try: raise SystemExit(app.exec())
finally: server.close()
