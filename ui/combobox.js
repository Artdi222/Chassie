// Searchable dropdowns shared by the studio (Settings) and the first-run setup.
window.ChassieCombobox = (() => {
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
    return {combobox, enhanceSelect};
})();
