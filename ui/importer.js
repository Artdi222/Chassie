// Drop-in Live2D model importer used by onboarding and the Customize panel.
// Accepts a downloaded .zip or a whole model folder (picked or dragged); the server finds
// the .model3.json inside, copies only that package into model/, and reloads the catalog.
window.ChassieImporter = (() => {
    const svg = id => `<svg class="icon" aria-hidden="true"><use href="icons.svg#${id}"/></svg>`;

    async function walk(entry, prefix, out) {
        if (entry.isFile) {
            const file = await new Promise((ok, fail) => entry.file(ok, fail));
            out.push([file, prefix + file.name]);
        } else if (entry.isDirectory) {
            const reader = entry.createReader();
            for (;;) {
                const batch = await new Promise((ok, fail) => reader.readEntries(ok, fail));
                if (!batch.length) break;
                for (const child of batch) await walk(child, prefix + entry.name + '/', out);
            }
        }
    }

    function mount(container, {onInstalled, compact = false} = {}) {
        container.classList.add('model-import');
        container.classList.toggle('compact', compact);
        container.innerHTML = `
            <div class="drop-zone" role="group" aria-label="Add a Live2D model">
                <div class="drop-icon">${svg('upload')}</div>
                <strong>${compact ? 'Add another model' : 'Drop your Live2D model here'}</strong>
                <small>A downloaded .zip, or the folder that contains a .model3.json file</small>
                <div class="drop-actions">
                    <button type="button" class="main" data-pick="zip">${svg('upload')}Choose .zip file</button>
                    <button type="button" data-pick="folder">${svg('folder')}Choose folder</button>
                </div>
                <div class="progress" hidden><i></i></div>
            </div>
            <p class="import-status" role="status" aria-live="polite"></p>
            <input type="file" accept=".zip,application/zip" hidden data-input="zip">
            <input type="file" webkitdirectory multiple hidden data-input="folder">`;
        const zone = container.querySelector('.drop-zone');
        const status = container.querySelector('.import-status');
        const bar = container.querySelector('.progress');
        const say = (text, kind = '') => { status.textContent = text; status.className = 'import-status ' + kind; };

        function upload(items) {
            if (!items.length) return;
            const body = new FormData();
            for (const [file, name] of items) body.append('files', file, name);
            const size = items.reduce((n, [f]) => n + f.size, 0);
            zone.classList.add('busy'); bar.hidden = false; bar.firstElementChild.style.width = '0';
            say(`Uploading ${(size / 1048576).toFixed(size > 1048576 * 10 ? 0 : 1)} MB…`);
            const xhr = new XMLHttpRequest();
            xhr.open('POST', '/api/models/import');
            xhr.upload.onprogress = e => {
                if (!e.lengthComputable) return;
                const pct = Math.round(e.loaded / e.total * 100);
                bar.firstElementChild.style.width = pct + '%';
                if (pct >= 100) say('Unpacking and checking the model…');
            };
            const done = () => { zone.classList.remove('busy'); bar.hidden = true; };
            xhr.onerror = () => { done(); say('Could not reach Chassie. Is it still running?', 'error'); };
            xhr.onload = () => {
                done();
                let data = {};
                try { data = JSON.parse(xhr.responseText); } catch { /* plain-text error */ }
                if (xhr.status !== 200) { say(data.error || xhr.responseText || 'The model could not be added.', 'error'); return; }
                const names = data.models.filter(m => data.installed.includes(m.id)).map(m => m.name);
                say(`Added ${names.join(', ')}.`, 'ok');
                onInstalled?.(data);
            };
            xhr.send(body);
        }

        container.querySelectorAll('[data-pick]').forEach(b => b.onclick = () => container.querySelector(`[data-input=${b.dataset.pick}]`).click());
        container.querySelector('[data-input=zip]').onchange = e => { const f = e.target.files[0]; if (f) upload([[f, f.name]]); e.target.value = ''; };
        container.querySelector('[data-input=folder]').onchange = e => {
            upload([...e.target.files].map(f => [f, f.webkitRelativePath || f.name])); e.target.value = '';
        };
        zone.ondragover = e => { e.preventDefault(); zone.classList.add('dragging'); };
        zone.ondragleave = e => { if (!zone.contains(e.relatedTarget)) zone.classList.remove('dragging'); };
        zone.ondrop = async e => {
            e.preventDefault(); zone.classList.remove('dragging');
            const entries = [...e.dataTransfer.items].map(i => i.webkitGetAsEntry?.()).filter(Boolean);
            if (entries.length === 1 && entries[0].isFile) {
                const f = e.dataTransfer.files[0];
                if (!/\.zip$/i.test(f.name)) { say('Drop a .zip file or a model folder.', 'error'); return; }
                upload([[f, f.name]]); return;
            }
            say('Reading the folder…');
            const out = [];
            try { for (const entry of entries) await walk(entry, '', out); }
            catch { say('That folder could not be read. Try “Choose folder” instead.', 'error'); return; }
            upload(out);
        };
        return {say};
    }
    return {mount};
})();
