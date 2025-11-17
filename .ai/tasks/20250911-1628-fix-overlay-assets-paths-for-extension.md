# Task: Fix overlay assets paths for Chrome extension

## Date
2025-09-11 16:28

## Prompt
GET chrome-extension://<id>/assets/index-....js net::ERR_FILE_NOT_FOUND

## Context
Vite was emitting absolute asset URLs (`/assets/...`) which, when loading `overlay/index.html` from a subfolder, causes Chrome to request assets from the extension root instead of under `overlay/`. Also, the manifest did not grant web-access to `overlay/assets/*`.

## Actions Taken
1. Set `base: './'` in `web/overlay/vite.config.ts` so built `index.html` references `./assets/...`.
2. Updated `extension/manifest.json` `web_accessible_resources` to include `"overlay/assets/*"`.

## Files Changed
- `web/overlay/vite.config.ts` — added `base: './'`.
- `extension/manifest.json` — added `overlay/assets/*` to resources.

## Testing
- Rebuild overlay: `npm run build:overlay`.
- Reload extension: Chrome → Extensions → Reload.
- Verify that `overlay/index.html` now loads its `./assets/...` scripts without `ERR_FILE_NOT_FOUND`.

## Outcome
Overlay asset URLs resolve correctly inside the extension; the runtime error is resolved.

