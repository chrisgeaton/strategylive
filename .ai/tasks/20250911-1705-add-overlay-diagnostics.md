# Task: Add overlay diagnostics (owner, status, last error)

## Date
2025-09-11 17:05

## Prompt
yes

## Context
Troubleshooting start issues requires quick visibility in the Meet overlay without opening DevTools.

## Actions Taken
1. Offscreen: annotate all forwarded messages with `owner: 'offscreen'`.
2. Overlay: show `Status`, `Source`, and a help panel with last error/call-to-action.

## Files Changed
- `extension/offscreen.js` — add `owner: 'offscreen'` to status and forwarded WS messages.
- `web/overlay/src/main.tsx` — diagnostics UI state and rendering.

## Testing
- Confirmed overlay shows Source: offscreen and surfaces last errors.

## Outcome
Easier diagnosis of capture state and errors directly in the overlay.

