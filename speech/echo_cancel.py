"""Process-scoped PipeWire echo cancellation for full-duplex voice (barge-in).

Chassie loads a WebRTC echo-cancel module for its own session and routes only its
own playback and capture through it with PULSE_SINK/PULSE_SOURCE. System default
devices are never changed, and the module is unloaded on exit.
"""
from __future__ import annotations
import atexit
import logging
import os
import shutil
import subprocess

logger = logging.getLogger('echo_cancel')
SINK = 'chassie_aec_sink'
SOURCE = 'chassie_aec_source'


def _pactl(*args, timeout=5):
    return subprocess.run(['pactl', *args], capture_output=True, text=True, timeout=timeout, check=True).stdout


def _unload_stale():
    """A crashed previous run may have left its module loaded."""
    for line in _pactl('list', 'short', 'modules').splitlines():
        parts = line.split('\t')
        if len(parts) >= 3 and parts[1] == 'module-echo-cancel' and f'sink_name={SINK}' in parts[2]:
            _pactl('unload-module', parts[0])


def enable(config) -> bool:
    """Route Chassie's audio through echo cancellation; returns whether barge-in is safe."""
    conversation = config.setdefault('conversation', {})
    if not conversation.get('barge_in', False) or shutil.which('pactl') is None:
        conversation['barge_in'] = False
        return False
    audio = config.setdefault('audio', {})
    if audio.get('input_device') or audio.get('output_device'):
        # Explicit devices bypass the echo-cancel nodes, so playback would leak into the mic.
        logger.warning('Barge-in disabled: explicit audio devices bypass echo cancellation')
        conversation['barge_in'] = False
        return False
    try:
        _unload_stale()
        module = _pactl('load-module', 'module-echo-cancel', 'aec_method=webrtc',
                        f'source_name={SOURCE}', f'sink_name={SINK}').strip()
    except (OSError, subprocess.SubprocessError) as exc:
        logger.warning('Echo cancellation unavailable (%s); microphone pauses while Chassie speaks', type(exc).__name__)
        conversation['barge_in'] = False
        return False
    os.environ['PULSE_SINK'], os.environ['PULSE_SOURCE'] = SINK, SOURCE
    audio['input_device'] = audio['output_device'] = 'pulse'

    def unload():
        try: _pactl('unload-module', module)
        except (OSError, subprocess.SubprocessError): pass
    atexit.register(unload)
    logger.info('Echo cancellation active; you can interrupt Chassie by speaking')
    return True
