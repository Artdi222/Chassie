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
        const gazeWeight=!tracking || this.reduced.matches || this.hoverSince!==null?0:1-this.amount;
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
