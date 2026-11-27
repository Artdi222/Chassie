"""AppImage first run (again after each new AppImage): the models that need no terms prompt, the Hermes
memory plugin and the application-menu entry. launch.py starts it in the background; output goes to
.chassie/launcher.log. VOICEVOX is not here: its terms are accepted in Settings → Voice & chat, which installs it.
"""
import os
from pathlib import Path
import shutil
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / 'scripts')]
from paths import DATA  # noqa: E402
import install_memory_model, install_speaker, install_vision  # noqa: E402

MARKER = DATA / '.chassie' / 'first-run'


def version():
    try: return (ROOT / 'VERSION').read_text().strip()
    except OSError: return 'dev'


def plugin():
    """Copy (not link: the AppImage mount path changes each run) the memory plugin into Hermes."""
    hermes = Path(os.environ.get('HERMES_HOME') or Path.home() / '.hermes')
    if not hermes.is_dir(): raise RuntimeError(f'Hermes not found at {hermes}; open Chassie again after installing it')
    target = hermes / 'plugins' / 'chassie'
    if target.is_symlink(): return  # A git install of Chassie owns the plugin.
    shutil.copytree(ROOT / 'hermes_plugin' / 'chassie', target, dirs_exist_ok=True,
                    ignore=shutil.ignore_patterns('__pycache__'))


def menu_entry():
    appimage = os.environ.get('APPIMAGE')
    if not appimage: return
    target = Path(os.environ.get('XDG_DATA_HOME') or Path.home() / '.local/share') / 'applications' / 'chassie.desktop'
    if target.is_file() and 'X-Chassie-AppImage' not in target.read_text(): return  # The git install's own entry.
    icon = DATA / 'chassie-icon.png'
    shutil.copyfile(ROOT / 'ui/public/chassie-icon.png', icon)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text('[Desktop Entry]\nVersion=1.0\nType=Application\nName=Chassie\nComment=Local Live2D companion\n'
                      f'Exec="{appimage}"\nIcon={icon}\nTerminal=false\nCategories=Utility;\n'
                      'StartupWMClass=chassie-overlay\nX-Chassie-AppImage=true\n')


def main():
    if MARKER.is_file() and MARKER.read_text() == version(): return 0
    failed = []
    for name, step in [('vision models', install_vision.install), ('speaker model', install_speaker.install),
                       ('memory model', install_memory_model.install), ('Hermes memory plugin', plugin),
                       ('application menu', menu_entry)]:
        try: step(); print(f'first run: {name} ready', flush=True)
        except Exception as exc: failed.append(name); print(f'first run: {name} failed: {exc}', flush=True)
    if not failed: MARKER.parent.mkdir(parents=True, exist_ok=True); MARKER.write_text(version())
    return 1 if failed else 0  # Failed steps run again next time Chassie opens.


if __name__ == '__main__':
    raise SystemExit(main())
