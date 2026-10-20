"""Native gaze regression: run manually in a desktop session; uses a simulated cursor."""
import json,sys,tempfile,time,os
from pathlib import Path
root=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(root))
os.environ['QT_QPA_PLATFORM']='xcb'
from desktop.qt_app import AvatarWindow
from desktop.compositor import APPLICATION_ID, configure_hyprland
from desktop.model import prepare_entry
from desktop.pointer import GAZE_RADIUS
from desktop.state import OverlayState,Framing
from avatar.catalog import ModelCatalog
from PySide6.QtCore import QTimer,QPoint
from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QCursor
import live2d.v3 as live2d

out=root/'.test-artifacts/pointer-idle';out.mkdir(exist_ok=True)
app=QApplication([APPLICATION_ID]);app.setApplicationName(APPLICATION_ID)
if app.platformName()=='xcb':configure_hyprland()
live2d.init();live2d.enableLog(False)
catalog=ModelCatalog();ids=['Model_4'];results=[];window=None;cursor=QPoint(-10000,-10000)
old=QCursor.pos;QCursor.pos=staticmethod(lambda:cursor)
cache=tempfile.TemporaryDirectory(prefix='chassie-pointer-')
def fail(exc):
    import traceback;traceback.print_exc()
    print(repr(exc),flush=True);results.append({'error':repr(exc)});app.exit(2)
def next_model():
    global window,cursor
    try:
        cursor=QPoint(-10000,-10000)
        if not ids:app.quit();return
        e=catalog.get(ids.pop(0))
        if window is None:
            window=AvatarWindow(prepare_entry(e,Path(cache.name)),OverlayState(),30)
            window.entry=e;window.resize(360,560);window.failed.connect(fail)
        else:window.select_entry(e,{},Path(cache.name))
        window.framing=Framing.for_model(e.id);window.show()
        QTimer.singleShot(1400,hover)
    except Exception as exc:fail(exc)
baseline={}
def eyes():
    m=window.model;params=m.GetParamIds()
    return [m.GetParameterValue(params.index(p)) for p in ('ParamEyeBallX','ParamEyeBallY')]
def hover():
    global cursor,baseline
    try:
        assert window.renderer_ready
        # Isolate gaze restoration from the separately tested headpat gesture;
        # hair on some models overlaps otherwise valid body hover points.
        window.pointer_interaction.head_parts=set()
        model=window.model;ratio=window.devicePixelRatioF();head=set(window.entry.head_parts)
        hits=[]
        for y in range(12,window.height()-12,12):
            for x in range(12,window.width()-12,12):
                parts=model.HitPart(x*ratio,y*ratio)
                if parts and not head.intersection(parts) and all(model.HitPart((x+dx)*ratio,(y+dy)*ratio) for dx,dy in ((-18,0),(18,0),(0,-18),(0,18))):hits.append((x,y))
        assert hits,('no body hit',window.entry.id)
        baseline=eyes()
        x,y=min(hits,key=lambda p:(p[0]-window.width()*.65)**2+(p[1]-window.height()*.8)**2)
        row=[px for px in range(0,window.width(),4) if model.HitPart(px*ratio,y*ratio)]
        x=max(row)+140  # Well outside the previous 64-pixel limit.
        assert x>=window.width() or not model.HitPart(x*ratio,y*ratio)
        cursor=window.mapToGlobal(QPoint(x,y));QTimer.singleShot(1000,check)
    except Exception as exc:fail(exc)
def check():
    global cursor
    try:
        local=window.mapFromGlobal(cursor);ratio=window.devicePixelRatioF()
        row=[px for px in range(0,window.width(),4) if window.model.HitPart(px*ratio,local.y()*ratio)]
        assert window.pointer_interaction.tracking, ('lost body hover',window.entry.id,
            (local.x(),local.y()),(window.width(),window.height()),max(row) if row else None)
        assert max(abs(a-b) for a,b in zip(eyes(),baseline))>.02, ('did not follow',eyes(),baseline)
        window.grabFramebuffer().save(str(out/f'{window.entry.id}-following.png'))
        cursor=window.mapToGlobal(QPoint(window.width()+GAZE_RADIUS+1,window.height()//2))
        QTimer.singleShot(1600,restore)
    except Exception as exc:fail(exc)
def restore():
    try:
        local=window.mapFromGlobal(cursor)
        assert not window.pointer_interaction.tracking, ('still tracking',
            (local.x(),local.y()),(window.width(),window.height()))
        assert not window.pointer_interaction.headpat
        assert window.pointer_interaction.gaze==(0.,0.)
        restored=eyes()
        assert max(abs(a-b) for a,b in zip(restored,baseline))<.03, (baseline,restored)
        result={'model':window.entry.id,'baseline_eyes':baseline,'restored_eyes':restored,'tracking':False}
        print(json.dumps(result),flush=True);results.append(result)
        window.grabFramebuffer().save(str(out/f'{window.entry.id}-idle.png'))
        QTimer.singleShot(100,next_model)
    except Exception as exc:fail(exc)
QTimer.singleShot(0,next_model);QTimer.singleShot(55000,lambda:fail('timeout'))
code=app.exec();QCursor.pos=old
if window:window.cleanup();window.close()
cache.cleanup();(out/'native-results.json').write_text(json.dumps(results,indent=2)+'\n')
sys.exit(code)
