"""Bounded desktop metadata lookup, independent of camera/screenshot capture."""
import json
import os
import shutil
import subprocess
import time

OVERLAY_CLASS = 'chassie-overlay'


def _app_name(window):
    name=window.get('class') if isinstance(window,dict) else None
    if isinstance(name,str):
        return ''.join(char for char in name if char.isprintable()).strip()[:100]
    return ''


def _is_overlay(window):
    return any(isinstance(window.get(key),str) and window[key].casefold()==OVERLAY_CLASS
               for key in ('class','initialClass'))


def active_application():
    """Read app metadata; while chatting, use the last focused external app.

    Re-read the compositor's live focus history per turn, without retaining
    window titles, closed apps or previous lookup results. Total budget: 250 ms.
    """
    if os.environ.get('HYPRLAND_INSTANCE_SIGNATURE') and shutil.which('hyprctl'):
        try:
            deadline=time.monotonic()+.25
            raw = subprocess.check_output(['hyprctl', '-j', 'activewindow'],
                                          timeout=.25, stderr=subprocess.DEVNULL)
            window = json.loads(raw)
            if not isinstance(window,dict):return {'available':False}
            if _is_overlay(window):
                remaining=deadline-time.monotonic()
                if remaining<=0:return {'available':False}
                clients=json.loads(subprocess.check_output(['hyprctl','-j','clients'],
                    timeout=remaining,stderr=subprocess.DEVNULL))
                if not isinstance(clients,list):return {'available':False}
                candidates=[w for w in clients if isinstance(w,dict) and not _is_overlay(w)
                    and w.get('mapped') is True and not w.get('hidden',False) and _app_name(w)
                    and type(w.get('focusHistoryID')) is int and w['focusHistoryID']>=0]
                if candidates:
                    previous=min(candidates,key=lambda w:w['focusHistoryID'])
                    return {'available':True,'app':_app_name(previous),
                            'source':'last_external_focus','overlay_focused':True}
                return {'available':False,'overlay_focused':True}
            name=_app_name(window)
            if name:return {'available': True, 'app': name}
        except (OSError, subprocess.SubprocessError, ValueError):
            pass
    return {'available': False}
