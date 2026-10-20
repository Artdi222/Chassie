import hashlib
import importlib.util
import io
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location('speech_download', Path(__file__).parents[1] / 'scripts/download_speech_asset.py')
downloader = importlib.util.module_from_spec(spec)
spec.loader.exec_module(downloader)


def response(data, size, start=0, status=206):
    result = io.BytesIO(data)
    result.status = status
    result.headers = {'Content-Range': f'bytes {start}-{size-1}/{size}'}
    return result


def test_download_resumes_partial_data_and_verifies_final_hash(tmp_path, monkeypatch):
    payload = b'complete model content'
    target = tmp_path / 'model.safetensors'
    parts = tmp_path / 'model.safetensors.parts'
    parts.mkdir()
    (parts / '0').write_bytes(payload[:5])
    requests = []
    def open_request(request, timeout):
        requests.append(request.get_header('Range'))
        return response(payload[5:], len(payload), 5)
    monkeypatch.setattr(downloader.urllib.request, 'urlopen', open_request)
    downloader.download('https://example.invalid/model', target, len(payload), hashlib.sha256(payload).hexdigest(), workers=1)
    assert requests == [f'bytes=5-{len(payload)-1}']
    assert target.read_bytes() == payload
    assert not parts.exists()


def test_corrupt_download_is_not_installed_and_can_be_retried(tmp_path, monkeypatch):
    target = tmp_path / 'model.safetensors'
    payload = b'good'
    monkeypatch.setattr(downloader.urllib.request, 'urlopen', lambda *a, **kw: response(b'bad!', len(payload)))
    with pytest.raises(ValueError, match='checksum mismatch'):
        downloader.download('https://example.invalid/model', target, len(payload), hashlib.sha256(payload).hexdigest(), workers=1)
    assert not target.exists()
    assert not (tmp_path / 'model.safetensors.parts/0').exists()
    monkeypatch.setattr(downloader.urllib.request, 'urlopen', lambda *a, **kw: response(payload, len(payload)))
    downloader.download('https://example.invalid/model', target, len(payload), hashlib.sha256(payload).hexdigest(), workers=1)
    assert target.read_bytes() == payload


def test_server_ignoring_range_is_rejected(tmp_path, monkeypatch):
    target = tmp_path / 'model.safetensors'
    monkeypatch.setattr(downloader.time, 'sleep', lambda _: None)
    monkeypatch.setattr(downloader.urllib.request, 'urlopen', lambda *a, **kw: response(b'data', 4, status=200))
    with pytest.raises(ValueError, match='unexpected range'):
        downloader.download('https://example.invalid/model', target, 4, hashlib.sha256(b'data').hexdigest(), workers=1)
    assert not target.exists()


def test_closed_terminal_does_not_repeat_or_discard_completed_download(tmp_path, monkeypatch):
    target = tmp_path / 'model.safetensors'
    requests = []
    def open_request(*args, **kwargs):
        requests.append(args[0].get_header('Range'))
        return response(b'data', 4)
    def closed_terminal(*args, **kwargs):
        raise BrokenPipeError('The session was closed')
    monkeypatch.setattr(downloader.urllib.request, 'urlopen', open_request)
    monkeypatch.setattr(downloader, 'print', closed_terminal, raising=False)
    downloader.download('https://example.invalid/model', target, 4, hashlib.sha256(b'data').hexdigest(), workers=1)
    assert target.read_bytes() == b'data'
    assert requests == ['bytes=0-3']
