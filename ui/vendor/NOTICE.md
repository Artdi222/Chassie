# Browser runtime dependencies

Local copies avoid a network dependency when opening the model studio.

- PixiJS 7.4.3, MIT: https://github.com/pixijs/pixijs/tree/v7.4.3 — from the npm package pixi.js@7.4.3, dist/pixi.min.js
- pixi-live2d-display-lipsyncpatch 0.5.0-ls-8, MIT (a maintained fork of guansss/pixi-live2d-display with the Cubism 5 framework: multiply/screen colours, inverted masks): https://github.com/RaSan147/pixi-live2d-display — from the npm package, dist/cubism4.min.js
- Live2D Cubism Core, copyright Live2D Inc. Redistributable code under its embedded license: https://www.live2d.com/eula/live2d-proprietary-software-license-agreement_en.html — downloaded from https://cubism.live2d.com/sdk-web/cubismcore/live2dcubismcore.min.js

One local change in `pixi-live2d-0.5.0-ls-8.min.js` (marked at the top of the file): the WebGL renderer's
`initialize()` picks enough mask render textures for the model (32 clip contexts each) instead of always one.
With one texture only 36 masks fit, so Cubism 5 models with more masks drew blush and mouth outside the face.

Original copyright/license headers are preserved. User-supplied model packages remain under their creators' terms and are not modified.
