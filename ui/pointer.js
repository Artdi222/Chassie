// Local model feedback only; cursor data never goes to the conversation backend.
class ChassiePointer {
    constructor(avatar, metadata, canvas) {
        this.avatar=avatar;this.canvas=canvas;this.position=null;
        this.hoverSince=null;this.leaveSince=null;this.headpat=false;
        this.bounds=null;this.amount=0;this.last=performance.now();
        const raw=avatar.internalModel.coreModel._model;
        const wanted=new Set(metadata.head_parts || []);
        this.headDrawables=[];
        for(let i=0;i<raw.drawables.count;i++) {
            let part=raw.drawables.parentPartIndices?.[i],depth=0;
            while(part>=0 && depth++<raw.parts.count) {
                if(wanted.has(raw.parts.ids[part])) {this.headDrawables.push(i);break;}
                part=raw.parts.parentIndices?.[part];
            }
        }
        this.fine=matchMedia('(hover: hover) and (pointer: fine)');
        this.reduced=matchMedia('(prefers-reduced-motion: reduce)');
    }

    update(dragging) {
        const preferences={gaze_enabled:true,gaze_radius:180,follow_speed:1,headpat_enabled:true,headpat_delay:.18,...this.settings};
        const now=performance.now(),dt=Math.min((now-this.last)/1000,.1);this.last=now;
        const internal=this.avatar.internalModel,core=internal.coreModel;
        let hit=false,held=false,tracking=false,x=0,y=0;
        const rect=this.canvas.getBoundingClientRect(),p=this.position;
        const radius=preferences.gaze_radius;
        const nearby=p && this.fine.matches && !dragging && !document.hidden &&
            p.x>=rect.left-radius && p.x<rect.right+radius && p.y>=rect.top-radius && p.y<rect.bottom+radius;
        const near=nearby && p.x>=rect.left && p.x<rect.right && p.y>=rect.top && p.y<rect.bottom;
        if(nearby) {
            const point=this.avatar.toModelPosition(new PIXI.Point(p.x-rect.left,p.y-rect.top));
            const halo=this.avatar.toModelPosition(new PIXI.Point(p.x-rect.left+radius,p.y-rect.top+radius));
            const radiusX=Math.abs(halo.x-point.x),radiusY=Math.abs(halo.y-point.y);
            // A small proximity halo around visible parts makes gaze easy to
            // engage without extending the entire transparent canvas.
            for(let i=0;i<core._model.drawables.count;i++) {
                if(core.getDrawableOpacity(i)<=.01)continue;
                const b=internal.getDrawableBounds(i);
                const dx=Math.max(b.x-point.x,0,point.x-b.x-b.width);
                const dy=Math.max(b.y-point.y,0,point.y-b.y-b.height);
                if(Math.hypot(dx/radiusX,dy/radiusY)<=1) {
                    tracking=true;break;
                }
            }
            // Freeze the contact region throughout the gesture and its fade.
            // The nod itself must never move the head out from under the cursor.
            if(!this.bounds || (this.hoverSince===null && this.amount<.01)) {
                let left=Infinity,right=-Infinity,top=Infinity,bottom=-Infinity;
                for(const i of this.headDrawables) {
                    if(core.getDrawableOpacity(i)<=.01)continue;
                    const b=internal.getDrawableBounds(i);
                    left=Math.min(left,b.x);right=Math.max(right,b.x+b.width);
                    top=Math.min(top,b.y);bottom=Math.max(bottom,b.y+b.height);
                }
                this.bounds={left,right,top,bottom};
            }
            const {left,right,top,bottom}=this.bounds;
            if(right>left && bottom>top) {
                x=Math.max(-1,Math.min(1,(point.x-(left+right)/2)/(right-left)));
                y=Math.max(-1,Math.min(1,((top+bottom)/2-point.y)/(bottom-top)));
                const extra=this.avatar.toModelPosition(new PIXI.Point(p.x-rect.left+12,p.y-rect.top+12));
                const padX=Math.abs(extra.x-point.x),padY=Math.abs(extra.y-point.y);
                const inside=(pad)=>point.x>=left-padX*pad && point.x<=right+padX*pad &&
                    point.y>=top-padY*pad && point.y<=bottom+padY*pad;
                hit=preferences.headpat_enabled && near && inside(1);
                held=preferences.headpat_enabled && near && this.hoverSince!==null && inside(2.5);
            }
        }
        if(hit || held) {
            this.leaveSince=null;
            if(this.hoverSince===null)this.hoverSince=now;
        } else if(preferences.headpat_enabled && near && this.hoverSince!==null) {
            if(this.leaveSince===null)this.leaveSince=now;
            if(now-this.leaveSince>=160)this.hoverSince=null;
        } else {this.hoverSince=null;this.leaveSince=null;}
        const active=this.hoverSince!==null && now-this.hoverSince>=preferences.headpat_delay*1000 && (this.headpat || hit || held);
        this.headpat=active;
        const target=active?1:0;
        this.amount+=(target-this.amount)*(1-Math.exp(-dt/(active?.09:.12)));
        tracking=tracking && preferences.gaze_enabled;
        let gazeWeight=!tracking || this.reduced.matches || this.hoverSince!==null?0:1-this.amount;
        const look=this.look;
        if(!tracking && look && preferences.gaze_enabled && !this.reduced.matches && this.hoverSince===null) {
            // No cursor nearby: look toward the owner's face from the camera. The camera
            // image is mirrored relative to the viewer, and model y points up.
            x=-look[0]*.6;y=-look[1]*.4;gazeWeight=1;
        }
        this.gazeX=(this.gazeX||0)+(x*gazeWeight-(this.gazeX||0))*(1-Math.exp(-dt/(.1/preferences.follow_speed)));
        this.gazeY=(this.gazeY||0)+(y*gazeWeight-(this.gazeY||0))*(1-Math.exp(-dt/(.1/preferences.follow_speed)));
        internal.focusController.focus(this.gazeX,this.gazeY);
        const values={ParamAngleX:0,ParamAngleY:this.reduced.matches?0:-10,ParamAngleZ:this.reduced.matches?0:3,
            ParamEyeLOpen:0,ParamEyeROpen:0,ParamEyeLSmile:1,ParamEyeRSmile:1,ParamMouthForm:1};
        if(this.amount>.001) for(const [id,value] of Object.entries(values)) {
            if(core._model.parameters.ids.includes(id))core.setParameterValueById(id,value,this.amount);
        }
        return {headpat:active,amount:this.amount,tracking,x:x*gazeWeight,y:y*gazeWeight};
    }
}
window.ChassiePointer=ChassiePointer;

// Mirrors desktop/motion.py: attentive nods while the user talks, a tilt while
// thinking, a gentle sway while speaking or idle. Additive degrees, eased.
const HEAD_POSES={
    listening:[4,-2,1,1.6,.5,5], thinking:[-7,6,0,1,1,6],
    speaking:[0,0,1.5,.9,.4,3.2], idle:[0,0,0,1,1.2,8],
};
function headTarget(status,t){
    const [tilt,baseY,nod,nodPeriod,sway,swayPeriod]=HEAD_POSES[status]||HEAD_POSES.idle;
    return {ParamAngleZ:tilt+sway*Math.sin(2*Math.PI*t/swayPeriod),
            ParamAngleY:baseY-nod*Math.max(0,Math.sin(2*Math.PI*t/nodPeriod)),
            ParamAngleX:sway*.6*Math.sin(2*Math.PI*t/(swayPeriod*1.7))};
}
// One soft nod per backchannel cue (desktop/motion.py nod_offset).
function nodOffset(since){return since===null||since<0||since>=.55?0:-7*Math.sin(Math.PI*since/.55)**2;}
class ChassieHeadMotion {
    constructor(){this.current={ParamAngleX:0,ParamAngleY:0,ParamAngleZ:0};this.last=null;this.nodAt=null;
        this.reduced=matchMedia('(prefers-reduced-motion: reduce)');}
    nod(){this.nodAt=performance.now()/1000;}
    // Eased head pose in degrees for this status (ParamAngleX/Y/Z), nod included.
    pose(status){
        if(this.reduced.matches)return {ParamAngleX:0,ParamAngleY:0,ParamAngleZ:0};
        const now=performance.now()/1000,dt=this.last===null?1/30:Math.min(Math.max(now-this.last,0),.1);this.last=now;
        const target=headTarget(status,now),ease=1-Math.exp(-dt/.35),out={};
        for(const id of Object.keys(this.current)) {
            this.current[id]+=(target[id]-this.current[id])*ease;
            out[id]=this.current[id]+(id==='ParamAngleY'?nodOffset(this.nodAt===null?null:now-this.nodAt):0);
        }
        return out;
    }
    apply(core,status){
        if(this.reduced.matches)return;
        for(const [id,value] of Object.entries(this.pose(status)))
            if(core._model.parameters.ids.includes(id))core.addParameterValueById(id,value);
    }
}

// VTube Studio-style rigs (catalog 'aliases', e.g. ParamAngleX -> AngleX) drive the head
// through tracking inputs and let physics write ParamAngle*, so anything written to
// ParamAngle* earlier is overwritten. Mirror desktop/model.py: feed the head pose, a slow
// breathing sway and the gaze into the rig's own inputs before physics runs, so the head,
// hair and body all follow.
const RIG_BREATH={ParamAngleX:[7.5,6.5345],ParamAngleY:[4,3.5345],ParamAngleZ:[5,5.5345]};
class ChassieRig {
    constructor(model,metadata){
        this.aliases=Object.fromEntries(Object.entries(metadata?.aliases||{}).filter(([p])=>p.startsWith('ParamAngle')));
        this.active=Object.keys(this.aliases).length>0;
        this.source=null;  // () => {ParamAngleX, ParamAngleY, ParamAngleZ} in degrees
        this.reduced=matchMedia('(prefers-reduced-motion: reduce)');
        if(this.active)model.internalModel.on('afterMotionUpdate',()=>this.feed(model.internalModel.coreModel));
    }
    feed(core){
        const pose=this.source?.()||{},t=performance.now()/1000,still=this.reduced.matches;
        for(const [param,alias] of Object.entries(this.aliases)) {
            const [amplitude,period]=RIG_BREATH[param]||[0,1];
            core.setParameterValueById(alias,(pose[param]||0)+(still?0:amplitude*Math.sin(2*Math.PI*t/period)));
        }
    }
}
window.ChassieRig=ChassieRig;
window.ChassieHeadMotion=ChassieHeadMotion;
window.chassieHeadTarget=headTarget;
window.chassieNodOffset=nodOffset;
