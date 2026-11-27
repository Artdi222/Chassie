// Web Chat UI Client for Chassie
document.addEventListener("DOMContentLoaded", () => {
    let ws = null;
    const gatewayUrl = `${window.location.protocol === "https:" ? "wss" : "ws"}://${window.location.host}/ws`;
    let settings = null;
    let voiceDraft = "";
    let inventory = {};
    const streamBubbles = new Map();
    const emotionNames = ["happy", "sad", "surprised", "thinking", "teasing", "concerned", "excited", "neutral", "angry", "shy", "sleepy", "love", "defeated", "curious", "flustered", "shocked"];
    const emotionTags = new RegExp(`\\[(?:${emotionNames.join("|")})\\]\\s*`, "gi");

    // DOM Elements
    const messagesContainer = document.getElementById("messages-container");
    const latestButton=document.getElementById('jump-latest');
    let followLatest=true;
    function scrollForNewContent() {
        if(followLatest)messagesContainer.scrollTop=messagesContainer.scrollHeight;
        else latestButton.hidden=false;
    }
    messagesContainer.addEventListener('scroll',()=>{
        followLatest=messagesContainer.scrollHeight-messagesContainer.clientHeight-messagesContainer.scrollTop<48;
        if(followLatest)latestButton.hidden=true;
    });
    latestButton.onclick=()=>{followLatest=true;latestButton.hidden=true;scrollForNewContent();};
    const chatForm = document.getElementById("chat-form");
    const chatInput = document.getElementById("chat-input");
    const statusGlow = document.getElementById("status-glow");
    const statusText = document.getElementById("status-text");
    const faceExpressionBadge = document.getElementById("face-expression");
    const clearBtn = document.getElementById("clear-btn");
    const micToggle = document.getElementById("mic-toggle");
    const currentActivity = document.getElementById("current-activity");

    // Initialize connection
    function connect() {
        console.log(`Connecting to Chassie WebSocket at ${gatewayUrl}...`);
        ws = new WebSocket(gatewayUrl);

        ws.onopen = () => {
            console.log("Connected to Chassie WebSocket.");
            sendControl({type: "avatar_inventory"});
        };

        ws.onmessage = (event) => {
            try {
                const message = JSON.parse(event.data);
                handleMessage(message);
            } catch (e) {
                console.error("Error parsing WebSocket message:", e);
            }
        };

        ws.onclose = () => {
            window.dispatchEvent(new CustomEvent("chassie-connection", {detail:{connected:false}}));
            console.warn("Chassie WebSocket disconnected. Retrying in 2 seconds...");
            updateStatus("disconnected");
            setControlsConnected(false);
            document.getElementById('vision-state').textContent = 'Disconnected. Camera and screen status are unknown.';
            document.getElementById('face-identity').textContent = '';
            setTimeout(connect, 2000);
        };

        ws.onerror = (err) => {
            console.error("WebSocket error:", err);
            ws.close();
        };
    }

    // Handle incoming backend event messages
    function handleMessage(data) {
        window.dispatchEvent(new CustomEvent("chassie-message", {detail: data}));
        switch (data.type) {
            case "model_catalog": case "model_state": case "subtitle": break;
            case "settings":
                settings = data;
                renderSettings();
                break;
            case "vision_status":
                renderVision(data);
                break;
            case "update": renderUpdate(data); break;
            case "voice_preview": document.getElementById("voice-pick-state").textContent = ""; break;
            case "voices": voiceData = data; document.getElementById("voice-pick-state").textContent = ""; drawVoices(); break;
            case "providers":
                brainItems.providers = data.providers.map(p => ({value: p.id, label: p.label, badge: p.signed_in ? "Signed in" : ""}));
                brainCombos.provider.refresh();
                break;
            case "models": {
                if (data.provider !== document.getElementById("brain-provider").value.trim()) break;
                brainItems.models = data.models.map(m => ({value: m.id, label: m.name, badge: m.vision ? "Images" : ""}));
                brainItems.vision = brainItems.models.filter((_, i) => data.models[i].vision !== false).map(m => ({...m, badge: ""}));
                Object.values(brainCombos).forEach(c => c.refresh());
                document.getElementById("brain-models-note").textContent = data.models.length
                    ? `${data.models.length} models known for ${data.provider}; you can also type any model id.`
                    : `No model list for ${data.provider}; type the model id.`;
                break;
            }
            case "brain_test":
                document.getElementById("test-brain").disabled = false;
                document.getElementById("brain-state").textContent = data.ok ? `Working: answered in ${data.seconds} s.` : `Not working: ${data.error}`;
                break;
            case "notice":
                document.getElementById("control-notice").textContent = data.text;
                document.getElementById("check-update").disabled = document.getElementById("apply-update").disabled = false;
                if (data.scope === "chat") appendSystemAlert(data.text,data.retry_text);
                // A failed control never sends settings back: unlock the mic switch at its real state.
                if (settings && micToggle.disabled) { micToggle.disabled = false; micToggle.checked = settings.mic_enabled; }
                break;
            case "voice_draft_cleared":
                if (chatInput.value === voiceDraft) chatInput.value = "";
                voiceDraft = ""; insertDraft.hidden = true;
                break;
            case "memories":
                renderMemories(data.items);
                break;
            case "memory_status":
                document.getElementById("vault-state").textContent = data.available
                    ? `Obsidian · ${data.path} · ${data.chunks || 0} memories${data.pending_cloud_sources ? " · Sync queued" : ""}`
                    : (data.error || "Vault unavailable. Memories have not been saved here.");
                break;
            case "speaker_status":
                document.getElementById("speaker-state").textContent = data.name ? `Voice sounds like ${data.name}. Recognition is an estimate.` : "Voice not recognized.";
                break;
            case "person_enrolled":
                document.getElementById("person-form").reset();
                break;
            case "avatar_inventory":
                inventory = data.capabilities.emotions || {};
                renderExpressions();
                break;
            case "avatar_state":
                break;
            case "status":
                updateStatus(data.status);
                break;
            case "face_context":
                updateFaceExpression(data.expression);
                break;
            case "chat":
                appendChatBubble(data.role, data.text);
                break;
            case "chat_stream":
                updateStreamBubble(data);
                break;
            case "history_snapshot":
                const priorScroll=messagesContainer.scrollTop,wasFollowing=followLatest;
                clearChatDisplay(false);
                for (const item of data.items) {
                    if (item.stream_id) updateStreamBubble({id: item.stream_id, text: item.text, done: false});
                    else appendChatBubble(item.role, item.text);
                }
                followLatest=wasFollowing;
                if(!wasFollowing)messagesContainer.scrollTop=priorScroll;
                break;
            case "stt_transcription":
                handleSTTTranscription(data.text);
                break;
            case "history_cleared":
                clearChatDisplay();
                break;
            case "sessions":
                renderSessions(data);
                break;
            default:
                console.warn("Unknown message type received:", data);
        }
    }

    // Place voice transcription into input box for review
    function handleSTTTranscription(text) {
        if (!text) return;
        const previous = voiceDraft;
        voiceDraft = text; insertDraft.hidden = !voiceDraft;
        if (!chatInput.value || chatInput.value === previous) chatInput.value = text;
        else document.getElementById("control-notice").textContent = "A voice draft is ready. Use ‘Insert voice draft’ to add it to your message.";
    }

    // Clear chat feed from screen
    function clearChatDisplay(showNotice = true) {
        if(showNotice){followLatest=true;latestButton.hidden=true;}
        streamBubbles.clear();
        messagesContainer.innerHTML = `
            <div class="welcome-box">
                <svg class="welcome-icon"><use href="icons.svg#chat"/></svg>
                <h3>Start with a hello.</h3>
                <p>Type below or turn on the microphone.</p>
            </div>
        `;
        if (showNotice) appendSystemAlert("New conversation started. Earlier chats are kept in History.");
    }

    // Update pipeline status layout
    function updateStatus(status) {
        // Reset classes
        statusGlow.className = "glow-ring " + status;
        
        let text = "Idle";
        let activity = "Ready to chat";

        if (status === "listening") {
            text = "Listening";
            activity = "Listening to your voice...";
        } else if (status === "thinking") {
            text = "Thinking";
            activity = "Thinking of a response...";
        } else if (status === "speaking") {
            text = "Speaking";
            activity = "Speaking...";
        } else if (status === "disconnected") {
            text = "Offline";
            activity = "Reconnecting to Chassie backend...";
            statusGlow.className = "glow-ring idle";
        }

        statusText.textContent = text;
        currentActivity.textContent = activity;
    }


    // Update Face tracker expression context
    function updateFaceExpression(expression) {
        if (expression) {
            faceExpressionBadge.textContent = expression;
        } else {
            faceExpressionBadge.textContent = "Neutral";
        }
    }

    // Append user/assistant chat bubble
    function displayText(text, streaming = false) {
        let clean = text.replace(emotionTags, "");
        if (streaming) {
            const partial = clean.match(/\[([a-z]*)$/i);
            if (partial && emotionNames.some(name => name.startsWith(partial[1].toLowerCase()))) {
                clean = clean.slice(0, partial.index);
            }
        }
        return clean.trim();
    }

    function updateStreamBubble(data) {
        const text = displayText(data.text, !data.done);
        let bubble = streamBubbles.get(data.id);
        if (!bubble && text) {
            bubble = appendChatBubble("assistant", text);
            streamBubbles.set(data.id, bubble);
        }
        if (!bubble) return;
        bubble.querySelector(".bubble-content").textContent = text;
        bubble.querySelector(".bubble-meta").textContent = data.interrupted ? "Chassie • Interrupted" : data.done ? "Chassie" : "Chassie • Replying…";
        bubble.dataset.streamId = data.id;
        scrollForNewContent();
    }

    function appendChatBubble(role, text) {
        // Hide welcome box if present
        const welcomeBox = document.querySelector(".welcome-box");
        if (welcomeBox) {
            welcomeBox.style.display = "none";
        }

        // Clean up formatting (strip any brackets used in raw LLM text for display)
        const cleanText = role === "assistant" ? displayText(text) : text.trim();
        if (!cleanText) return;

        const bubble = document.createElement("div");
        bubble.className = `message-bubble ${role}`;

        const content = document.createElement("div");
        content.className = "bubble-content";
        content.textContent = cleanText;

        const meta = document.createElement("div");
        meta.className = "bubble-meta";
        
        const now = new Date();
        const timeStr = now.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
        meta.textContent = role === "user" ? `You • ${timeStr}` : `Chassie • ${timeStr}`;

        bubble.appendChild(content);
        bubble.appendChild(meta);
        const copy=document.createElement('button');copy.className='copy-message';copy.type='button';
        copy.textContent='Copy';copy.setAttribute('aria-label','Copy message');
        copy.onclick=async()=>{
            try {await navigator.clipboard.writeText(content.textContent);copy.textContent='Copied';}
            catch {copy.textContent='Copy unavailable';}
            setTimeout(()=>copy.textContent='Copy',1800);
        };
        bubble.append(copy);
        messagesContainer.appendChild(bubble);

        // Auto scroll to bottom
        scrollForNewContent();
        return bubble;
    }

    // Append system alert box
    function appendSystemAlert(text,retryText) {
        const alertBox = document.createElement("div");
        alertBox.className = "welcome-box";
        alertBox.setAttribute("role", "alert");
        alertBox.style.margin = "12px auto";
        alertBox.style.padding = "16px";
        alertBox.style.borderRadius = "16px";
        alertBox.style.maxWidth = "360px";
        const notice = document.createElement("p");
        notice.textContent = text;
        alertBox.append(notice);
        if(typeof retryText==='string' && retryText.trim()) {
            const retry=action('Try again',()=>{
                if(sendControl({type:'user_input',text:retryText})) {
                    retry.disabled=true;retry.textContent='Retrying…';followLatest=true;scrollForNewContent();
                }
            });
            alertBox.append(retry);
        }
        messagesContainer.appendChild(alertBox);
        scrollForNewContent();
    }

    /* Legacy sidebar logic (replaced by studio panels)
    // Responsive Sidebar Hamburger Logic
    const menuToggle = document.getElementById("menu-toggle");
    const sidebarClose = document.getElementById("sidebar-close");
    const sidebar = document.querySelector(".sidebar");
    const chatArea = document.querySelector(".chat-area");

    if (menuToggle && sidebarClose && sidebar) {
        console.log("Hamburger sidebar system initialized.");
        
        menuToggle.addEventListener("click", (e) => {
            console.log("Hamburger icon clicked. Opening sidebar.");
            e.stopPropagation();
            sidebar.classList.add("active");
        });

        sidebarClose.addEventListener("click", (e) => {
            console.log("Sidebar close button clicked. Closing sidebar.");
            e.stopPropagation();
            sidebar.classList.remove("active");
        });

        // Close sidebar when clicking main chat area
        chatArea.addEventListener("click", (e) => {
            if (sidebar.classList.contains("active")) {
                console.log("Clicked main chat area while sidebar was open. Closing sidebar.");
                sidebar.classList.remove("active");
            }
        });
    }

    */
    // Submit Text Input Form
    chatForm.addEventListener("submit", (e) => {
        e.preventDefault();
        const text = chatInput.value.trim();
        if (!text || !ws || ws.readyState !== WebSocket.OPEN) return;

        // Send to backend
        followLatest=true;latestButton.hidden=true;
        ws.send(JSON.stringify({
            type: "user_input",
            text: text
        }));

        chatInput.value = "";
    });

    // Previous chats: continue an earlier conversation or start a new one.
    const sessionsToggle=document.getElementById("sessions-toggle"),sessionList=document.getElementById("session-list");
    const sessionTitle=document.getElementById("session-title");
    let sessionState={items:[],current:null,available:true};
    function sessionDate(value){
        const date=new Date(value);if(Number.isNaN(date.getTime()))return "";
        const today=new Date(),time=date.toLocaleTimeString([], {hour:"2-digit",minute:"2-digit"});
        const yesterday=new Date(today);yesterday.setDate(today.getDate()-1);
        if(date.toDateString()===today.toDateString())return "Today "+time;
        if(date.toDateString()===yesterday.toDateString())return "Yesterday "+time;
        return date.toLocaleDateString([], {day:"numeric",month:"short"})+" "+time;
    }
    function sessionMeta(item){
        const turns=Math.max(1,Math.ceil(item.count/2));
        return sessionDate(item.updated)+" · "+turns+(turns===1?" exchange":" exchanges");
    }
    function renderSessions(data){
        sessionState=data;
        const current=data.items.find(item=>item.id===data.current);
        sessionTitle.textContent=current?current.title:"New chat";
        sessionList.replaceChildren();
        if(!data.available){
            const note=document.createElement("p");note.className="session-empty";
            note.textContent="Chat history is hidden while someone else is here.";sessionList.append(note);return;
        }
        if(!data.items.length){
            const note=document.createElement("p");note.className="session-empty";
            note.textContent="No earlier chats yet. They appear here after your first message.";sessionList.append(note);return;
        }
        for(const item of data.items){
            const row=document.createElement("div");row.className="session-item";
            if(item.id===data.current)row.setAttribute("aria-current","true");
            const open=document.createElement("button");open.type="button";open.className="session-open";
            const title=document.createElement("strong");title.textContent=item.title;
            const meta=document.createElement("span");meta.textContent=sessionMeta(item);
            open.append(title,meta);
            if(item.summary){const recap=document.createElement("em");recap.className="session-summary";recap.textContent=item.summary;open.append(recap);}
            open.addEventListener("click",()=>{
                if(item.id!==sessionState.current)sendControl({type:"open_session",session_id:item.id});
                closeSessions();
            });
            const remove=document.createElement("button");remove.type="button";remove.className="session-delete";
            remove.title="Delete this chat";remove.setAttribute("aria-label","Delete chat: "+item.title);
            remove.innerHTML='<svg class="icon"><use href="icons.svg#close"/></svg>';
            remove.addEventListener("click",()=>{
                if(remove.dataset.confirm){sendControl({type:"delete_session",session_id:item.id});return;}
                // Two clicks to delete, without a blocking browser dialog.
                remove.dataset.confirm="1";remove.title="Click again to delete";meta.textContent="Click × again to delete this chat";
                setTimeout(()=>{delete remove.dataset.confirm;remove.title="Delete this chat";meta.textContent=sessionMeta(item);},3000);
            });
            row.append(open,remove);sessionList.append(row);
        }
        renderReminders(data.reminders||[]);
    }
    function renderReminders(items){
        if(!items.length)return;
        const heading=document.createElement("h3");heading.className="session-heading";heading.textContent="Reminders";
        sessionList.append(heading);
        for(const item of items){
            const row=document.createElement("div");row.className="session-item reminder-item";
            const body=document.createElement("div");body.className="session-open";
            const title=document.createElement("strong");title.textContent=item.text;
            const meta=document.createElement("span");
            meta.textContent=sessionDate(item.at)+(item.repeat?" · "+item.repeat:"");
            body.append(title,meta);
            const remove=document.createElement("button");remove.type="button";remove.className="session-delete";
            remove.title="Delete this reminder";remove.setAttribute("aria-label","Delete reminder: "+item.text);
            remove.innerHTML='<svg class="icon"><use href="icons.svg#close"/></svg>';
            remove.addEventListener("click",()=>sendControl({type:"delete_reminder",reminder_id:item.id}));
            row.append(body,remove);sessionList.append(row);
        }
    }
    function closeSessions(){sessionList.hidden=true;sessionsToggle.setAttribute("aria-expanded","false");}
    sessionsToggle.addEventListener("click",()=>{
        const opening=sessionList.hidden;
        sessionList.hidden=!opening;sessionsToggle.setAttribute("aria-expanded",String(opening));
        if(opening){
            sessionList.style.setProperty("--session-top",(sessionsToggle.offsetTop+sessionsToggle.offsetHeight+6)+"px");
            sendControl({type:"list_sessions"});
        }
    });
    document.getElementById("new-chat").addEventListener("click",()=>{closeSessions();sendControl({type:"clear_history"});});
    document.addEventListener("keydown",event=>{if(event.key==="Escape"&&!sessionList.hidden){closeSessions();sessionsToggle.focus();}});

    // Clear History Button Action
    clearBtn.addEventListener("click", () => {
        if (!ws || ws.readyState !== WebSocket.OPEN) return;
        ws.send(JSON.stringify({
            type: "clear_history"
        }));
    });

    function sendControl(data) {
        if (!ws || ws.readyState !== WebSocket.OPEN) {
            document.getElementById("control-notice").textContent = "Disconnected. Your changes have not been sent.";
            return false;
        }
        ws.send(JSON.stringify(data));
        return true;
    }

    function setControlsConnected(connected) {
        ["mic-toggle", "input-mode", "companion-mode", "translation-language", "initiative-mode", "persona", "save-persona", "stop-btn", "profile-select"].forEach(id => {
            document.getElementById(id).disabled = !connected;
        });
        if (!connected) {
            ["preview-btn", "resume-btn", "load-memories", "delete-profile"].forEach(id => document.getElementById(id).disabled = true);
        }
    }

    // One line per part of her: working, broken, or off/unknown.
    function renderHealth(health, usage) {
        const list = document.getElementById("health-state");
        if (!list || !health) return;
        const parts = {brain: "Brain (Hermes)", voice: "Voice", ears: "Microphone", memory: "Memory vault", eyes: "Camera"};
        list.replaceChildren(...Object.entries(parts).map(([key, label]) => {
            const value = health[key], item = document.createElement("li");
            item.className = "health-item " + (value === true ? "ok" : value === false ? "bad" : "off");
            item.textContent = `${label}: ${value === true ? "working" : value === false ? "not working" : "off or not checked yet"}`;
            return item;
        }));
        const note = document.getElementById("usage-state");
        if (note && usage) {
            const tokens = (usage.prompt_tokens || 0) + (usage.completion_tokens || 0);
            note.textContent = `This session: ${usage.requests || 0} model requests, ${tokens.toLocaleString()} tokens`
                + (typeof usage.cost === "number" ? ` (about $${usage.cost.toFixed(3)}).`
                   : ". Set hermes.price_per_million in config.local.yaml to see the cost.");
        }
    }

    function renderUpdate(data) {
        const state = document.getElementById("update-state"), notes = document.getElementById("update-notes");
        document.getElementById("check-update").disabled = document.getElementById("apply-update").disabled = false;
        document.getElementById("apply-update").hidden = !data.available || data.local_changes.length > 0;
        notes.hidden = !data.available || !data.notes;
        notes.textContent = data.latest ? `${data.latest}: ${data.notes}` : "";
        state.textContent = data.updated ? "Updated. Chassie is restarting…"
            : data.local_changes.length ? `Files changed on this computer block updating: ${data.local_changes.join(", ")}`
            : data.available ? `${data.behind} new change${data.behind === 1 ? "" : "s"} available (you have ${data.current}).`
            : `Chassie is up to date (${data.current}).`;
    }

    let voiceData = null, pendingVoice = null, heardVoice = null;
    function drawVoices() {
        const list = document.getElementById("voice-list"), chosen = settings?.voice?.style, state = document.getElementById("voice-pick-state");
        if (pendingVoice !== null && pendingVoice === chosen) { pendingVoice = null; state.textContent = ""; }
        const mb = bytes => bytes ? ` · ${Math.round(bytes / 1e6)} MB` : "";
        const packs = {};
        voiceData.voices.forEach(v => (packs[v.pack] ??= []).push(v));
        // Rebuilt on every settings update: keep what the person opened and where they scrolled.
        const moreOpen = Boolean(list.querySelector("details.more-voices[open]")), scroll = list.scrollTop;
        list.replaceChildren();
        const missing = [];
        for (const [pack, styles] of Object.entries(packs)) {
            const names = [...new Set(styles.map(v => v.name))];
            if (!styles[0].installed) { missing.push([pack, names]); continue; }
            for (const name of names) {
                const row = document.createElement("div");row.className = "memory-item";
                const label = document.createElement("p");label.textContent = name;
                row.append(label, ...styles.filter(v => v.name === name).map(v => {
                    const button = action(`▶ ${v.style_name}${v.id === chosen ? " ✓" : ""}`, () => {
                        if (!sendControl({type: "preview_voice", style: v.id})) return;
                        heardVoice = v; state.textContent = `Playing ${v.name} · ${v.style_name}…`; drawVoices();
                    });
                    button.title = v.id === chosen ? "Her voice now · listen" : "Listen";
                    button.setAttribute("aria-pressed", String(v.id === heardVoice?.id));
                    return button;
                }));
                list.append(row);
            }
        }
        const use = document.getElementById("use-voice");
        use.hidden = !heardVoice || heardVoice.id === chosen;
        if (heardVoice) use.textContent = `Use ${heardVoice.name} · ${heardVoice.style_name}`;
        if (missing.length) {
            const more = document.createElement("details");
            more.className = "more-voices"; more.open = moreOpen;
            const summary = document.createElement("summary");summary.textContent = `More voices to download (${missing.length} packs)`;
            more.append(summary, ...missing.map(([pack, names]) => {
                const row = document.createElement("div");row.className = "memory-item";
                const text = document.createElement("p");
                text.textContent = `Pack ${pack.replace(".vvm", "")} · ${names.length} character${names.length === 1 ? "" : "s"}${mb(voiceData.sizes[pack])}: ${names.join(", ")}`;
                row.append(text, action("Download", () => {
                    if (!document.getElementById("voice-terms-accept").checked) { state.textContent = "Accept the VOICEVOX terms below first."; return; }
                    if (sendControl({type: "download_voice", pack, accept_terms: true}))
                        state.textContent = `Downloading pack ${pack.replace(".vvm", "")}${mb(voiceData.sizes[pack])}… this can take a few minutes.`;
                }));
                return row;
            }));
            list.append(more);
        }
        list.scrollTop = scroll;
        document.getElementById("voice-terms").hidden = !missing.length;
        document.getElementById("voice-terms-text").textContent = voiceData.terms;
    }

    const BRAIN_KEYS = ["provider", "text_model", "vision_model", "background_model", "reasoning_effort"];
    let providersAsked = false, modelsFor = null;
    function askModels(provider) {
        if (provider && provider !== modelsFor && sendControl({type: "list_models", provider})) modelsFor = provider;
    }
    const brainItems = {providers: [], models: [], vision: []};

    // Searchable dropdown over a plain text input: any typed value still counts.
    function combobox(input, items, empty) {
        const list = document.createElement("ul");
        list.className = "combo-list"; list.id = `${input.id}-options`; list.setAttribute("role", "listbox"); list.hidden = true;
        input.after(list);
        input.setAttribute("role", "combobox"); input.setAttribute("aria-autocomplete", "list");
        input.setAttribute("aria-controls", list.id); input.setAttribute("aria-expanded", "false");
        let shown = [], active = -1, query = "";
        const close = () => { list.hidden = true; input.setAttribute("aria-expanded", "false"); input.removeAttribute("aria-activedescendant"); };
        const choose = item => { input.value = item.value; close(); input.dispatchEvent(new Event("change")); };
        const mark = index => {
            active = index;
            [...list.children].forEach((li, i) => li.setAttribute("aria-selected", String(i === active)));
            const li = list.children[active];
            if (li && shown[active]) { input.setAttribute("aria-activedescendant", li.id); li.scrollIntoView({block: "nearest"}); }
        };
        const render = () => {
            const q = query.toLowerCase();
            shown = items().filter(i => !q || i.value.toLowerCase().includes(q) || i.label.toLowerCase().includes(q)).slice(0, 80);
            list.replaceChildren(...shown.map((item, i) => {
                const li = document.createElement("li");
                li.id = `${list.id}-${i}`; li.setAttribute("role", "option");
                const label = document.createElement("span"); label.className = "combo-label"; label.textContent = item.label;
                li.append(label);
                if (item.label !== item.value) { const id = document.createElement("span"); id.className = "combo-id"; id.textContent = item.value; li.append(id); }
                if (item.badge) { const badge = document.createElement("span"); badge.className = "combo-badge"; badge.textContent = item.badge; li.append(badge); }
                li.addEventListener("mousedown", e => { e.preventDefault(); choose(item); });
                return li;
            }));
            if (!shown.length) {
                const li = document.createElement("li"); li.className = "combo-empty";
                li.textContent = items().length ? "No match. Your typed value will be used." : empty();
                list.append(li);
            }
            list.hidden = false; input.setAttribute("aria-expanded", "true"); mark(-1);
        };
        input.addEventListener("focus", () => { query = ""; render(); });  // Show everything first, then narrow.
        input.addEventListener("input", () => { query = input.value.trim(); render(); });
        input.addEventListener("blur", close);
        input.addEventListener("keydown", e => {
            if (e.key === "ArrowDown" || e.key === "ArrowUp") {
                e.preventDefault();
                if (list.hidden) render();
                if (shown.length) mark((active + (e.key === "ArrowDown" ? 1 : -1) + shown.length) % shown.length);
            } else if (e.key === "Enter" && !list.hidden && active >= 0) { e.preventDefault(); choose(shown[active]); }
            else if (e.key === "Escape" && !list.hidden) { e.preventDefault(); close(); }
        });
        return {refresh: () => { if (!list.hidden) render(); }};
    }
    // Same look as the comboboxes for a fixed list; the hidden <select> keeps the value.
    function enhanceSelect(select) {
        const wrap = document.createElement("div"), button = document.createElement("button"), list = document.createElement("ul");
        wrap.className = "combo"; button.type = "button"; button.className = "field combo-button";
        list.className = "combo-list"; list.id = `${select.id}-options`; list.setAttribute("role", "listbox"); list.hidden = true;
        button.setAttribute("aria-haspopup", "listbox"); button.setAttribute("aria-controls", list.id); button.setAttribute("aria-expanded", "false");
        const label = document.querySelector(`label[for="${select.id}"]`);
        if (label) { button.id = `${select.id}-button`; label.htmlFor = button.id; }
        select.hidden = true; select.after(wrap); wrap.append(button, list);
        let active = -1;
        const sync = () => { button.textContent = select.selectedOptions[0]?.text || ""; };
        const close = () => { list.hidden = true; button.setAttribute("aria-expanded", "false"); };
        const mark = i => { active = i; [...list.children].forEach((li, n) => li.setAttribute("aria-selected", String(n === i))); list.children[i]?.scrollIntoView({block: "nearest"}); };
        const choose = i => { select.selectedIndex = i; sync(); close(); select.dispatchEvent(new Event("change")); button.focus(); };
        const open = () => {
            list.replaceChildren(...[...select.options].map((option, i) => {
                const li = document.createElement("li"); li.setAttribute("role", "option"); li.textContent = option.text;
                li.addEventListener("mousedown", e => { e.preventDefault(); choose(i); });
                return li;
            }));
            list.hidden = false; button.setAttribute("aria-expanded", "true"); mark(select.selectedIndex);
        };
        button.addEventListener("click", () => list.hidden ? open() : close());
        button.addEventListener("blur", close);
        button.addEventListener("keydown", e => {
            if (e.key === "ArrowDown" || e.key === "ArrowUp") {
                e.preventDefault(); if (list.hidden) return open();
                mark((active + (e.key === "ArrowDown" ? 1 : -1) + select.options.length) % select.options.length);
            } else if ((e.key === "Enter" || e.key === " ") && !list.hidden && active >= 0) { e.preventDefault(); choose(active); }
            else if (e.key === "Escape" && !list.hidden) { e.preventDefault(); close(); }
        });
        sync();
        return {sync};
    }
    const effortSelect = enhanceSelect(document.getElementById("brain-reasoning_effort"));
    const brainCombos = {
        provider: combobox(document.getElementById("brain-provider"), () => brainItems.providers, () => "Loading providers from Hermes…"),
        text_model: combobox(document.getElementById("brain-text_model"), () => brainItems.models, () => "Choose a provider to see its models."),
        vision_model: combobox(document.getElementById("brain-vision_model"), () => brainItems.vision, () => "Choose a provider to see its models."),
        background_model: combobox(document.getElementById("brain-background_model"), () => brainItems.models, () => "Choose a provider to see its models."),
    };
    function renderBrain(brain) {
        if (!brain) return;
        for (const key of BRAIN_KEYS) {
            const input = document.getElementById(`brain-${key}`);
            if (document.activeElement !== input) input.value = brain[key] || "";
        }
        const effort = document.getElementById("brain-reasoning_effort");
        if (effort.options.length === 1) brain.efforts.forEach(e => effort.add(new Option(e === "xhigh" ? "Extra high" : e[0].toUpperCase() + e.slice(1), e)));
        effort.value = brain.reasoning_effort || "";
        effortSelect.sync();
        askModels(brain.provider);
        document.getElementById("brain-key").hidden = !brain.key_name;
        document.getElementById("brain-key-label").textContent = `API key (${brain.key_name})`;
        document.getElementById("brain-key-state").textContent = brain.key_saved
            ? "A key is saved in Hermes. Type a new one only to replace it. If Test fails after a change, restart Hermes."
            : `No ${brain.key_name} in Hermes's .env. If Hermes already reaches this provider through its own sign-in, leave this empty.`;
    }

    function renderSettings() {
        setControlsConnected(true);
        renderVision(settings.vision);
        renderHealth(settings.health, settings.usage);
        renderBrain(settings.brain);
        const look = settings.appearance || {};
        document.getElementById("appearance-text").textContent = look.text
            || (look.pending ? "Looking at this avatar…" : "She learns her look the first time the avatar opens on the desktop.");
        micToggle.checked = settings.mic_enabled;
        const voicevox = settings.speech_engine === "voicevox";
        const subtitles = settings.translation_language === "id" ? "Indonesian" : "English";
        document.getElementById("translation-language").value = settings.translation_language || "en";
        document.getElementById("initiative-mode").value = settings.initiative_mode || "normal";
        const persona = document.getElementById("persona");
        if (document.activeElement !== persona) persona.value = settings.persona || "";  // Never overwrite while typing.
        document.getElementById("translation-language").hidden = document.querySelector('label[for="translation-language"]').hidden = !voicevox;
        document.getElementById("speech-language").textContent = voicevox
            ? `Voice: ${settings.voice?.name || "Mochiko-san"} · ${settings.voice?.style_name || "Normal"} (VOICEVOX) · speaks Japanese with ${subtitles} subtitles`
            : "English voice and subtitles";
        document.getElementById("echo-help").textContent = settings.automatic_barge_in
            ? "Echo cancellation is on: you can interrupt Chassie just by speaking."
            : "The microphone pauses while Chassie talks to avoid echo.";
        document.getElementById("input-caption").textContent = voicevox ? `Japanese voice · ${subtitles} subtitles` : "English voice and subtitles";
        document.getElementById("speech-credit").hidden = !voicevox;
        document.getElementById("speech-credit").textContent = settings.voice?.credit || "";
        if (voiceData) drawVoices();
        document.getElementById("input-mode").value = settings.input_mode;
        document.getElementById("companion-mode").value = settings.mode;
        document.getElementById("voice-state").textContent = !settings.mic_enabled ? "Microphone muted" : settings.capture_paused ? "Microphone paused during reply — echo protection" : settings.voice_ready ? "Microphone listening" : (settings.voice_error || "Microphone is starting or unavailable");
        document.getElementById("resume-btn").disabled = !settings.pending_topic;
        const automatic = !!settings.automatic_memory;
        document.getElementById("automatic-memory-controls").hidden = !automatic;
        document.getElementById("legacy-people-controls").hidden = automatic;
        document.getElementById("personal-memory-state").textContent = settings.scope === "personal" ? "Your memories are active." : "Personal memory is paused while someone else may be present.";
        document.getElementById("resume-personal").hidden = settings.scope !== "shared";
        document.getElementById("person-voice").disabled = !settings.speaker_ready;
        document.getElementById("person-enrollment").textContent = settings.enrollment_pending ? "Listening for the consenting person's voice. Speak alone for 3–12 seconds within 90 seconds." : "";
        document.getElementById("cancel-enrollment").hidden = !settings.enrollment_pending;
        document.querySelector('#person-form button[type="submit"]').disabled = !!settings.enrollment_pending;
        const people = document.getElementById("people-list");people.replaceChildren();
        (settings.people || []).forEach(p => {
            const row=document.createElement("div");row.className="memory-item";
            const name=document.createElement("p");name.textContent=`${p.name} · ${[p.face && "Face remembered",p.voice && "Voice remembered"].filter(Boolean).join(" · ")}`;
            row.append(name,action("Forget face & voice",()=>{
                if(window.confirm(`Forget ${p.name}'s saved face and voice? Text memories are kept.`))sendControl({type:"forget_person",person_id:p.id});
            }));people.append(row);
        });
        if (automatic && !people.children.length) people.textContent="No introductions yet.";
        const select = document.getElementById("profile-select");
        select.replaceChildren(new Option("No profile selected", ""));
        settings.profiles.forEach(p => select.add(new Option(p.name, p.id)));
        select.value = settings.owner_id || "";
        document.getElementById("delete-profile").disabled = !settings.owner_id;
        document.getElementById("load-memories").disabled = settings.scope !== "personal";
        document.getElementById("memory-form").hidden = settings.scope !== "personal";
        document.getElementById("session-scope").textContent = settings.scope === "shared" ? "Shared session — personal memories hidden" : settings.scope === "personal" ? "Personal session — selected profile memories may be used" : "No personal profile in use";
        if (settings.scope !== "personal") renderMemories([]);
        const guests = document.getElementById("guest-list");
        guests.replaceChildren();
        settings.guests.forEach(g => {
            const row = document.createElement("div"); row.className = "guest-item";
            const name = document.createElement("p"); name.textContent = `${g.name} — ${g.invited ? "invited" : "present, not invited"}`; row.append(name);
            if (!g.invited) row.append(action("Invite to conversation", () => sendControl({type:"invite_guest",guest_id:g.id})));
            row.append(action("Mark as gone", () => sendControl({type:"remove_guest",guest_id:g.id})));
            guests.append(row);
        });
    }

    function action(label,handler) {
        const button = document.createElement("button");
        button.type="button";button.className="action-btn secondary-btn";button.textContent=label;button.addEventListener("click",handler);
        return button;
    }

    function renderVision(vision) {
        const state = document.getElementById('vision-state');
        const identity = document.getElementById('face-identity');
        if (!vision) {
            state.textContent = 'Automatic vision is disabled in this session.';
            identity.textContent = '';
            return;
        }
        state.textContent = ['camera', 'screen'].map(source => {
            const value = vision[source];
            const label = source === 'camera' ? 'Camera' : 'Screen';
            return !value.enabled ? `${label} off` : value.available ? `${label} active` : value.error || `${label} starting…`;
        }).join(' · ');
        const faces = vision.identity;
        identity.textContent = faces.error || (faces.matches.length
            ? `Face match: ${faces.matches.map(face => face.name).join(', ')}. Recognition is an estimate.`
            : faces.face_count ? `${faces.face_count} face(s) visible; no saved match.` : 'No face recognized.');
    }

    let memoryItems = [];
    const memoryShown = {}, MEMORY_ORDER = ["People", "Events", "Plans", "Technical", "Learnings", "Reflections", "Notes"];
    function renderMemories(items) { memoryItems = items; drawMemories(); }

    function memoryRow(m) {
        const row=document.createElement("div");row.className="memory-item";
        const text=document.createElement("p");text.textContent=m.content;
        const source=document.createElement("p");source.className="control-help";
        source.textContent=[m.date, m.source, m.superseded ? "Replaced by a newer fact" : ""].filter(Boolean).join(" · ");
        if(m.editable === false){source.textContent += " · Edit this note in Obsidian";row.append(text,source);return row;}
        const edit=document.createElement("textarea");edit.value=m.content;edit.maxLength=2000;edit.hidden=true;edit.setAttribute("aria-label","Edit saved memory");
        const save=action("Save correction",()=>{ if(edit.value.trim()) sendControl({type:"edit_memory",memory_id:m.id,content:edit.value}); });save.hidden=true;
        row.append(text,source,action("Edit",()=>{edit.hidden=false;save.hidden=false;edit.focus();}),edit,save,action("Delete",()=>{sendControl({type:"delete_memory",memory_id:m.id});}));
        return row;
    }

    function drawMemories() {
        const list = document.getElementById("memory-list");
        const query = document.getElementById("memory-search").value.trim().toLowerCase();
        const replaced = document.getElementById("memory-replaced").checked;
        const open = new Set([...list.querySelectorAll("details[open]")].map(d => d.dataset.category));
        document.getElementById("memory-tools").hidden = !memoryItems.length;
        list.replaceChildren();
        const groups = {}, shown = memoryItems.filter(m => (replaced || !m.superseded) && (!query || m.content.toLowerCase().includes(query)))
            .sort((a, b) => (b.date || "").localeCompare(a.date || ""));  // Newest first; undated keep the server order.
        shown.forEach(m => (groups[m.category || "Notes"] ??= []).push(m));
        const rank = c => (MEMORY_ORDER.indexOf(c) + 1 || 99);
        Object.keys(groups).sort((a, b) => rank(a) - rank(b)).forEach(category => {
            const items = groups[category], limit = memoryShown[category] || 20;
            const group = document.createElement("details");group.className="memory-group";group.dataset.category = category;
            group.open = open.has(category) || Boolean(query) || shown.length <= 20;  // Few memories: no need to unfold.
            const summary = document.createElement("summary");summary.textContent = `${category} (${items.length})`;
            group.append(summary, ...items.slice(0, limit).map(memoryRow));
            if (items.length > limit) group.append(action(`Show more (${items.length - limit} left)`, () => { memoryShown[category] = limit + 20; drawMemories(); }));
            list.append(group);
        });
        if (!list.children.length && memoryItems.length) list.textContent = "No memories match.";
    }

    function renderExpressions() {
        const select=document.getElementById("emotion-select");const previous=select.value;select.replaceChildren();
        Object.entries(inventory).forEach(([name,info])=>{
            const option=new Option(name + (info.available ? "" : " — unavailable"),name);option.disabled=!info.available;select.add(option);
        });
        if (!select.options.length) select.add(new Option("Connect an avatar renderer first", ""));
        if (inventory[previous]?.available) select.value=previous;
        expressionChanged();
    }
    function expressionChanged() {
        const value=document.getElementById("emotion-select").value;
        const info=inventory[value];
        document.getElementById("preview-btn").disabled=!info?.available;
        const targets=(info?.backends || []).map(name=>name === "overlay" ? "desktop overlay" : "VTube Studio");
        document.getElementById("expression-note").textContent=(info?.note || "Preview on a connected avatar renderer.") + (targets.length ? " Preview target: " + targets.join(" and ") + "." : " Connect VTube Studio or the desktop overlay to preview.");
    }

    micToggle.addEventListener("change",()=>{
        const enabled=micToggle.checked;micToggle.disabled=true;
        sendControl({type:"set_mic",enabled});
    });
    document.getElementById("input-mode").addEventListener("change",e=>sendControl({type:"set_input_mode",mode:e.target.value}));
    document.getElementById("companion-mode").addEventListener("change",e=>sendControl({type:"set_mode",mode:e.target.value}));
    document.getElementById("translation-language").addEventListener("change",e=>sendControl({type:"set_translation_language",language:e.target.value}));
    document.getElementById("initiative-mode").addEventListener("change",e=>sendControl({type:"set_initiative_mode",mode:e.target.value}));
    for (const [id, type, text] of [["check-update", "check_update", "Checking…"], ["apply-update", "apply_update", "Updating; this can take a few minutes…"]])
        document.getElementById(id).addEventListener("click", () => {
            if (!sendControl({type})) return;
            document.getElementById("check-update").disabled = document.getElementById("apply-update").disabled = true;
            document.getElementById("update-state").textContent = text;
        });
    document.getElementById("describe-again").addEventListener("click", () => {
        if (sendControl({type: "describe_appearance"})) document.getElementById("appearance-text").textContent = "Looking at this avatar…";
    });
    document.getElementById("load-voices").addEventListener("click", () => sendControl({type: "list_voices"}));
    document.getElementById("use-voice").addEventListener("click", () => {
        if (heardVoice && sendControl({type: "set_voice", style: heardVoice.id})) {
            pendingVoice = heardVoice.id; document.getElementById("voice-pick-state").textContent = "Switching her voice…";
        }
    });
    document.getElementById("brain-provider").addEventListener("change", e => askModels(e.target.value.trim()));
    document.getElementById("brain-provider").addEventListener("focus", () => {
        if (!providersAsked && sendControl({type: "list_providers"})) providersAsked = true;  // Runs `hermes auth list` once.
    });
    document.getElementById("save-brain").addEventListener("click", () => {
        const values = Object.fromEntries(BRAIN_KEYS.map(k => [k, document.getElementById(`brain-${k}`).value]));
        sendControl({type: "set_brain", ...values});
    });
    document.getElementById("test-brain").addEventListener("click", () => {
        if (!sendControl({type: "test_brain"})) return;
        document.getElementById("test-brain").disabled = true;
        document.getElementById("brain-state").textContent = "Asking the model…";
    });
    document.getElementById("save-key").addEventListener("click", () => {
        const input = document.getElementById("brain-key-input");
        if (input.value.trim() && sendControl({type: "set_api_key", key: input.value})) input.value = "";  // Never kept in the page.
    });
    document.getElementById("save-persona").addEventListener("click",()=>sendControl({type:"set_persona",persona:document.getElementById("persona").value}));
    document.getElementById("stop-btn").addEventListener("click",()=>sendControl({type:"stop"}));
    document.getElementById("resume-btn").addEventListener("click",()=>sendControl({type:"resume_topic"}));
    document.getElementById("profile-select").addEventListener("change",e=>sendControl({type:"select_profile",profile_id:e.target.value || null}));
    document.getElementById("person-form").addEventListener("submit",e=>{
        e.preventDefault();
        sendControl({type:"enroll_person",name:document.getElementById("person-name").value,
            face:document.getElementById("person-face").checked,voice:document.getElementById("person-voice").checked,
            consent:document.getElementById("person-consent").checked});
    });
    for(const id of ['person-name','person-face','person-voice'])document.getElementById(id).addEventListener('input',()=>{
        document.getElementById('person-consent').checked=false;
    });
    document.getElementById("cancel-enrollment").addEventListener("click",()=>sendControl({type:"cancel_enrollment"}));
    document.getElementById("resume-personal").addEventListener("click",()=>sendControl({type:"resume_personal"}));
    document.getElementById("tab-people-btn").addEventListener("click",()=>{
        if(settings?.automatic_memory)sendControl({type:"memory_status"});
    });
    document.getElementById("profile-form").addEventListener("submit",e=>{
        e.preventDefault();
        if(sendControl({type:"create_profile",name:document.getElementById("profile-name").value,consent:document.getElementById("profile-consent").checked}))e.target.reset();
    });
    document.getElementById("delete-profile").addEventListener("click",()=>{
        if(settings?.owner_id && window.confirm("Delete this profile and all its saved memories?"))sendControl({type:"delete_profile",profile_id:settings.owner_id});
    });
    document.getElementById("guest-form").addEventListener("submit",e=>{
        e.preventDefault();if(sendControl({type:"guest_present",name:document.getElementById("guest-name").value}))e.target.reset();
    });
    document.getElementById("memory-form").addEventListener("submit",e=>{
        e.preventDefault();if(sendControl({type:"add_memory",content:document.getElementById("memory-content").value,consent:document.getElementById("memory-consent").checked}))e.target.reset();
    });
    document.getElementById("load-memories").addEventListener("click",()=>sendControl({type:"list_memories"}));
    document.getElementById("memory-search").addEventListener("input",drawMemories);
    document.getElementById("memory-replaced").addEventListener("change",drawMemories);
    document.getElementById("expression-panel").addEventListener("toggle",()=>sendControl({type:"avatar_inventory"}));
    document.getElementById("emotion-select").addEventListener("change",expressionChanged);
    document.getElementById("preview-btn").addEventListener("click",()=>sendControl({type:"preview_emotion",emotion:document.getElementById("emotion-select").value}));
    const insertDraft=action("Insert voice draft",()=>{
        if(voiceDraft) { chatInput.value = (chatInput.value.trim() + " " + voiceDraft).trim();voiceDraft="";chatInput.focus(); }
        insertDraft.hidden = true;
    });
    insertDraft.hidden = true;
    document.getElementById("input-mode").after(insertDraft);

    window.chassie = {send: sendControl};
    // Start WebSocket Connection
    connect();
});
