# Task: Scaffold real-time sales assistant MVP (Meet + Deepgram + Claude)

## Date
2025-09-11 14:25

## Prompt
I'm building a real-time sales conversation assistant MVP that works with Google Meet calls. The tool should:
- Capture audio from Google Meet via browser extension
- Transcribe speech in real-time using Deepgram API
- Generate contextual sales suggestions using Claude API
- Display suggestions in a non-intrusive overlay

Create a project structure with:
- Browser extension manifest and basic files
- Real-time audio capture setup
- WebSocket backend for processing
- Simple React frontend for suggestion display

Set up package.json with dependencies for:
- Audio processing (WebRTC)
- Real-time transcription (Deepgram SDK)
- LLM integration (Anthropic SDK)
- WebSocket communication
- Browser extension APIs

Include initial configuration files and environment setup.
Document the architecture decisions and setup process for future reference.

## Context
We need a cohesive scaffold that ties together extension-based audio capture, a backend that streams to Deepgram and Anthropic, and a lightweight overlay UI. This is an MVP; correctness and clear structure are prioritized over feature completeness.

## Actions Taken
1. Added `package.json` with dependencies: `deepgram-sdk`, `@anthropic-ai/sdk`, `ws`, `express`, `dotenv`, `react`, `react-dom`, plus Vite and plugin for overlay build.
2. Created `.env.example` with keys for Deepgram and Anthropic and server port.
3. Implemented backend WebSocket server (`server/index.js`) with Deepgram live transcription and Claude suggestion stubs.
4. Added Deepgram and Claude client wrappers in `server/lib/`.
5. Created Chrome extension (MV3): `extension/manifest.json`, `background.js`, `content.js` with tab audio capture and WS streaming; overlay injection via iframe.
6. Scaffolded React overlay app with Vite in `web/overlay/`, output targeting `extension/overlay/`.
7. Wrote architecture and setup docs in `docs/architecture.md` and updated `README.md` with quickstart.

## Files Changed
- `package.json` - Project scripts and dependencies.
- `.env.example` - Environment configuration template.
- `server/index.js` - WebSocket backend with Deepgram/Claude integration points.
- `server/lib/deepgramClient.js` - Deepgram live session wrapper.
- `server/lib/claudeClient.js` - Anthropic suggestion helper.
- `extension/manifest.json` - MV3 manifest with permissions and content script.
- `extension/background.js` - Action click toggles capture.
- `extension/content.js` - Audio capture, PCM conversion, WS client, overlay messaging.
- `web/overlay/*` - React overlay (Vite, TS, main app).
- `docs/architecture.md` - Architecture decisions and setup process.
- `README.md` - Quickstart and component overview.

## Testing
- Static validation of file presence and references.
- Sanity review of data flow and permissions.
- Note: Actual runtime tests require API keys and Chrome extension load; documented steps provided.

## Outcome
MVP scaffold created with clear build/run instructions and architecture docs. Ready for integration testing with API keys.

## Notes
- Audio pipeline currently uses ScriptProcessor and 48kHz PCM for simplicity; consider AudioWorklet and resampling to 16k.
- In production, use WSS and auth; add rate limiting for Claude suggestions.

