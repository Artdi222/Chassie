import pytest

from vision.visual_requests import requested_visual_sources


@pytest.mark.parametrize('text,sources', [
    ('Tolong lihat layar aku', {'screen'}),
    ('Cek error di layar ini dong', {'screen'}),
    ('Apa yang ada di layarku?', {'screen'}),
    ('Read the text on my screen', {'screen'}),
    ('Can you see me?', {'camera'}),
    ('Kamu bisa lihat aku?', {'camera'}),
    ('Lihat kameraku dong', {'camera'}),
    ('Describe my screen and camera', {'screen', 'camera'}),
    ('Jangan lihat kamera, tapi cek layarku', {'screen'}),
    ('Look at my screen, but do not use the camera', {'screen'}),
    ('Hai, apa kabar?', set()),
    ('Aku sedang memperbaiki kamera dan layar', set()),
    ('Bagaimana cara share screen?', set()),
    ('My camera is broken', set()),
    ('What is a camera?', set()),
    ('What is screen sharing?', set()),
    ("What's on my screen?", {'screen'}),
    ('Aku lagi lihat layar komputer', set()),
    ('I can see my camera', set()),
    ('Kemarin kamu lihat layar aku', set()),
    ('Chassie, coba lihat layarku', {'screen'}),
    ('I want you to check my screen', {'screen'}),
    ('Jangan lihat layar aku', set()),
    ("Don't look at my screen", set()),
    ('Translate "look at my screen" into Indonesian', set()),
    ('ingat wajahku sebagai Artdi', set()),
    ('forget the face of Owner', set()),
])
def test_visual_input_requires_current_explicit_request(text, sources):
    assert requested_visual_sources(text) == sources
