from types import SimpleNamespace

from chassie_core.presence import PresenceMixin
from face_identity import face_command
from visual_requests import requested_visual_sources


def reason(camera, identity):
    host = SimpleNamespace(_session_context=SimpleNamespace(owner_profile_id='owner'), _automatic_memory=True)
    return PresenceMixin._visual_guest_reason(host, {'camera': camera, 'identity': identity})


def test_warming_camera_is_not_treated_as_a_guest():
    assert reason({'enabled': True, 'available': False, 'error': None}, {}) is None
    assert reason({'enabled': True, 'available': False, 'error': 'Camera unavailable'}, {}) == 'Camera presence could not be checked'
    assert reason({'enabled': True, 'available': True}, {'presence_ready': False}) == 'Camera presence could not be checked'
    assert reason({'enabled': True, 'available': True}, {'presence_ready': True, 'face_count': 2}) == 'Additional face detected'


def test_casual_face_commands_enroll_the_owner_without_a_name():
    for text in ('inget muka gw ya', 'simpan wajahku', 'chassie, ingat wajahku ya', 'kenali wajahku'):
        assert face_command(text) == ('remember', ''), text
    assert face_command('simpan wajah gw dong, nama gw Artdi') == ('remember', 'Artdi')
    assert face_command('ingat wajahku ya sayang') is None


def test_indonesian_tag_questions_request_vision_but_negations_do_not():
    assert requested_visual_sources('kamu bisa liat aku gak?') == {'camera'}
    assert requested_visual_sources('kamu liat aku ga sih') == {'camera'}
    assert requested_visual_sources('cek aplikasi yang lagi aku buka') == {'screen'}
    assert requested_visual_sources('jangan lihat layarku') == set()
    assert requested_visual_sources('gak usah liat kamera') == set()
