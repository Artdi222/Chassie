from types import SimpleNamespace

from vision.face_tracker import FaceTracker


def tracker(now):
    return FaceTracker({'face_tracker': {'enabled':True, 'freshness_seconds':1}}, clock=lambda:now[0])


def result(count, **scores):
    return SimpleNamespace(face_landmarks=[[] for _ in range(count)],
                           face_blendshapes=[[SimpleNamespace(category_name=k,score=v)
                                              for k,v in scores.items()] for _ in range(count)])


def test_fresh_face_observation_has_no_identity_claim_and_expires():
    now=[10.0]; face=tracker(now)
    face._record_result(result(1,mouthSmileLeft=.9,mouthSmileRight=.9),10)
    observation=face.get_observation()
    assert observation == {'available':True,'face_count':1,'observed_at':10,
                           'expression':'smiling','identity_verified':False}
    assert 'User' not in face.get_context_string()
    now[0]=11.01
    assert not face.get_observation()['available']
    assert face.get_observation()['expression']=='unknown'
    assert face.get_context_string()==''


def test_multiple_faces_are_counted_without_attributing_first_face():
    now=[10.0]; face=tracker(now)
    face._record_result(result(3,mouthSmileLeft=.9,mouthSmileRight=.9),10)
    observation=face.get_observation()
    assert observation['available'] and observation['face_count']==3
    assert observation['expression']=='unknown'
    assert not observation['identity_verified']
    assert '3 faces' in face.get_context_string()
    assert 'smil' not in face.get_context_string()


def test_no_faces_and_camera_failure_immediately_invalidate_prior_face():
    now=[10.0]; face=tracker(now)
    face._record_result(result(1,mouthSmileLeft=.9,mouthSmileRight=.9),10)
    face._record_result(result(0),10)
    assert face.get_observation()['face_count']==0
    assert not face.get_observation()['available']
    assert face.get_context_string()==''
    face._record_result(result(1),10)
    face._invalidate()
    assert not face.get_observation()['available']
    assert face.get_current_expression()=='unknown'


def test_eyes_closed_and_open_mouth_are_not_emotion_or_tiredness_facts():
    now=[10.0]; face=tracker(now)
    for _ in range(5): face._record_result(result(1,eyeBlinkLeft=.95,eyeBlinkRight=.95),10)
    assert face.get_current_expression()=='eyes_closed'
    assert 'tired' not in face.get_context_string()
    face._record_result(result(1,mouthSmileLeft=.9,mouthSmileRight=.9,jawOpen=.8),10)
    assert face.get_current_expression()=='smiling_mouth_open'
    assert 'laughing' not in face.get_context_string()


def test_stop_invalidates_observation_and_older_results_are_ignored():
    now=[10.0]; face=tracker(now)
    face._record_result(result(1),10)
    face._record_result(result(3),9)
    assert face.get_observation()['face_count']==1
    face.stop()
    assert not face.get_observation()['available']


def test_video_mode_uses_increasing_timestamps_and_releases_resources(monkeypatch):
    import sys
    now=[10.0]; face=tracker(now)
    timestamps=[]; settings={}; cleaned=[]
    cap=SimpleNamespace(isOpened=lambda:True, set=lambda *a:None,
                        read=lambda:(True,object()),release=lambda:cleaned.append('camera'))
    def detect(image,timestamp):
        timestamps.append(timestamp)
        if len(timestamps)==2: face._running=False
        return result(2)
    landmarker=SimpleNamespace(detect_for_video=detect,close=lambda:cleaned.append('landmarker'))
    def options(**kwargs): settings.update(kwargs); return kwargs
    cv2=SimpleNamespace(CAP_DSHOW=1,CAP_ANY=0,CAP_PROP_BUFFERSIZE=2,CAP_PROP_FRAME_WIDTH=3,
                        CAP_PROP_FRAME_HEIGHT=4,COLOR_BGR2RGB=5,VideoCapture=lambda *a:cap,
                        cvtColor=lambda frame,format:frame)
    mp=SimpleNamespace(tasks=SimpleNamespace(BaseOptions=lambda **kw:kw,vision=SimpleNamespace(
        FaceLandmarkerOptions=options,RunningMode=SimpleNamespace(VIDEO='video'),
        FaceLandmarker=SimpleNamespace(create_from_options=lambda opts:landmarker))),
        Image=lambda **kw:kw,ImageFormat=SimpleNamespace(SRGB='rgb'))
    monkeypatch.setitem(sys.modules,'cv2',cv2)
    monkeypatch.setitem(sys.modules,'mediapipe',mp)
    face._running=True
    face._capture_loop()
    assert settings['running_mode']=='video' and settings['num_faces']==3
    assert timestamps==[10000,10001]
    assert cleaned==['landmarker','camera']
    assert not face.get_observation()['available']
