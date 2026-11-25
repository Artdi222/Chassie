// First-run setup. Talks to the same local backend as the studio: model catalog and
// choices over the WebSocket, model import over /api/models/import, completion over
// /api/onboarding. When finished, the page title tells the desktop launcher to continue.
(() => {
    const $ = id => document.getElementById(id);
    const views = [...document.querySelectorAll('.ob-view')];
    const steps = [...document.querySelectorAll('.ob-steps li')];
    const state = {step: 0, models: [], selected: null, settings: null};
    let ws = null, app = null, avatar = null, shownId = null, loadToken = 0;

    // ---- Backend link ----
    function connect() {
        ws = new WebSocket(`${location.protocol === 'https:' ? 'wss' : 'ws'}://${location.host}/ws`);
        ws.onmessage = e => {
            let d; try { d = JSON.parse(e.data); } catch { return; }
            if (d.type === 'model_catalog') { state.models = d.models; render(); }
            else if (d.type === 'model_state') { state.selected = d.model_id; render(); }
            else if (d.type === 'settings') {
                if (!state.settings) applySettings(d);
                state.settings = d;
            }
        };
        ws.onclose = () => setTimeout(connect, 1500);
    }
    const send = data => ws?.readyState === WebSocket.OPEN && ws.send(JSON.stringify(data));
    function applySettings(s) {
        const set = (name, value) => { const el = document.querySelector(`input[name=${name}][value="${value}"]`); if (el) el.checked = true; };
        set('language', s.translation_language); set('initiative', s.initiative_mode); set('input', s.input_mode);
    }
    document.querySelectorAll('input[name=language]').forEach(i => i.onchange = () => send({type: 'set_translation_language', language: i.value}));
    document.querySelectorAll('input[name=initiative]').forEach(i => i.onchange = () => send({type: 'set_initiative_mode', mode: i.value}));
    document.querySelectorAll('input[name=input]').forEach(i => i.onchange = () => send({type: 'set_input_mode', mode: i.value}));

    // ---- Steps ----
    const current = () => state.models.find(m => m.id === state.selected);
    function go(step) {
        state.step = Math.max(0, Math.min(3, step));
        views.forEach((v, i) => v.hidden = i !== state.step);
        steps.forEach((s, i) => { s.classList.toggle('done', i < state.step); if (i === state.step) s.setAttribute('aria-current', 'step'); else s.removeAttribute('aria-current'); });
        render();
        views[state.step].querySelector('h1')?.focus?.();
    }
    function render() {
        const m = current();
        const name = m?.name || 'Chassie';
        $('ob-back').hidden = state.step === 0;
        const next = $('ob-next');
        const label = ['Get started', 'Continue', 'Continue', `Meet ${name}`][state.step];
        next.firstChild.textContent = label;
        next.disabled = state.step === 1 && !m;
        $('ob-hint').textContent = state.step === 1 && !m ? 'Add a model to continue' : '';
        $('ready-title').textContent = `${name} is ready to meet you.`;
        $('character-title').textContent = state.models.length ? 'Choose her look.' : 'Give her a look.';
        const list = $('ob-models');
        list.hidden = !state.models.length;
        list.replaceChildren(...state.models.map(model => {
            const b = document.createElement('button');
            b.type = 'button'; b.className = 'model-option'; b.setAttribute('role', 'radio');
            b.setAttribute('aria-checked', String(model.id === state.selected));
            b.setAttribute('aria-pressed', String(model.id === state.selected));
            const t = document.createElement('strong'); t.textContent = model.name;
            const s = document.createElement('span'); s.textContent = `${model.expressions.length} expressions`;
            b.append(t, s);
            b.onclick = () => send({type: 'select_model', model_id: model.id});
            return b;
        }));
        preview(m);
    }

    // ---- Live preview ----
    function fit() {
        if (!avatar || !app) return;
        const box = $('ob-canvas').parentElement.getBoundingClientRect();
        app.renderer.resize(box.width, box.height);
        const scale = Math.min(box.width / avatar.internalModel.width, box.height / avatar.internalModel.height) * 1.75;
        avatar.scale.set(scale); avatar.anchor.set(.5, 0);
        avatar.position.set(box.width / 2, box.height * .1);
    }
    async function preview(m) {
        const placeholder = $('ob-placeholder');
        if (!m) { placeholder.hidden = false; $('ob-name').hidden = true; return; }
        if (shownId === m.id) return;
        shownId = m.id; const token = ++loadToken;
        $('ob-placeholder-text').textContent = `Loading ${m.name}…`;
        try {
            if (!app) {
                app = new PIXI.Application({view: $('ob-canvas'), backgroundAlpha: 0, antialias: true, resolution: Math.min(devicePixelRatio, 1.5), autoDensity: true});
                app.ticker.maxFPS = 30;
                addEventListener('resize', fit);
            }
            const model = await PIXI.live2d.Live2DModel.from(m.url, {autoHitTest: false, autoFocus: false});
            if (token !== loadToken) { model.destroy({children: true, texture: true, baseTexture: true}); return; }
            if (avatar) { app.stage.removeChild(avatar); avatar.destroy({children: true, texture: true, baseTexture: true}); }
            avatar = model; app.stage.addChild(model); fit();
            // Same life as the studio: idle head motion and breathing, eyes and head
            // following the mouse, headpats; VTube Studio-style rigs through ChassieRig.
            const pointer = new ChassiePointer(model, m, $('ob-canvas')), head = new ChassieHeadMotion();
            const rig = new ChassieRig(model, m);
            let gaze = {};
            rig.source = () => { const p = head.pose('idle'); return {...p, ParamAngleX: p.ParamAngleX + 30 * (gaze.x || 0), ParamAngleY: p.ParamAngleY + 30 * (gaze.y || 0)}; };
            model.internalModel.on('beforeModelUpdate', () => {
                pointer.position = cursor;
                gaze = pointer.update(false);
                if (!rig.active) head.apply(model.internalModel.coreModel, 'idle');
            });
            placeholder.hidden = true;
            const tag = $('ob-name'); tag.hidden = false; tag.querySelector('strong').textContent = m.name;
        } catch (e) {
            if (token !== loadToken) return;
            shownId = null;
            $('ob-placeholder-text').textContent = `${m.name} is installed, but this preview could not draw it. She will still appear on your desktop.`;
        }
    }
    let cursor = null;
    addEventListener('pointermove', e => { cursor = {x: e.clientX, y: e.clientY}; });
    document.addEventListener('pointerleave', () => { cursor = null; });

    // ---- Import ----
    ChassieImporter.mount($('ob-import'), {
        onInstalled: data => {
            state.models = data.models; state.selected = data.selected;
            if (data.installed[0] && data.installed[0] !== data.selected) send({type: 'select_model', model_id: data.installed[0]});
            render();
        },
    });

    // ---- Navigation ----
    $('ob-back').onclick = () => go(state.step - 1);
    $('ob-next').onclick = async () => {
        if (state.step < 3) { go(state.step + 1); return; }
        const button = $('ob-next'); button.disabled = true;
        $('finish-status').textContent = 'Starting…';
        try {
            const r = await fetch('/api/onboarding', {method: 'POST'});
            if (!r.ok) throw new Error(await r.text());
            $('finish-status').textContent = 'Opening Chassie on your desktop…';
            document.title = 'chassie:onboarding-complete';  // The desktop launcher watches for this.
            if (!/QtWebEngine/.test(navigator.userAgent)) setTimeout(() => location.href = '/', 600);
        } catch (e) {
            button.disabled = false;
            $('finish-status').className = 'import-status error';
            $('finish-status').textContent = 'Could not finish setup: ' + (e.message || e);
        }
    };
    document.addEventListener('keydown', e => {
        if (e.key === 'Enter' && e.target === document.body && !$('ob-next').disabled) $('ob-next').click();
    });
    views.forEach(v => v.querySelector('h1')?.setAttribute('tabindex', '-1'));

    connect(); go(location.hash === '#model' ? 1 : 0);
})();
