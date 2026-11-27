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
            else if (d.type === 'hermes_status') renderHermes(d);
            else if (d.type === 'providers') { brain.providers = d.providers; combos.provider.refresh(); showKey(); }
            else if (d.type === 'models' && d.provider === $('ob-provider').value.trim()) {
                brain.models = d.models.map(m => ({value: m.id, label: m.name})); combos.model.refresh();
                $('ob-model').placeholder = brain.models.length ? 'Type to search models' : 'Type the model name';
            }
            else if (d.type === 'brain_test') {
                $('ob-test').disabled = false;
                $('ob-test-status').className = 'import-status' + (d.ok ? '' : ' error');
                $('ob-test-status').textContent = d.ok ? `She can think: the model answered in ${d.seconds} s.` : `Not working yet: ${d.error}`;
            }
            else if (d.type === 'voices') renderVoice(d);
            else if (d.type === 'notice') { const line = state.step === 1 ? $('ob-test-status') : $('ob-voice-text'); line.textContent = d.text; $('ob-test').disabled = $('ob-voice-button').disabled = false; }
        };
        ws.onopen = () => { if (state.step === 1) askBrain(); if (state.step === 3) send({type: 'list_voices'}); };
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

    // ---- Brain: Hermes setup, then provider, key and model (same controls as Settings → AI model) ----
    const brain = {providers: [], models: [], status: null, testing: false};
    const {combobox} = window.ChassieCombobox;
    const combos = {
        provider: combobox($('ob-provider'), () => brain.providers.map(p => ({value: p.id, label: p.label, badge: p.signed_in ? 'Signed in' : ''})), () => 'Loading providers from Hermes…'),
        model: combobox($('ob-model'), () => brain.models, () => 'Choose a provider to see its models.'),
    };
    const askBrain = () => { send({type: 'hermes_status'}); send({type: 'list_providers'}); };
    const chosenProvider = () => brain.providers.find(p => p.id === $('ob-provider').value.trim());
    function showKey() {
        const p = chosenProvider();
        $('ob-key-row').hidden = !p?.key_name || p.signed_in;
        if (p?.key_name) $('ob-key-label').textContent = `API key (${p.key_name})`;
    }
    $('ob-provider').addEventListener('change', () => {
        brain.models = []; $('ob-model').value = ''; showKey();
        const provider = $('ob-provider').value.trim();
        if (provider) send({type: 'list_models', provider});
    });
    function renderHermes(d) {
        if (d.busy) { $('hermes-setup').disabled = true; $('hermes-progress').className = 'import-status'; $('hermes-progress').textContent = d.progress || 'Working…'; return; }
        brain.status = d;
        for (const li of $('hermes-checks').children) li.dataset.ok = String(!!d[li.dataset.check]);
        const ready = d.installed && d.connected && d.running;
        const button = $('hermes-setup');
        button.hidden = ready; button.disabled = false;
        button.textContent = !d.installed ? 'Install Hermes (a few minutes)' : !d.connected ? 'Connect Hermes to Chassie' : 'Start Hermes';
        $('hermes-progress').className = 'import-status' + (d.error ? ' error' : '');
        $('hermes-progress').textContent = d.error || (ready ? 'Hermes is ready. Now choose which AI she uses.' : '');
        $('ob-brain-pick').hidden = !ready;
        if (ready && !brain.providers.length) send({type: 'list_providers'});
        if (ready && brain.testing) { brain.testing = false; $('ob-test-status').textContent = 'Asking the model a test question…'; send({type: 'test_brain'}); }
        else if (brain.testing) { brain.testing = false; $('ob-test').disabled = false; }
        render();
    }
    $('hermes-setup').onclick = () => send({type: 'hermes_setup'});
    $('ob-test').onclick = () => {
        const provider = $('ob-provider').value.trim(), model = $('ob-model').value.trim(), key = $('ob-key').value.trim();
        if (!provider || !model) { $('ob-test-status').textContent = 'Choose a provider and a model first.'; return; }
        $('ob-test').disabled = true; $('ob-test-status').className = 'import-status'; $('ob-test-status').textContent = 'Saving…';
        send({type: 'set_brain', provider, text_model: model});
        if (key && !$('ob-key-row').hidden) { send({type: 'set_api_key', key}); $('ob-key').value = ''; }  // Never kept in the page.
        brain.testing = true;
        send({type: 'hermes_setup'});  // Restarts Hermes so it reads the new key, then the test runs (renderHermes).
    };

    // ---- Voice: VOICEVOX with Mochiko-san, installed here once its terms are accepted ----
    function renderVoice(d) {
        const installed = d.voices.filter(v => v.installed);
        $('ob-voice-button').disabled = false;
        $('ob-voice-install').hidden = installed.length > 0;
        $('ob-voice-terms').textContent = d.terms;
        $('ob-voice-text').textContent = installed.length
            ? `Her voice is installed: ${installed.find(v => v.id === state.settings?.voice?.style)?.name || installed[0].name}. She speaks Japanese, with subtitles in your language. More voices are in Settings.`
            : 'She speaks Japanese through VOICEVOX, a free voice engine, with subtitles in your language. Without it she only writes.';
    }
    $('ob-voice-button').onclick = () => {
        if (!$('ob-voice-accept').checked) { $('ob-voice-text').textContent = 'Tick the box to accept the VOICEVOX terms first.'; return; }
        $('ob-voice-button').disabled = true;
        $('ob-voice-text').textContent = 'Installing her voice… this takes a few minutes. You can continue meanwhile.';
        send({type: 'download_voice', pack: '15.vvm', accept_terms: true});
    };

    // ---- Steps ----
    const current = () => state.models.find(m => m.id === state.selected);
    function go(step) {
        state.step = Math.max(0, Math.min(4, step));
        if (state.step === 1) askBrain();
        if (state.step === 3) send({type: 'list_voices'});
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
        const label = ['Get started', 'Continue', 'Continue', 'Continue', `Meet ${name}`][state.step];
        next.firstChild.textContent = label;
        next.disabled = state.step === 2 && !m;
        const thinking = brain.status && brain.status.installed && brain.status.connected && brain.status.running;
        $('ob-hint').textContent = state.step === 2 && !m ? 'Add a model to continue'
            : state.step === 1 && !thinking ? 'You can do this later in Settings, but she cannot answer until Hermes runs' : '';
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
        if (state.step < 4) { go(state.step + 1); return; }
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

    connect(); go(location.hash === '#model' ? 2 : 0);
})();
