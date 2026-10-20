# Local model studio and companion surfaces

Approved scope: safely extract three user-provided archives; support four model packages in a shared local catalog; implement browser avatar stage/subtitles/right chat and desktop click-menu/floating panels; provide an application launcher. Preserve current TTS and original model files.

1. Catalog: discover real model manifests, validate referenced paths, expose only renderer assets; inventory usable expression/outfit/prop files and safe derived manifests.
2. Shared state: serialize model changes and manual expression/outfit/prop selection, persist preferences, synchronize web/desktop, reject stale model controls.
3. Browser: local bundled Cubism/Pixi renderer, waist-up framing, model picker, actual expression/wardrobe controls, subtitle playback events, existing chat/settings/memory controls.
4. Desktop: native Cubism model switching; circular icon actions on click; drag distinct from click; floating embedded chat/settings/model panels; recovery tray; launcher owns only its child backend.
5. Verify: catalog and traversal tests, control validation and persistence, existing regression suite adjusted for user-moved Model_1 assets, browser screenshots with all models, native bounded render checks, launcher checks. Real TTS replacement and translation are deferred.

Visual direction follows the approved layout: a quiet pale lavender application shell, dark ink, purple action accents, actual model as the focus, compact outline icon controls, white chat/settings surfaces. Preserve the existing palette identity while replacing the chat-first layout. No generated substitute model imagery.

## Verification completed

- Three archives extracted safely; originals retained. Catalog validates four packages and all referenced assets: 34/10/8/0 usable presets for Model_1/2/3/4.
- Full regression suite: 150 passed in 41.31 seconds, including all four actual browser models, per-model control validation, allowlisted asset routes, focus/modal behavior, embedded Escape behavior, launcher ownership, and native readiness registration.
- Native Cubism loaded each model with transparency; integrated desktop check switched all four models, opened chat/model/settings/wardrobe panels and verified avatar click opens the circular action menu. Process exited cleanly. Qt logged non-fatal OpenGL cleanup warnings after embedded panels closed.
- Real bounded launcher check opened the native app, returned exit 0, and confirmed its owned backend stopped. No test conversation, microphone or camera capture was needed.
- Shortcut installed at ~/.local/share/applications/chassie.desktop. Local browser assets bundled; existing TTS preserved.
- Visual evidence: .test-artifacts/model-studio/ contains browser desktop/mobile, each real model, native switching and embedded-panel captures. Finish review's three findings (collapsed-chat overlap, embedded dismissal, keyboard focus) resolved. Automated style detector ran in degraded regex mode; browser checks provide interaction evidence.
- Product and design references: PRODUCT.md, DESIGN.md, .impeccable/design.json. Shared selections persist in .chassie/model-selection.json; desktop per-model framing in .chassie/overlay/window.json.


## Desktop arc correction

User feedback: horizontal controls sat behind the avatar inside compositor blur; button handlers hid the menu. Replaced the row with five masked circular targets on a left arc, kept the menu visible on actions, and made controls/panels transient children of the avatar. Added a separate scoped Hyprland no-blur/no-shadow rule for controls and subtitle. Screen clamping preserves the arc and gaps pass clicks through.

Verified 152 tests passing in 54.43 seconds, including a native subprocess using the production desktop entrypoint and actual QTest button clicks for chat, models, wardrobe, settings, and Stop. Native checks verify panel ownership, menu visibility after each action, renderer readiness, and live Hyprland no-blur/no-shadow properties. Evidence: .test-artifacts/desktop-arc.png and desktop-arc-check.log. Previous native crash log did not recur in these interaction checks; no unsupported claim of a Cubism-wide crash fix is made.


### Composited transparency correction

The user's screenshot disproved the earlier transparency claim: QWidget.grab and no_blur properties did not verify the actual desktop pixels. Replaced the shared menu surface with five independent 44px alpha windows and narrowed the arc to a 28px bow with 56px vertical spacing. X11 bounding masks caused black pixels even with an 8-bit alpha surface; removing setMask resolved the corners in the real compositor capture. Verification now uses grim over an owned opaque calibration backdrop and checks actual corner/gap pixels, plus five action clicks and native ownership. Evidence: .test-artifacts/desktop-bubbles-composited.png. A widget-only screenshot is insufficient evidence for desktop transparency.


### Panel click crash: confirmed root cause and regression

Real launcher cores 41729 and 50101 show QtWebEngine profile startup calling std::filesystem implementations exported by Live2D's _v3cpp.so, then throwing std::bad_alloc. Production qt_app imported Live2D before Qt; the old probe imported Qt first and masked the failure. The same import sequence reproduced SIGABRT (exit 134) in a headless first-panel probe without loading any model. Loading Qt before Live2D makes that probe exit 0 with JavaScript result PANEL_READY 2. The native probe now imports qt_app first too, and a separate cold-process headless regression protects the production import sequence. The allocation exception was not evidence that the machine needed more RAM.

Final verification after the import-order fix: 153 tests passed in 78.90 seconds. The native probe confirmed all five actions, transparent compositor gap/corner pixels, five independent 44px windows and transient ownership. The actual main application started after the patch and its Outfit & properti panel remained open; it was left running without restarting the user's active session.
