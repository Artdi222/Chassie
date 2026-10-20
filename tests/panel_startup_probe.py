import sys
if sys.platform.startswith("linux"):
    import resource
    resource.setrlimit(resource.RLIMIT_CORE,(0,0))
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
# Match the production entrypoint: qt_app must be the first native import.
import desktop.qt_app
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QTimer
from PySide6.QtWebEngineWidgets import QWebEngineView
app=QApplication(['chassie-panel-startup-check'])
view=QWebEngineView()
def loaded(ok):
    if not ok:app.exit(2);return
    view.page().runJavaScript('1+1',lambda value:(print('PANEL_READY',value,flush=True),app.exit(0 if value==2 else 3)))
view.loadFinished.connect(loaded)
view.setHtml('<html><body>Panel startup check</body></html>')
QTimer.singleShot(12000,lambda:app.exit(4))
raise SystemExit(app.exec())
