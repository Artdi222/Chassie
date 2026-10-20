"""Model_4 native expression integration, no microphone/camera or AI requests."""
import json,os,sys,tempfile
from pathlib import Path
root=Path(__file__).resolve().parents[1];sys.path.insert(0,str(root))
os.environ['QT_QPA_PLATFORM']='xcb'
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QTimer,QPoint
from PySide6.QtGui import QCursor
import live2d.v3 as live2d
from avatar.catalog import ModelCatalog
from desktop.model import prepare_entry
from desktop.qt_app import AvatarWindow
from desktop.state import OverlayState,Framing
from desktop.compositor import APPLICATION_ID,configure_hyprland

app=QApplication([APPLICATION_ID]);app.setApplicationName(APPLICATION_ID)
if app.platformName()=='xcb':configure_hyprland()
live2d.init();live2d.enableLog(False)
cache=tempfile.TemporaryDirectory(prefix='chassie-reactions-');entry=ModelCatalog().get('Model_4')
state=OverlayState();window=AvatarWindow(prepare_entry(entry,Path(cache.name)),state,30)
window.entry=entry;window.selection={'auto':True};window.framing=Framing.for_model('Model_4');window.resize(360,560)
old=QCursor.pos;QCursor.pos=staticmethod(lambda:QPoint(-10000,-10000))
out=root/'.test-artifacts/model-reactions';out.mkdir(parents=True,exist_ok=True)
steps=iter(['happy','sad','thinking','sleepy','neutral']);current=None;results=[]
def fail(error):print(str(error),flush=True);app.exit(2)
window.failed.connect(fail)
def next_step():
    global current
    try:current=next(steps)
    except StopIteration:app.quit();return
    state.status='thinking' if current=='thinking' else 'idle' if current=='neutral' else 'speaking'
    state.emotion=current
    QTimer.singleShot(1000,check)
def check():
    try:
        assert window.renderer_ready
        ids=window.model.GetParamIds()
        values={p:window.model.GetParameterValue(ids.index(p)) for p in ['ParamMouthForm','ParamBrowLY','ParamBrowRY','ParamEyeLOpen','ParamEyeROpen','ParamCheek']}
        if current=='happy':assert values['ParamMouthForm']>.6,values
        elif current=='sad':assert values['ParamMouthForm']<-.3,values
        elif current=='thinking':assert values['ParamBrowLY']-values['ParamBrowRY']>.25,values
        elif current=='sleepy':assert values['ParamEyeLOpen']<.5 and values['ParamEyeROpen']<.5,values
        else:assert not window.driver.active
        window.grabFramebuffer().save(str(out/f'Model_4-{current}.png'))
        results.append({'mood':current,'parameters':values});QTimer.singleShot(0,next_step)
    except Exception as exc:fail(repr(exc))
window.show();QTimer.singleShot(1500,next_step);QTimer.singleShot(30000,lambda:fail('timeout'))
code=app.exec();QCursor.pos=old
window.cleanup();window.close();cache.cleanup()
(out/'results.json').write_text(json.dumps(results,indent=2))
print(json.dumps({'passed':len(results)==5,'moods':[r['mood'] for r in results]}),flush=True)
sys.exit(code)
