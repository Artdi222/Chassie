"""Bounded real-render check; captures only this process's avatar framebuffer.

Run: QT_QPA_PLATFORM=xcb python -m desktop.smoke --output .test-artifacts/overlay.png
No microphone/camera access or full-desktop capture. A local test server is optional.
"""
import argparse
import json
import os
import subprocess
from pathlib import Path
import time


def main():
    parser = argparse.ArgumentParser(description='Render the real model, capture its own framebuffer and exit')
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--emotion', default='happy')
    parser.add_argument('--model-id', default='Model_4')
    parser.add_argument('--exercise-controls', action='store_true')
    parser.add_argument('--endpoint', default='ws://127.0.0.1:9/ws', help='Optional local test server for controls')
    parser.add_argument('--expect-emotion', help='Fail unless the final rendered state matches this emotion')
    parser.add_argument('--verify-hyprland', action='store_true', help='Assert live compositor pin/blur state for this process only')
    args = parser.parse_args()
    from brain.emotion_parser import VALID_EMOTIONS
    if args.emotion not in VALID_EMOTIONS:
        parser.error('Unsupported emotion')
    from PySide6.QtCore import QTimer
    from PySide6.QtGui import QImage
    from PySide6.QtWidgets import QApplication
    import live2d.v3 as live2d
    from desktop.qt_app import AvatarWindow, Controls, screens
    from desktop.state import OverlayState, bottom_right, validate_endpoint
    from desktop.compositor import APPLICATION_ID, configure_hyprland
    validate_endpoint(args.endpoint)

    root = Path(__file__).resolve().parents[1]
    app = QApplication([APPLICATION_ID])
    app.setApplicationName(APPLICATION_ID)
    if app.platformName() == 'xcb':
        configure_hyprland()
    from avatar.catalog import ModelCatalog
    from desktop.model import prepare_entry
    entry=ModelCatalog().get(args.model_id)
    prepared=prepare_entry(entry,root/'.chassie/overlay')
    live2d.init()
    live2d.enableLog(False)
    # Speaking keeps the requested emotion; idle/disconnected show Tian Muzi neutral.
    state = OverlayState(emotion=args.emotion, mouth=0.25, updated_at=time.monotonic(), status='speaking')
    window = AvatarWindow(prepared, state, 30)
    if entry:
        window.entry=entry
        from desktop.state import Framing
        window.framing=Framing.for_model(entry.id)
        window.selection={'auto':True}
    rect = bottom_right(screens()[0], 300, 400)
    window.setGeometry(rect.x, rect.y, rect.width, rect.height)
    outcome = {'rendered': False, 'platform': app.platformName(), 'emotion': args.emotion}

    def fail(message):
        outcome['error'] = message
        app.exit(2)

    def capture():
        try:
            if window.model is None:
                fail('No live Cubism model was created')
                return
            if args.expect_emotion and state.emotion != args.expect_emotion:
                raise RuntimeError(f'Expected {args.expect_emotion}, received {state.emotion}')
            if args.verify_hyprland:
                clients=json.loads(subprocess.check_output(['hyprctl','clients','-j'],text=True,timeout=3))
                owned=[c for c in clients if c['pid']==os.getpid() and c['title']=='Chassie']
                if len(owned)!=1:
                    raise RuntimeError('Expected exactly one owned avatar window')
                client=owned[0]
                properties={name:subprocess.check_output(['hyprctl','getprop','address:'+client['address'],name],text=True,timeout=3).strip()
                            for name in ('no_blur','no_shadow','border_size','rounding')}
                outcome['compositor']={'class':client['class'],'pinned':client['pinned'],'floating':client['floating'],**properties}
                if client['class']!=APPLICATION_ID or not client['pinned'] or not client['floating']:
                    raise RuntimeError('Avatar identity/floating/pin rules did not apply')
                if properties['no_blur'] not in ('true','1') or properties['no_shadow'] not in ('true','1'):
                    raise RuntimeError('Avatar blur/shadow rules did not apply: '+str(properties))
                # Circular recovery controls are intentionally pinned with the avatar.
            state.updated_at = time.monotonic()
            frame = window.grabFramebuffer().convertToFormat(QImage.Format.Format_RGBA8888)
            if frame.isNull():
                raise RuntimeError('Empty framebuffer')
            pixels = bytes(frame.constBits())
            alpha = pixels[3::4]
            opaque = sum(value > 0 for value in alpha)
            transparent = sum(value == 0 for value in alpha)
            if opaque == 0 or transparent == 0:
                raise RuntimeError(f'Expected both avatar and transparent pixels, got opaque={opaque}, transparent={transparent}')
            args.output.parent.mkdir(parents=True, exist_ok=True)
            if not frame.save(str(args.output)):
                raise RuntimeError('Could not save framebuffer')
            outcome.update(rendered=True, emotion=state.emotion, width=frame.width(), height=frame.height(),
                           nontransparent_pixels=opaque, transparent_pixels=transparent,
                           renderer_ready=window.renderer_ready, loaded_expressions=len(window.loaded_expressions),
                           model_parameters=window.model.GetParameterCount(), screenshot=str(args.output))
            app.exit(0)
        except Exception as exc:
            fail(str(exc))

    controls = None
    window.failed.connect(fail)
    window.show()
    if args.exercise_controls:
        controls = Controls(window, state, args.endpoint, root / '.chassie' / 'overlay' / 'smoke-window.json')
        controls.show()
        QTimer.singleShot(500, lambda: controls.click.setChecked(True))
        QTimer.singleShot(1000, lambda: controls.click.setChecked(False))
        QTimer.singleShot(1500, window.hide)
        QTimer.singleShot(1750, window.show)
        QTimer.singleShot(2000, lambda: controls.scale(1.1))
        outcome['controls_exercised'] = ['click-through flags', 'hide/show', 'resize', 'local WebSocket endpoint']
    QTimer.singleShot(3500, capture)
    QTimer.singleShot(10000, lambda: fail('Render smoke timed out'))
    try:
        result = app.exec()
    finally:
        if controls:
            controls.shutdown()
        window.cleanup()
        window.close()
        live2d.dispose()
    print(json.dumps(outcome, indent=2))
    return result


if __name__ == '__main__':
    raise SystemExit(main())
