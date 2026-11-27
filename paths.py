"""Where Chassie's code is (APP) and where her data lives (DATA).

A git install keeps both in the repository, as before. The AppImage is read-only, so its AppRun sets
CHASSIE_DATA (~/.local/share/chassie): config.local.yaml, .chassie/ and model/ live there.
"""
import os
from pathlib import Path

APP = Path(__file__).resolve().parent
DATA = Path(os.environ.get('CHASSIE_DATA') or APP).expanduser()
