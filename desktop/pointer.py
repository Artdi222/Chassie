"""Local cursor feedback layered over the selected appearance and speech."""
import json
import math
from avatar.interaction import interaction_settings

HEADPAT_ID = '__chassie_headpat__'
# Under XWayland the global cursor position stops updating once the pointer is over a
# native Wayland window, so its last spot beside the avatar would be tracked forever.
# Trust a position only while the pointer is over the avatar or has moved this recently.
CURSOR_STALE_SECONDS = 1.0
GAZE_RADIUS = 180  # Logical screen pixels; independent of display scaling.
GAZE_SAMPLES = tuple((radius*math.cos(i*math.pi/8), radius*math.sin(i*math.pi/8))
                     for radius in (*range(32,GAZE_RADIUS,32),GAZE_RADIUS) for i in range(16))
HEADPAT = {'ParamAngleX':0, 'ParamAngleY':-10, 'ParamAngleZ':3,
           'ParamEyeLOpen':0, 'ParamEyeROpen':0,
           'ParamEyeLSmile':1, 'ParamEyeRSmile':1, 'ParamMouthForm':1}


class PointerInteraction:
    def __init__(self,model,head_parts,cache_dir,aliases=None):
        self.model=model; self.head_parts=set(head_parts)
        self.look=(0.,0.)  # Normalised gaze for rigs whose physics overrides Drag().
        self.hover_since=None; self.headpat=False
        self.leave_since=None; self.anchor=None
        self.last=None; self.amount=0.; self.gaze=(0.,0.)
        self.cursor=None; self.cursor_moved_at=None
        self.radius=GAZE_RADIUS;self.samples=GAZE_SAMPLES
        available=set(model.GetParamIds())
        aliases=aliases or {}
        values={}
        for key,value in HEADPAT.items():values.setdefault(aliases.get(key,key),value)
        path=cache_dir/'chassie-headpat.exp3.json'
        path.write_text(json.dumps({'Type':'Live2D Expression','FadeInTime':.24,'FadeOutTime':.28,
            'Parameters':[{'Id':key,'Value':value,'Blend':'Overwrite'}
                          for key,value in values.items() if key in available]}))
        model.LoadExtraExpression(HEADPAT_ID,str(path))

    def update(self,x,y,width,height,*,ratio=1,now,dragging=False,enabled=True,settings=None,look=None,hovered=None):
        preferences=interaction_settings(settings)
        radius=preferences['gaze_radius']
        if radius!=self.radius:
            self.radius=radius
            self.samples=tuple((r*math.cos(i*math.pi/8),r*math.sin(i*math.pi/8))
                for r in (*range(32,int(radius),32),radius) for i in range(16))
        dt=min(max(now-self.last,0),.1) if self.last is not None else 1/30
        self.last=now
        if (x,y)!=self.cursor:
            self.cursor=(x,y); self.cursor_moved_at=now
        # hovered=None keeps the old behaviour for callers that cannot tell.
        fresh=hovered is None or hovered or now-self.cursor_moved_at<CURSOR_STALE_SECONDS
        allowed=enabled and not dragging and fresh
        near=allowed and 0<=x<width and 0<=y<height
        parts=self.model.HitPart(x*ratio,y*ratio) if near else []
        self.tracking=bool(parts)
        # Gaze has a bounded halo around visible parts, distinct from the
        # smaller headpat contact area. Never extend the whole empty window.
        if (allowed and preferences['gaze_enabled'] and not self.tracking and -radius<=x<width+radius
                and -radius<=y<height+radius):
            self.tracking=any(0<=x+dx<width and 0<=y+dy<height and
                bool(self.model.HitPart((x+dx)*ratio,(y+dy)*ratio)) for dx,dy in self.samples)
        self.tracking=self.tracking and preferences['gaze_enabled']
        padding=max(8.,min(16.,width*.035))

        def hit_at(px,py):
            return (0<=px<=width and 0<=py<=height and bool(
                self.head_parts.intersection(self.model.HitPart(px*ratio,py*ratio))))

        # A small halo includes the hair edge. Keep the last confirmed point
        # while nodding: animated mesh movement must not cancel a still cursor.
        pat_allowed=near and preferences['headpat_enabled']
        hit=pat_allowed and (bool(self.head_parts.intersection(parts)) or any(
            hit_at(x+dx,y+dy) for dx,dy in
            ((-padding,0),(padding,0),(0,-padding),(0,padding))))
        if hit:self.anchor=(x,y)
        held=(pat_allowed and self.anchor is not None and
              math.hypot(x-self.anchor[0],y-self.anchor[1])<=padding*2.5)
        if hit or held:
            self.leave_since=None
            if self.hover_since is None:self.hover_since=now
        elif pat_allowed and self.hover_since is not None:
            if self.leave_since is None:self.leave_since=now
            if now-self.leave_since>=.16:
                self.hover_since=None; self.anchor=None
        else:
            self.hover_since=None; self.leave_since=None; self.anchor=None
        active=self.hover_since is not None and now-self.hover_since>=preferences['headpat_delay']
        # Do not activate from the release grace period alone.
        active=active and (self.headpat or hit or held)
        self.amount+=(float(active)-self.amount)*(1-math.exp(-dt/(.09 if active else .12)))
        # The SDK adds cursor angles after expressions; center its gaze while
        # entering a pat, and resume following only as the expression fades out.
        weight=float(self.tracking)*(0 if self.hover_since is not None else 1-self.amount)
        target=((x-width/2)*weight,(y-height/2)*weight)
        if look is not None and preferences['gaze_enabled'] and not self.tracking and self.hover_since is None:
            # No cursor nearby: look toward the owner. The camera image is mirrored
            # relative to the viewer, so a face on the image's left is on her right.
            target=(-look[0]*width*.35,look[1]*height*.25)
        ease=1-math.exp(-dt/(.1/preferences['follow_speed']))
        self.gaze=tuple(a+(b-a)*ease for a,b in zip(self.gaze,target))
        if not self.tracking and max(abs(v) for v in self.gaze)<.01:
            self.gaze=(0.,0.)
        self.model.Drag((width/2+self.gaze[0])*ratio,(height/2+self.gaze[1])*ratio)
        clamp=lambda v:max(-1.,min(1.,v))
        self.look=(clamp(self.gaze[0]/(width/2)) if width else 0.,clamp(-self.gaze[1]/(height/2)) if height else 0.)
        if active!=self.headpat:
            if active:self.model.AddExpression(HEADPAT_ID)
            else:self.model.RemoveExpression(HEADPAT_ID)
            self.headpat=active
