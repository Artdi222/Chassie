import json
from unittest.mock import Mock
import pytest
from desktop.pointer import GAZE_RADIUS, HEADPAT_ID, PointerInteraction


def test_headpat_requires_head_hover_and_restores_without_affecting_speech(tmp_path):
    model=Mock();model.GetParamIds.return_value=['ParamAngleY','ParamEyeLOpen','ParamEyeROpen','ParamMouthForm','ParamMouthOpenY']
    model.HitPart.return_value=['face']
    interaction=PointerInteraction(model,['face'],tmp_path)
    interaction.update(100,80,300,500,ratio=2,now=1)
    assert not interaction.headpat
    interaction.update(100,80,300,500,ratio=2,now=1.2)
    model.HitPart.assert_called_with(200,160)
    model.AddExpression.assert_called_once_with(HEADPAT_ID)
    interaction.update(100,80,300,500,now=1.3)
    model.AddExpression.assert_called_once()
    interaction.update(100,80,300,500,now=1.4,dragging=True)
    model.RemoveExpression.assert_called_once_with(HEADPAT_ID)
    assert not interaction.headpat
    assert 'ParamMouthOpenY' not in (tmp_path/'chassie-headpat.exp3.json').read_text()
    model.SetParameterValue.assert_not_called()


def test_body_hover_and_far_cursor_never_trigger_headpat(tmp_path):
    model=Mock();model.GetParamIds.return_value=[];model.HitPart.return_value=['body']
    interaction=PointerInteraction(model,['face'],tmp_path)
    for now in (1,2):interaction.update(150,300,300,500,now=now)
    model.AddExpression.assert_not_called()
    model.HitPart.reset_mock()
    for frame in range(50):interaction.update(-200,80,300,500,now=3+frame/30)
    assert model.Drag.call_args.args==pytest.approx((150,250),abs=.01)
    model.HitPart.assert_not_called()


def test_stationary_cursor_and_head_edge_jitter_do_not_restart_headpat(tmp_path):
    model=Mock();model.GetParamIds.return_value=[];model.HitPart.return_value=['head']
    interaction=PointerInteraction(model,['head'],tmp_path)
    interaction.update(150,80,300,500,now=1)
    interaction.update(150,80,300,500,now=1.2)
    # Nodding moves the animated mesh away from the pointer, indefinitely.
    model.HitPart.return_value=[]
    for frame in range(90):
        interaction.update(150,80+(frame%3-1)*8,300,500,now=1.3+frame/30)
        assert interaction.headpat
    model.AddExpression.assert_called_once_with(HEADPAT_ID)
    model.RemoveExpression.assert_not_called()
    # A brief excursion outside the retention halo should not blink open.
    interaction.update(150,30,300,500,now=4.4)
    interaction.update(150,80,300,500,now=4.5)
    assert interaction.headpat
    interaction.update(150,30,300,500,now=4.6)
    interaction.update(150,30,300,500,now=4.8)
    assert not interaction.headpat
    model.RemoveExpression.assert_called_once_with(HEADPAT_ID)


def test_gaze_decays_to_idle_and_retargets_without_a_snap(tmp_path):
    model=Mock();model.GetParamIds.return_value=[];model.HitPart.return_value=['body']
    interaction=PointerInteraction(model,['head'],tmp_path)
    for frame in range(30):interaction.update(280,250,300,500,now=frame/30)
    before=interaction.gaze[0]
    assert before>100
    interaction.update(1000,250,300,500,now=1)
    assert 0<interaction.gaze[0]<before
    previous=interaction.gaze[0]
    for frame in range(1,40):
        interaction.update(1000,250,300,500,now=1+frame/30)
        assert 0<=interaction.gaze[0]<=previous
        previous=interaction.gaze[0]
    assert interaction.gaze[0]<.01
    interaction.update(20,250,300,500,now=2.4)
    assert -130<interaction.gaze[0]<0


@pytest.mark.parametrize('cursor',[(301,250),(-1,250),(150,-1),(150,501),(290,250)])
def test_leaving_visible_model_releases_gaze_even_just_outside(tmp_path,cursor):
    model=Mock();model.GetParamIds.return_value=[];model.HitPart.return_value=['body']
    interaction=PointerInteraction(model,['head'],tmp_path)
    for frame in range(30):interaction.update(250,300,300,500,now=frame/30)
    assert interaction.tracking and interaction.gaze[0]>90
    # Also covers transparent space INSIDE the avatar window.
    model.HitPart.return_value=[]
    for frame in range(45):interaction.update(*cursor,300,500,now=1+frame/30)
    assert not interaction.tracking
    assert interaction.gaze==(0.,0.)
    model.Drag.assert_called_with(150,250)


@pytest.mark.parametrize('ratio',[1,2])
def test_nearby_cursor_follows_without_touching_model_then_releases(tmp_path,ratio):
    model=Mock();model.GetParamIds.return_value=[]
    # A narrow visible body surrounded by transparent space.
    model.HitPart.side_effect=lambda x,y:['body'] if 120*ratio<=x<=180*ratio and 200*ratio<=y<=400*ratio else []
    interaction=PointerInteraction(model,['head'],tmp_path)
    for frame in range(30):interaction.update(-20,250,300,500,ratio=ratio,now=frame/30)
    assert interaction.tracking and interaction.gaze[0]<-160
    assert not interaction.headpat
    for frame in range(45):
        interaction.update(180+GAZE_RADIUS+1,250,300,500,ratio=ratio,now=1+frame/30)
    assert not interaction.tracking and interaction.gaze==(0.,0.)


def test_proximity_can_cross_window_edge_but_has_a_finite_limit(tmp_path):
    model=Mock();model.GetParamIds.return_value=[]
    model.HitPart.side_effect=lambda x,y:['body'] if 260<=x<300 and 200<=y<=400 else []
    interaction=PointerInteraction(model,['head'],tmp_path)
    interaction.update(330,250,300,500,now=1)
    assert interaction.tracking and not interaction.headpat
    interaction.update(300+GAZE_RADIUS+1,250,300,500,now=2)
    assert not interaction.tracking


def test_hair_halo_can_start_a_pat_but_a_brief_pass_cannot(tmp_path):
    model=Mock();model.GetParamIds.return_value=[]
    model.HitPart.side_effect=lambda x,y:['head'] if 100<=x<=200 and 80<=y<=160 else []
    interaction=PointerInteraction(model,['head'],tmp_path)
    # Ten logical pixels above the hair, on a high-DPI display.
    model.HitPart.side_effect=lambda x,y:['head'] if 200<=x<=400 and 160<=y<=320 else []
    interaction.update(150,70,300,500,ratio=2,now=1)
    interaction.update(150,70,300,500,ratio=2,now=1.2)
    assert interaction.headpat
    interaction.update(150,70,300,500,ratio=2,now=1.3,enabled=False)
    assert not interaction.headpat
    interaction.update(150,70,300,500,ratio=2,now=2)
    interaction.update(150,300,300,500,ratio=2,now=2.05)
    interaction.update(150,300,300,500,ratio=2,now=2.2)
    assert not interaction.headpat


def test_vts_style_rig_gets_pose_gaze_and_headpat_through_its_tracking_inputs(tmp_path):
    from types import SimpleNamespace
    from desktop.model import CatalogModelDriver
    written={}
    class Model:
        def GetParamIds(self):return ['ParamAngleX','ParamAngleY','AngleX','AngleY','AngleZ','EyeSmile','ParamMouthForm']
        def LoadExtraExpression(self,name,path):written['headpat']=json.loads(open(path).read())
        def SetParameterValue(self,param,value):written[param]=value
        def Update(self):pass
        def Draw(self):pass
    aliases={'ParamAngleX':'AngleX','ParamAngleY':'AngleY','ParamAngleZ':'AngleZ','ParamEyeLSmile':'EyeSmile','ParamEyeRSmile':'EyeSmile'}
    PointerInteraction(Model(),['head'],tmp_path,aliases)
    ids={p['Id'] for p in written['headpat']['Parameters']}
    assert {'AngleY','AngleZ','EyeSmile','ParamMouthForm'}<=ids and 'ParamAngleY' not in ids
    driver=CatalogModelDriver(Model(),SimpleNamespace(aliases=aliases),clock=lambda:0.)
    driver.frame(0.,{'ParamAngleX':1.,'ParamAngleZ':-7.},look=(.5,-.5))
    assert written['AngleX']==16. and written['AngleY']==-15. and written['AngleZ']==-7.
    assert 'ParamAngleZ' not in written


def test_physics_driven_rig_breathes_and_its_body_trails_the_head():
    from types import SimpleNamespace
    from desktop.model import CatalogModelDriver
    written={}
    model=SimpleNamespace(SetParameterValue=lambda p,v:written.__setitem__(p,v),Update=lambda:None,Draw=lambda:None)
    entry=SimpleNamespace(aliases={'ParamAngleX':'AngleX','ParamAngleY':'AngleY','ParamAngleZ':'AngleZ'},
                          body_follow={'AngleX':'PositionX'})
    t=[6.5345/4]  # Quarter of the X breathing cycle: full sway.
    driver=CatalogModelDriver(model,entry,clock=lambda:t[0])
    driver.frame(0.,{})
    assert abs(written['AngleX']-7.5)<1e-6
    assert 0<written['PositionX']<written['AngleX']  # Smoothed: the body lags the head.
    for _ in range(60):
        driver.frame(0.,{})  # Same instant, dt clamps to 0 -> no further easing.
    plain=SimpleNamespace(aliases={},body_follow={})
    written.clear();CatalogModelDriver(model,plain,clock=lambda:t[0]).frame(0.,{'ParamAngleX':2.})
    assert written=={'ParamMouthOpenY':0.,'ParamAngleX':2.}  # Tian Muzi path unchanged.


def test_frozen_cursor_after_leaving_the_avatar_releases_gaze_and_headpat(tmp_path):
    # XWayland stops updating the cursor over native Wayland windows: the last spot
    # beside (or even inside) the avatar must not be followed forever.
    model=Mock();model.GetParamIds.return_value=[];model.HitPart.return_value=['head']
    interaction=PointerInteraction(model,['head'],tmp_path)
    for frame in range(12):interaction.update(150,80,300,500,now=1+frame/30,hovered=True)
    assert interaction.headpat and interaction.tracking
    # Pointer left: Qt reports no hover and the position never changes again.
    for frame in range(90):interaction.update(150,80,300,500,now=1.5+frame/30,hovered=False)
    assert not interaction.headpat and not interaction.tracking
    model.RemoveExpression.assert_called_with(HEADPAT_ID)
    assert model.Drag.call_args.args==pytest.approx((150,250),abs=.5)  # Gaze back to centre.
    assert interaction.look==pytest.approx((0,0),abs=.01)
    # A live cursor outside the window (moving) is still followed within the halo.
    model.HitPart.side_effect=lambda x,y:['body'] if 0<=x<300 and 0<=y<500 else []
    for frame in range(10):interaction.update(320+frame,250,300,500,now=5+frame/30,hovered=False)
    assert interaction.tracking


def test_breath_sway_settles_while_speaking():
    from desktop.model import CatalogModelDriver
    t=[0.]
    model=Mock();written={}
    model.SetParameterValue.side_effect=lambda k,v:written.__setitem__(k,v)
    entry=Mock(aliases={'ParamAngleX':'AngleX','ParamAngleY':'AngleY','ParamAngleZ':'AngleZ'},body_follow={})
    driver=CatalogModelDriver(model,entry,clock=lambda:t[0])
    def peak(status):
        values=[]
        for _ in range(400):
            t[0]+=.05;driver.frame(0.,{},status=status);values.append(abs(written['AngleX']))
        return max(values[-130:])
    idle,speaking=peak('idle'),peak('speaking')
    assert idle>6 and speaking<idle*.25


