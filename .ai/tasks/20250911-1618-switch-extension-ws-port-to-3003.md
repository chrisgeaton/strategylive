# Task: Switch extension WebSocket port to 3003

## Date
2025-09-11 16:18

## Prompt
please change to 3003

## Context
The backend server is configured via `.env` to listen on `PORT=3003`. The extension content script still pointed to `ws://localhost:3001/`, causing connection failures.

## Actions Taken
1. Updated `extension/content.js` to use `ws://localhost:3003/` for the WebSocket base URL.

## Files Changed
- `extension/content.js` — `SERVER_URL` updated from port 3001 to 3003.

## Testing
- After restarting the backend on port 3003, the extension should establish a WS connection and stream audio.

## Outcome
Extension and backend are aligned on port 3003.

