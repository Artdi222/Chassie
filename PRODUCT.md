# Chassie
<!-- impeccable:product-schema 1 -->

## Platform
web

## Users and purpose
Personal local AI companion with a browser application and a transparent Linux desktop avatar. The immediate task is comparing four supplied Live2D models and their actual expressions/outfits alongside a local Japanese character voice.

## Confirmed interaction
Browser: waist-up avatar centered in its stage, spoken subtitles below, collapsible chat at right. Desktop: launch from an application icon, click avatar for circular action buttons, floating chat above-left, centered settings, manual outfit/expression controls. Share conversation and model selection between surfaces. Preserve a single audio output.

## Constraints
Keep the existing Python/aiohttp/Qt stack and working conversation controls. Local computer only. Preserve original model assets and archives. Discover capabilities per model; do not invent missing outfit assets. Use local VOICEVOX Mochiko-san speech in Japanese with mood-dependent styles. Typed and microphone input accept Indonesian or English; reply chat and subtitles display English translations. Edge English speech remains a configurable alternative. Prior documented hardware budget is 4 GB VRAM / 8 GB RAM.

## Decisions confirmed in conversation
One character voice with mood-dependent delivery is the desired future direction. Web use starts locally. Model selection and UI implementation precede TTS evaluation. User supplied the composition and radial-menu interaction and approved implementation.

All built-in interface labels, accessibility labels, desktop panel titles, tooltips, preset display names, and system notices use English. Preserve user-authored content and original model asset identifiers.
