import sys, json, tempfile, subprocess
from pathlib import Path
root=Path(__file__).resolve().parents[1];sys.path.insert(0,str(root))
from desktop.qt_app import run,AvatarWindow
from PySide6.QtCore import Qt,QTimer,QPoint
from PySide6.QtWidgets import QApplication,QWidget
from PySide6.QtTest import QTest,QSignalSpy
from desktop.studio import StudioControls
from PySide6.QtGui import QImage
from types import SimpleNamespace

original_exec=QApplication.exec
outcome={'clicked':[]}
def checked_exec(self):
    app=QApplication.instance()
    controls=next(w.studio_controls for w in app.allWidgets() if isinstance(w,AvatarWindow))
    avatar=controls.window
    actions=list(controls.bubbles)
    def fail(exc):
        outcome['error']=repr(exc);outcome.pop('_capture_rect',None);print(json.dumps(outcome),flush=True);app.exit(2)
    def click_next():
        try:
            if actions:
                name=actions.pop(0)
                print('CLICK',name,flush=True)
                QTest.mouseClick(controls.bubbles[name],Qt.MouseButton.LeftButton)
                assert controls.isVisible(),'Menu unexpectedly dismissed'
                if name!='stop':
                    panel=controls.panels[name]
                    assert panel.isVisible()
                    assert panel.parentWidget() is avatar
                    assert panel.windowHandle().transientParent() is avatar.windowHandle()
                assert avatar.isVisible() and avatar.renderer_ready
                outcome['clicked'].append(name)
                QTimer.singleShot(1500,click_next)
            else:
                (root/'.test-artifacts').mkdir(exist_ok=True)
                assert not any(c['title']=='Chassie controls' for c in json.loads(subprocess.check_output(['hyprctl','clients','-j'])))
                clients=json.loads(subprocess.check_output(['hyprctl','clients','-j']))
                owned=[c for c in clients if c['pid']==__import__('os').getpid()]
                menus=[c for c in owned if c['title'].startswith('Chassie bubble ')]
                assert len(menus)==5
                assert all(c['size']==[44,44] for c in menus)
                menu=menus[0]
                outcome['compositor']={k:menu[k] for k in ('floating','pinned','at','size')}
                for key in ('no_blur','no_shadow'):
                    value=subprocess.check_output(['hyprctl','getprop','address:'+menu['address'],key],text=True).strip()
                    assert value in ('true','1'),(key,value)
                    outcome['compositor'][key]=value
                outcome['transient_above_avatar']=all(b.windowHandle().transientParent() is avatar.windowHandle() for b in controls.bubbles.values())
                assert outcome['transient_above_avatar']
                avatar.hide();assert not controls.isVisible()
                avatar.show();controls.show()
                assert all(b.isVisible() for b in controls.bubbles.values())
                print(json.dumps(outcome),flush=True);app.quit()
        except Exception as exc:fail(exc)
    def capture_desktop():
        try:
            rect=outcome.pop('_capture_rect')
            path=root/'.test-artifacts/desktop-bubbles-composited.png'
            path.parent.mkdir(exist_ok=True)
            subprocess.run(['grim','-g',f'{rect.x()},{rect.y()} {rect.width()}x{rect.height()}',str(path)],check=True)
            captured=QImage(str(path))
            bubbles=list(controls.bubbles.values())
            # Upper gaps and the outer corner are clear of the moving model.
            first,second=bubbles[:2]
            samples=[((first.geometry().center().x()+second.geometry().center().x())//2,
                      (first.geometry().center().y()+second.geometry().center().y())//2),
                     (first.x()+2,first.y()+2)]
            for x,y in samples:
                color=captured.pixelColor(x-rect.x(),y-rect.y())
                assert all(abs(a-b)<8 for a,b in zip(color.getRgb()[:3],(54,86,108))),('Opaque button or gap',color.name(),x,y)
            outcome['compositor_gaps_transparent']=True
            QTimer.singleShot(100,click_next)
        except Exception as exc:fail(exc)

    def start():
        try:
            if not controls.connected or not avatar.renderer_ready or avatar.selection.get('model_id')!='Model_1':
                QTimer.singleShot(300,start);return
            print('AVATAR CLICK',flush=True)
            spy=QSignalSpy(avatar.clicked)
            before=str(avatar.geometry())
            QTest.mouseClick(avatar,Qt.MouseButton.LeftButton,pos=QPoint(160,180))
            assert controls.isVisible(),(spy.count(),before,str(avatar.geometry()),avatar.isVisible())
            rect=avatar.geometry()
            for button in controls.bubbles.values():rect=rect.united(button.geometry())
            rect=rect.adjusted(-8,-8,8,8)
            subprocess.run(['hyprctl','eval', '''if not _G.chassie_test_backdrop then _G.chassie_test_backdrop=hl.window_rule({name='chassie-test-backdrop',match={class='^chassie-overlay$',title='^Chassie transparency test$'},float=true,opaque=true,opacity='1.0 override',no_blur=true,no_shadow=true,rounding=0,border_size=0}) end'''],check=True,capture_output=True)
            backdrop=QWidget(None,Qt.WindowType.Tool|Qt.WindowType.FramelessWindowHint|Qt.WindowType.WindowStaysOnTopHint)
            backdrop.setWindowTitle('Chassie transparency test')
            backdrop.setStyleSheet('background:#36566c;')
            backdrop.setGeometry(rect);backdrop.show()
            avatar.windowHandle().setTransientParent(backdrop.windowHandle())
            avatar.raise_();controls.raise_()
            controls.test_backdrop=backdrop
            outcome['_capture_rect']=rect
            QTimer.singleShot(1200,capture_desktop)
        except Exception as exc:fail(exc)
    QTimer.singleShot(3000,start)
    QTimer.singleShot(25000,lambda:fail('Timeout'))
    return original_exec()
QApplication.exec=checked_exec
with tempfile.TemporaryDirectory(prefix='chassie-arc-') as cache:
    args=SimpleNamespace(model_dir=root/'model',cache_dir=Path(cache),endpoint=sys.argv[1] if len(sys.argv)>1 else 'ws://127.0.0.1:8768/ws',fps=30)
    raise SystemExit(run(args))
