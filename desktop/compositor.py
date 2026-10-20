"""Scoped session rules for transparent Chassie windows on Hyprland's Lua API.

No user configuration files are modified. Reloading Hyprland clears runtime rules;
restart the overlay to register them again. Other desktops are left untouched.
"""
import os
import subprocess

APPLICATION_ID = 'chassie-overlay'

# Scope avatar and transparent controls separately from opaque application panels.
# A session-global handle prevents duplicate registration across overlay restarts.
HYPRLAND_RULE = '''
if not _G.chassie_overlay_rule then
    _G.chassie_overlay_rule = hl.window_rule({
        name = "chassie-avatar-overlay",
        match = { class = "^chassie-overlay$", title = "^Chassie$" },
        float = true,
        pin = true,
        no_blur = true,
        no_shadow = true,
        border_size = 0,
        rounding = 0,
    })
end
if not _G.chassie_controls_rule then
    _G.chassie_controls_rule = hl.window_rule({
        name = "chassie-avatar-controls",
        match = { class = "^chassie-overlay$", title = "^Chassie (controls|subtitle)$" },
        float = true,
        pin = true,
        no_blur = true,
        no_shadow = true,
        border_size = 0,
        rounding = 0,
    })
end
if not _G.chassie_bubbles_rule then
    _G.chassie_bubbles_rule = hl.window_rule({
        name = "chassie-avatar-bubbles",
        match = { class = "^chassie-overlay$", title = "^Chassie bubble .*$" },
        float = true, pin = true, no_blur = true, no_shadow = true,
        border_size = 0, rounding = 0,
    })
end
if not _G.chassie_chat_rule then
    _G.chassie_chat_rule = hl.window_rule({
        name = "chassie-floating-chat",
        match = { class = "^chassie-overlay$", title = "^Chassie — Conversation$" },
        float = true, pin = true, no_blur = true, no_shadow = true,
        border_size = 0, rounding = 0,
    })
end
'''


def configure_hyprland(*, environ=None, run=None):
    environ = os.environ if environ is None else environ
    run = subprocess.run if run is None else run
    if not environ.get('HYPRLAND_INSTANCE_SIGNATURE'):
        return False
    try:
        result = run(['hyprctl', 'eval', HYPRLAND_RULE],
                     capture_output=True, text=True, timeout=3, check=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise RuntimeError('Hyprland overlay rules unavailable: check hyprctl access. See docs/overlay.md.') from exc
    if result.returncode != 0 or result.stdout.strip() != 'ok':
        raise RuntimeError('Hyprland rejected overlay rules. Lua configuration support is required; see docs/overlay.md.')
    return True
