document.addEventListener('DOMContentLoaded', () => {
    const $ = id => document.getElementById(id);
    const panel = new URLSearchParams(location.search).get('panel');
    const embedded = ['chat', 'settings', 'models', 'wardrobe'].includes(panel);
    const studio = window.modelStudio = {models: [], selection: null, ready: false, modelId: null, error: null};
    let avatar = null, app = null, loadRevision = 0, avatarEvent = {}, subtitleGeneration = -1;
    let cursorInteraction=null,cursorPosition=null;
    let reactionWeights={},reactionLast=performance.now();
    let zoom = 1.8, offset = {x: 0, y: 0}, nativeSize = {width: 1, height: 1}, loadingId = null;
    const send = data => window.chassie?.send(data);
    const control = data => studio.selection && send({type: 'set_model_options', model_id: studio.selection.model_id, ...data});
    const entry = () => studio.models.find(m => m.id === studio.selection?.model_id);
    let panelOpener = null;
    function showPanel(name) {
        if (name && $('panel-backdrop').hidden && !embedded) panelOpener = document.activeElement;
        document.querySelector('.studio-shell').inert = Boolean(name) && !embedded;
        for (const p of [document.querySelector('.sidebar'), $('model-panel')]) {
            p.setAttribute('role', embedded ? 'region' : 'dialog');
            if (name && !embedded) p.setAttribute('aria-modal', 'true'); else p.removeAttribute('aria-modal');
        }
        document.querySelector('.sidebar').classList.toggle('active', name === 'settings');
        $('model-panel').hidden = !['models', 'wardrobe'].includes(name);
        $('panel-backdrop').hidden = !name || embedded;
        if (name === 'wardrobe') setTimeout(() => $('wardrobe-section').scrollIntoView({block: 'start'}), 0);
        if (name) {
            const container = name === 'settings' ? document.querySelector('.sidebar') : $('model-panel');
            container.querySelector('button, input, select')?.focus();
        } else if (!embedded && panelOpener?.isConnected) panelOpener.focus();
    }
    if (embedded) {
        document.body.classList.add('embedded', `panel-${panel}`);
        if (panel === 'chat') document.documentElement.classList.add('embedded-chat');
        showPanel(panel === 'chat' ? null : panel);
    }
    $('menu-toggle').onclick = () => showPanel('settings');
    $('sidebar-close').onclick = $('close-models').onclick = $('panel-backdrop').onclick = () => showPanel(null);
    $('open-models').onclick = () => showPanel('models');
    const tabs = [...document.querySelectorAll('.settings-tabs [role=tab]')];
    function selectTab(tab, focus) {
        for (const t of tabs) {
            const active = t === tab;
            t.setAttribute('aria-selected', active); t.tabIndex = active ? 0 : -1;
            $(t.getAttribute('aria-controls')).hidden = !active;
        }
        if (focus) tab.focus();
    }
    tabs.forEach((t, i) => {
        t.onclick = () => selectTab(t);
        t.onkeydown = e => {
            const step = {ArrowRight: 1, ArrowLeft: -1}[e.key];
            if (step) { e.preventDefault(); selectTab(tabs[(i + step + tabs.length) % tabs.length], true); }
        };
    });
    document.addEventListener('keydown', e => {
        if (e.key === 'Escape') { if (!embedded) showPanel(null); $('avatar-menu').hidden = true; }
        if (e.key === 'Tab' && !embedded && !$('panel-backdrop').hidden) {
            const p = document.querySelector('.sidebar.active') || $('model-panel');
            const focusable = [...p.querySelectorAll('button:not(:disabled), input:not(:disabled), select:not(:disabled), textarea, summary')].filter(x => x.getClientRects().length);
            if (e.shiftKey && document.activeElement === focusable[0]) { e.preventDefault(); focusable.at(-1)?.focus(); }
            else if (!e.shiftKey && document.activeElement === focusable.at(-1)) { e.preventDefault(); focusable[0]?.focus(); }
        }
    });
    function chatVisible(visible) {
        document.querySelector('.chat-area').hidden = !visible;
        $('reopen-chat').hidden = visible;
        requestAnimationFrame(fit);
    }
    $('toggle-chat').onclick = () => chatVisible(false);
    $('reopen-chat').onclick = () => chatVisible(true);
    if (!embedded && innerWidth <= 800) chatVisible(false);
    document.querySelectorAll('[data-panel]').forEach(b => b.onclick = () => {
        $('avatar-menu').hidden = true;
        if (b.dataset.panel === 'chat') chatVisible(true); else showPanel(b.dataset.panel);
    });
    $('studio-stop').onclick = () => send({type: 'stop'});
    $('studio-mic').onclick = () => send({type: 'set_mic', enabled: !$('mic-toggle').checked});
    function button(label, active, action, title) {
        const b = document.createElement('button'); b.type = 'button'; b.textContent = label;
        b.dataset.focusKey = title || label;
        b.setAttribute('aria-pressed', String(active)); b.onclick = action;
        if (title) b.title = title;
        return b;
    }
    function choices(id, kinds, field, multiple = false) {
        const container = $(id); container.replaceChildren();
        const m = entry(), s = studio.selection;
        const items = m?.expressions.filter(x => kinds.includes(x.kind)) || [];
        if (!items.length) { const p = document.createElement('p'); p.textContent = 'No built-in presets for this category.'; container.append(p); return; }
        if (!multiple) container.append(button('Default', !s[field], () => control({[field]: null, ...(field === 'expression' ? {auto: false} : {})})));
        items.forEach(x => {
            const selected = multiple ? s[field].includes(x.id) : s[field] === x.id;
            container.append(button(x.name, selected, () => {
                const value = multiple ? selected ? s[field].filter(id => id !== x.id) : [...s[field], x.id] : x.id;
                control({[field]: value, ...(field === 'expression' ? {auto: false} : {})});
            }, x.name));
        });
    }
    function renderControls() {
        const focused = document.activeElement;
        const focusParent = focused?.parentElement?.id;
        const focusKey = focused?.dataset?.focusKey;
        const m = entry(), s = studio.selection;
        if (!m || !s) return;
        $('model-title').textContent = m.name;
        $('model-description').textContent = `Your companion · ${m.expressions.length} expressions`;
        $('model-list').replaceChildren(...studio.models.map(m => {
            const b = button('', s.model_id === m.id, () => send({type: 'select_model', model_id: m.id}));
            b.className = 'model-option'; b.dataset.modelId = m.id; b.dataset.focusKey = m.id;
            const title = document.createElement('strong'); title.textContent = m.name;
            const sub = document.createElement('span'); sub.textContent = `${m.id.replace('_',' ')} · ${m.expressions.length} presets`;
            b.append(title, sub); return b;
        }));
        $('auto-expression').checked = s.auto;
        const interaction=s.interaction;
        if(interaction) {
            for(const key of ['gaze_enabled','gaze_radius','follow_speed','headpat_enabled','headpat_delay']) {
                const el=$('interaction-'+key);
                if(el.type==='checkbox')el.checked=interaction[key];else el.value=interaction[key];
                const output=$('interaction-'+key+'-value');
                if(output)output.textContent=key==='gaze_radius'?`${interaction[key]} px`:key==='headpat_delay'?`${Math.round(interaction[key]*1000)} ms`:`${interaction[key]}×`;
            }
        }
        choices('expression-list', ['expression'], 'expression');
        choices('outfit-list', ['outfit'], 'outfit');
        const accessories = m.expressions.filter(x => x.kind === 'accessory');
        if (accessories.length) {
            if (!m.expressions.some(x => x.kind === 'outfit')) $('outfit-list').replaceChildren();
            accessories.forEach(x => $('outfit-list').append(button(x.name, s.accessories.includes(x.id), () => control({accessories: s.accessories.includes(x.id) ? s.accessories.filter(v => v !== x.id) : [...s.accessories,x.id]}), x.name)));
        }
        choices('prop-list', ['prop'], 'prop'); choices('effect-list', ['effect'], 'effects', true);
        $('mouth-preview').value = s.mouth_preview;
        $('mouth-preview').disabled = !m.mouth;
        $('model-notice').textContent = m.expressions.length ? 'Presets use this model\'s assets. Your outfit stays selected when the expression changes.' : 'This model has no expression presets. You can still preview blinking, breathing, and mouth movement.';
        if (focusParent && focusKey !== undefined) {
            [...($(focusParent)?.querySelectorAll('button') || [])].find(b => b.dataset.focusKey === focusKey)?.focus({preventScroll:true});
        }
    }
    $('auto-expression').onchange = e => control({auto: e.target.checked});
    for(const key of ['gaze_enabled','gaze_radius','follow_speed','headpat_enabled','headpat_delay']) {
        const el=$('interaction-'+key);
        el.onchange=()=>control({interaction:{[key]:el.type==='checkbox'?el.checked:Number(el.value)}});
        el.oninput=()=>{const output=$('interaction-'+key+'-value');if(output)output.textContent=key==='gaze_radius'?`${el.value} px`:key==='headpat_delay'?`${Math.round(el.value*1000)} ms`:`${el.value}×`;};
    }
    $('reset-interaction').onclick=()=>control({interaction:{gaze_enabled:true,gaze_radius:180,follow_speed:1,headpat_enabled:true,headpat_delay:.18}});
    $('mouth-preview').oninput = e => control({mouth_preview: Number(e.target.value)});
    $('reset-appearance').onclick = () => control({expression:null,outfit:null,prop:null,accessories:[],effects:[],auto:true,mouth_preview:0});
    function applyParameters() {
        const m=entry(), s=studio.selection;
        if (!avatar || !s || !m || studio.modelId !== m.id) return;
        let ids=[s.outfit,s.prop,...s.accessories,...s.effects];
        if (!s.auto) ids.push(s.expression);
        else if(m.id==='Model_4') {
            const aliases={};
            const mood={thinking:'thinking',listening:'curious',idle:'neutral',disconnected:'neutral'}[avatarEvent.status] || avatarEvent.emotion;
            ids.push(...m.expressions.filter(x=>x.generated && x.original===(aliases[mood]||mood)).map(x=>x.id));
        }
        const core=avatar.internalModel.coreModel;
        for (const x of m.expressions.filter(x => !x.generated && ids.includes(x.id))) for (const p of x.parameters) {
            if (p.Blend === 'Multiply') core.multiplyParameterValueById(p.Id,p.Value);
            else if (p.Blend === 'Overwrite') core.setParameterValueById(p.Id,p.Value);
            else core.addParameterValueById(p.Id,p.Value);
        }
        const now=performance.now(),dt=Math.min((now-reactionLast)/1000,.1);reactionLast=now;
        for(const x of m.expressions.filter(x=>x.generated)) {
            const weight=(reactionWeights[x.id]||0)+((ids.includes(x.id)?1:0)-(reactionWeights[x.id]||0))*(1-Math.exp(-dt/.08));
            reactionWeights[x.id]=weight;
            if(weight<.001)continue;
            for(const p of x.parameters) {
                if(p.Blend==='Multiply')core.multiplyParameterValueById(p.Id,1+(p.Value-1)*weight);
                else core.setParameterValueById(p.Id,p.Value,weight);
            }
        }
        const mouth=performance.now()-(avatarEvent.received || 0)<750 ? (avatarEvent.mouth || 0) : 0;
        if (m.mouth) core.setParameterValueById('ParamMouthOpenY',Math.max(mouth,s.mouth_preview));
        if(cursorInteraction) {
            cursorInteraction.settings=s.interaction;
            cursorInteraction.position=cursorPosition;
            studio.pointer=cursorInteraction.update(pointer!==null || !$('panel-backdrop').hidden);
        }
    }
    function fit() {
        if (!avatar || !app) return;
        const box=$('canvas-wrap').getBoundingClientRect();
        app.renderer.resize(box.width,box.height);
        const scale=Math.min(box.width/nativeSize.width,box.height/nativeSize.height)*zoom;
        avatar.scale.set(scale); avatar.anchor.set(.5,0);
        avatar.position.set(box.width/2+offset.x,Math.max(55,box.height*.08)+offset.y);
    }
    async function loadModel() {
        const m=entry(); if (embedded || !m || loadingId === m.id || (studio.modelId === m.id && studio.ready)) return;
        const revision=++loadRevision; loadingId=m.id; studio.ready=false; studio.error=null;
        $('model-loading').hidden=false; $('model-loading').textContent=`Loading ${m.name}…`; $('retry-model').hidden=true;
        if (avatar) { app.stage.removeChild(avatar); avatar.destroy({children:true,texture:true,baseTexture:true}); avatar=null; }
        try {
            if (!app) {
                app=new PIXI.Application({view:$('avatar-canvas'),backgroundAlpha:0,antialias:true,resolution:Math.min(devicePixelRatio,1.5),autoDensity:true});
                app.ticker.maxFPS=30;
            }
            const model=await PIXI.live2d.Live2DModel.from(m.url,{autoInteract:false});
            if (revision!==loadRevision) {model.destroy({children:true,texture:true,baseTexture:true});return;}
            avatar=model;reactionWeights={}; nativeSize={width:model.width,height:model.height}; zoom=1.8;offset={x:0,y:0};
            cursorInteraction=new ChassiePointer(model,m,$('avatar-canvas'));
            studio.pointerController=cursorInteraction;
            studio.modelId=m.id; app.stage.addChild(model);
            model.internalModel.on('beforeModelUpdate',applyParameters);
            fit();studio.ready=true;$('model-loading').hidden=true;
        } catch(e) {
            if(revision!==loadRevision)return;
            studio.error=String(e);$('model-loading').textContent='Unable to load the model. '+(e.message || 'Check WebGL support.');$('retry-model').hidden=false;
        } finally {if(revision===loadRevision)loadingId=null;}
    }
    $('retry-model').onclick=()=>loadModel();
    $('zoom-in').onclick=()=>{zoom=Math.min(3.5,zoom+.15);fit();};$('zoom-out').onclick=()=>{zoom=Math.max(.7,zoom-.15);fit();};
    $('reset-frame').onclick=()=>{zoom=1.8;offset={x:0,y:0};fit();};
    new ResizeObserver(fit).observe($('canvas-wrap'));
    let pointer=null;
    const canvas=$('avatar-canvas');
    canvas.addEventListener('pointerdown',e=>{pointer={x:e.clientX,y:e.clientY,ox:offset.x,oy:offset.y};canvas.setPointerCapture(e.pointerId);});
    document.addEventListener('pointermove',e=>{if(e.pointerType==='mouse')cursorPosition={x:e.clientX,y:e.clientY};});
    document.addEventListener('pointerout',e=>{if(!e.relatedTarget)cursorPosition=null;});
    window.addEventListener('blur',()=>{cursorPosition=null;});
    canvas.addEventListener('pointermove',e=>{if(pointer){offset={x:pointer.ox+e.clientX-pointer.x,y:pointer.oy+e.clientY-pointer.y};fit();}});
    canvas.addEventListener('pointerup',e=>{if(pointer&&Math.hypot(e.clientX-pointer.x,e.clientY-pointer.y)<6)$('avatar-menu').hidden=!$('avatar-menu').hidden;pointer=null;});
    canvas.addEventListener('pointercancel',()=>pointer=null);
    document.addEventListener('visibilitychange',()=>{if(app){if(document.hidden)app.stop();else app.start();}});
    window.addEventListener('chassie-connection',()=>{
        subtitleGeneration=-1;avatarEvent={};$('subtitle').textContent='';$('stage-hint').hidden=false;
        $('studio-mic').disabled=true;
    });
    window.addEventListener('chassie-message',({detail:d})=>{
        if(d.type==='model_catalog'){studio.models=d.models;renderControls();loadModel();}
        if(d.type==='model_state'){studio.selection=d;renderControls();loadModel();}
        if(d.type==='avatar_state'){avatarEvent={...d,received:performance.now()};}
        if(d.type==='subtitle'&&d.generation>=subtitleGeneration){subtitleGeneration=d.generation;$('subtitle').textContent=d.text;$('stage-hint').hidden=!!d.text;}
        if(d.type==='settings'){$('studio-mic').disabled=false;$('studio-mic').querySelector('span').textContent=d.mic_enabled?'Microphone on':'Microphone off';}
        if(d.type==='notice'){$('model-notice').textContent=d.text;}
    });
});
