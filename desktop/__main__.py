"""Optional entrypoint: python -m desktop --check, then python -m desktop."""
import argparse
import importlib.util
from pathlib import Path
import sys

from desktop.state import validate_endpoint
from paths import DATA


def main():
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description='Chassie optional transparent Live2D overlay')
    parser.add_argument('--model-dir', type=Path, default=DATA / 'model')
    parser.add_argument('--cache-dir', type=Path, default=DATA / '.chassie' / 'overlay')
    parser.add_argument('--endpoint', default='ws://127.0.0.1:8000/ws')
    parser.add_argument('--fps', type=int, choices=(15, 30, 60), default=30)
    parser.add_argument('--check', action='store_true', help='Check optional dependencies without opening a window')
    args = parser.parse_args()
    try:
        validate_endpoint(args.endpoint)
    except ValueError as exc:
        parser.error(str(exc))
    missing = []
    for name in ('PySide6', 'OpenGL', 'live2d.v3'):
        try:
            found = importlib.util.find_spec(name)
        except (ImportError, ModuleNotFoundError):
            found = None
        if found is None:
            missing.append(name)
    if missing:
        print('Overlay unavailable: missing ' + ', '.join(missing) + '. See docs/overlay.md.', file=sys.stderr)
        return 2
    if args.check:
        print('Optional modules found. Actual imports, Cubism/OpenGL rendering and desktop transparency still need a live check.')
        return 0
    try:
        from desktop.qt_app import run
        return run(args)
    except (ImportError, OSError, ValueError, RuntimeError) as exc:
        print(f'Overlay could not start: {exc}', file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
