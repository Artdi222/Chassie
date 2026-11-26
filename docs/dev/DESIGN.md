---
name: Chassie Companion Studio
description: A warm cream-and-lilac companion interface built around actual Live2D models, matched to the Chassie app icon.
colors:
  ink: "#2e2124"
  muted: "#6a5559"
  paper: "#fbf4ee"
  white: "#fffcf9"
  inset: "#fbf2ec"
  accent: "#76599a"
  accent-strong: "#61477f"
  accent-soft: "#f3eaf6"
  accent-ring: "#c7a9cd"
  line: "#efe2dc"
  night: "#2b1f22"
typography:
  headline:
    fontFamily: "Outfit, 'Segoe UI', sans-serif"
    fontSize: "21px"
    fontWeight: 550
    letterSpacing: "-.025em"
  title:
    fontFamily: "Outfit, 'Segoe UI', sans-serif"
    fontSize: "16px"
    fontWeight: 550
    letterSpacing: "-.025em"
  body:
    fontFamily: "Outfit, 'Segoe UI', sans-serif"
    fontSize: "14px"
    fontWeight: 400
  label:
    fontFamily: "Outfit, 'Segoe UI', sans-serif"
    fontSize: "13px"
    fontWeight: 400
rounded:
  compact: "8px"
  field: "9px"
  button: "10px"
  content: "12px"
  panel: "16px"
  circle: "50%"
spacing:
  small: "8px"
  control: "10px"
  compact: "12px"
  content: "16px"
  roomy: "22px"
  section: "24px"
components:
  button-icon:
    textColor: "{colors.ink}"
    rounded: "{rounded.button}"
    size: "38px"
  button-primary:
    backgroundColor: "{colors.accent}"
    textColor: "{colors.white}"
    rounded: "{rounded.button}"
    size: "38px"
  button-soft:
    backgroundColor: "{colors.white}"
    textColor: "{colors.ink}"
    rounded: "{rounded.button}"
    padding: "10px 15px"
  button-text:
    textColor: "{colors.accent}"
    rounded: "{rounded.compact}"
    padding: "10px"
  button-round:
    backgroundColor: "{colors.white}"
    textColor: "{colors.accent}"
    rounded: "{rounded.circle}"
    size: "46px"
  field:
    backgroundColor: "{colors.white}"
    textColor: "{colors.ink}"
    rounded: "{rounded.field}"
    padding: "10px 12px"
  choice:
    textColor: "{colors.ink}"
    rounded: "{rounded.compact}"
    padding: "8px 12px"
  choice-selected:
    backgroundColor: "{colors.accent}"
    textColor: "{colors.white}"
    rounded: "{rounded.compact}"
    padding: "8px 12px"
  model-option:
    backgroundColor: "{colors.white}"
    textColor: "{colors.ink}"
    rounded: "{rounded.content}"
    padding: "16px"
---

# Design System: Chassie Companion Studio

> 2026-11 redesign: pill-shaped controls and floating stage toolbar, real toggle switches, segmented settings
> tabs, model cards with an "Add another model" importer, and a four-step first-run onboarding
> (`ui/onboarding.html`) with a live model preview. Tokens live as CSS variables at the top of `ui/style.css`.

## Overview

**Creative North Star: "Cozy Cream Companion"** (2026-11-26, from the app icon `ui/public/chassie-icon.png`)

A warm cream shell gives the actual Live2D character visual priority. The palette is taken from the app icon: cream background, cocoa ink from her hair, mauve actions, a lilac focus ring from her hair clip, and a cream-to-lavender stage gradient. Compact outline icons carry the interface across browser and desktop panels.

The name below describes the approved lavender companion direction; it is documentation language, not an additional user-approved brand concept. This records the implemented system in ui/style.css, ui/index.html, ui/studio.js, and desktop/studio.py.

**Key Characteristics:**

- Warm cream foundations with mauve interaction states; lavender only on the stage and washes.
- Outfit typography with compact controls and restrained headings.
- Warm-white rounded panels and circular avatar actions; the app icon is the wordmark logo.
- Actual model assets, spoken subtitles, and shared web panel styling.

## Colors

A warm cream foundation supports cocoa ink and a mauve interaction accent. White text on `accent` is 5.7:1; `accent` on `paper` is 5.3:1.

### Primary

- **Companion Mauve** (`accent`): buttons, active appearance choices, microphone controls, and outline icons.
- **Soft Lilac** (`accent-soft`): selected model tiles, hover surfaces, and control notices.

### Neutral

- **Cocoa Ink** (`ink`): headings and primary interface text.
- **Muted Cocoa** (`muted`): descriptions, status captions, help, and metadata.
- **Cream Paper** (`paper`): application background and inset settings surfaces.
- **Warm White** (`white`): chat, dialogs, fields, and circular actions.
- **Blush Line** (`line`): dividers, input outlines, and unselected model borders.

**The Accent Signals Action Rule.** Use mauve for actionable controls and selected appearance choices; use muted ink for supporting information.

## Typography

**Body and heading font:** bundled Outfit, with Segoe UI and sans-serif fallbacks. Native Qt window chrome uses the platform font; it does not establish a separate display-font rule.

The scale is compact and functional. Panel headlines and section titles use a medium heading weight with slightly tightened tracking. Body and label roles retain ordinary tracking. Soft action buttons use a slightly stronger label weight (500).

The reusable hierarchy is captured in the frontmatter. Model stage titles additionally use a larger heading (30px, reduced to 24px on narrow screens); that stage-specific treatment is not a general display token. Paragraphs use a relaxed line height (1.55); conversation bubbles use a more open line height (1.65). Subtitles are larger than chat body copy.

## Layout

The browser uses a full viewport flex shell, capped at 2000px. Its header sits above the flexible avatar stage and right conversation panel. Chat is 360px wide, growing to 400px from the 1600px breakpoint. The stage absorbs remaining width and clips the movable character. The default framing is centered and waist-up, with subtitles above the bottom controls.

At widths up to 800px, shell padding contracts, secondary header text disappears, and chat starts collapsed. When opened, chat overlays the stage at its bottom-right corner, with width limited to the available space and height at 60% of the workspace. Model tiles remain a two-column grid; appearance choices wrap.

Browser dialogs are centered and constrained to the viewport, with independent vertical scrolling. Settings use the narrower panel variant. Desktop chat floats above-left of the avatar; other desktop panels open centered. The desktop avatar remains transparent. The desktop action menu follows a left-facing arc around the avatar, using five independent alpha windows on a shallow curve, with no shared menu window behind them. The gaps belong to the underlying desktop. Avoid QWidget.setMask on these windows: its X11 bounding shape produces black corners on this XWayland compositor. It remains visible when opening a panel. Desktop controls and panels are owned by the avatar window to keep them above it; the compositor disables blur and shadow specifically for the transparent controls. The browser retains its horizontal circular-action menu.

Repeated spacing favors compact control gaps, medium content padding, and larger section breaks, as listed in the frontmatter.

**The Shared Panel Rule.** Reuse browser panel content inside desktop windows; embedded content fills its host without an extra outer radius or modal shadow.

## Elevation & Depth

Tonal layering establishes the ordinary hierarchy: lavender shell, slightly deeper stage, white chat and panel surfaces, and fine lavender dividers. Diffuse shadows lift dialogs, the narrow-screen chat overlay, and circular avatar actions. Browser dialogs also dim the background; native panels rely on window placement and their white surface.

The sidecar records the exact shared panel and circular-action shadow values. These are ambient shadows, with no hard offset edge.

**The Floating Depth Rule.** Use diffuse shadows for floating panels and avatar actions; separate ordinary settings content with tone and fine borders.

## Shapes

Use gently rounded rectangular controls, fields, and containers from the recorded radius scale. Full circles identify click-to-open avatar actions. Chat and modal panels share the panel radius; inset cards and model options use the content radius. Fields and small buttons are more compact. Thin borders define fields, unselected choices, and model tiles.

The avatar stage has a larger corner treatment specific to its enclosing canvas. Outgoing chat bubbles have a small lower-right corner; incoming assistant text stays visually open. Neither shape replaces the general panel vocabulary.

## Components

### Buttons

Compact text and outline-icon actions use purple hover surfaces; the filled send action uses the primary purple with white content and a darker hover. Soft buttons use white at rest. Circular avatar actions reverse to purple with white icons on hover in the browser; native circular actions use a pale lavender hover.

The focus-visible outline applies to buttons, links, fields, and summaries. Disabled buttons lower opacity and use the disabled cursor. The sidecar preserves exact focus and hover values. Icons use SVG strokes with rounded caps and joins; ordinary browser icons are 21px, native action icons are 22px.

### Chips

Appearance choices are wrapping outlined buttons. Selection fills the button with purple and sets white text; the state is exposed with `aria-pressed`. Available choices come from the selected model's real presets. An empty group shows explanatory text.

### Cards / Containers

Model options are left-aligned selectable tiles with a title and muted preset count. Selected tiles use soft lavender with a stronger purple border. Settings status containers use lavender paper; chat and floating panels use white. The model picker uses a two-column grid.

Automatic vision uses the same shared controls panel in browser and embedded desktop views. Camera and screen capture states and estimated face matches appear as read-only status text, with supporting copy explaining automatic snapshots and spoken or typed chat commands for face enrollment and deletion. Keep these instructions beside the status without adding activation buttons.

### Inputs / Fields

Settings fields use white surfaces, fine lavender borders, and the field radius. The chat composer groups a transparent text input and send button in a soft inset container. Checkbox and range accents use purple. Retain visible focus treatment for keyboard navigation.

### Navigation

The header holds the wordmark and settings action. The stage toolbar groups framing controls separately from voice controls. Clicking the model opens circular chat, model, wardrobe, and settings actions; the desktop adds Stop. Dragging repositions the avatar rather than opening the menu. Escape dismisses the browser menu and modal; modal focus is contained and returned to its opener.

### Subtitles and motion

Spoken text appears on a dark rounded background with white centered text. Browser subtitles sit near the bottom of the stage; native subtitles float above the desktop avatar. Empty subtitles are hidden. Subtitle placement is surface-specific, while the contrast treatment is shared.

The browser avatar action row enters with a short fade and vertical shift. Reduced-motion preference removes CSS animations and transitions. The current model renderer's idle movement is separate from that CSS override.

## Do's and Don'ts

### Do:

- Do preserve the actual model as the visual focus and use its supplied assets.
- Do use the existing purple selected states and visible keyboard focus treatment.
- Do keep chat and settings content consistent between browser and embedded desktop panels.
- Do distinguish a model click from a drag, and preserve the reduced-motion override.

### Don't:

- Don't invent expression or outfit choices when the selected model has no matching assets.
- Don't add opaque application chrome behind the transparent desktop avatar.
