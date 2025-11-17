# StrategyLive Real-Time Sales Assistant - Architecture

## Overview
An MVP that augments Google Meet sales calls with real-time transcription and contextual suggestions.

## Components
- Browser Extension (MV3)
  - Captures tab audio via `chrome.tabCapture` on Google Meet.
  - Injects a small overlay (iframe) to display transcript and suggestions.
  - Streams 16-bit PCM audio frames via WebSocket to the Python backend.
- Backend (Python + WebSocket)
  - **File**: `whisper_server.py` - Main WebSocket server
  - Accepts PCM audio frames per client connection.
  - Processes audio locally using **OpenAI Whisper** model (no external API calls).
  - Channel-based speaker detection: ch0=mic (sales), ch1=tab (prospect).
  - Advanced conversation intelligence with phase detection and coaching triggers.
  - Generates contextual AI coaching suggestions via **Claude 3.5 Sonnet**.
  - **Session logging** to `logs/coaching_session_*.log` files.
  - Pushes transcripts (with speaker identification) and AI suggestions back over WebSocket.
- Overlay UI (React + Vite)
  - Rendered inside an iframe injected by the content script.
  - Receives status/transcript/suggestions from content script via `window.postMessage`.
  - Advanced UI with phase indicators, confidence scores, and suggestion priority levels.

## Data Flow
1. Extension starts capture on Meet tab (action button).
2. Content script converts audio float frames -> 16-bit PCM LE at ~48kHz; stereo when mic present (L=mic, R=tab).
3. WebSocket sends PCM buffers to Python backend on `ws://localhost:3003`.
4. **Backend processes audio locally with Whisper** - saves temporary WAV files for transcription.
5. **AI Coaching Engine** analyzes conversation context and generates suggestions via Claude API.
6. **Session Logger** records all activity to timestamped log files.
7. Backend emits transcript messages with speaker identification and coaching suggestions.
8. Content script relays messages to the overlay iframe, which renders them with advanced UI.

## APIs & SDKs
- **OpenAI Whisper**: Local speech-to-text model (tiny/small variants)
- **Anthropic Claude**: `anthropic` Python library for AI coaching suggestions
- **WebSocket**: `websockets` Python library for backend; native browser WebSocket in extension
- **Session Logging**: Custom `SessionLogger` class with file-based logging

## Configuration
- Environment variables in `.env` (see `.env.example`):
  - `ANTHROPIC_API_KEY` - Required for AI coaching suggestions
- Python dependencies:
  - `pip install whisper openai-whisper anthropic aiohttp websockets python-dotenv`

## Session Logging System
- **Location**: `logs/coaching_session_YYYYMMDD_HHMMSS.log`
- **Contents**:
  - Session metadata (ID, duration, timestamp)
  - All transcripts with speaker identification and confidence scores
  - Suggestion decision logging (when blocked and detailed reasons why)
  - Generated suggestions with priority levels, techniques, and full text
  - Session summary with statistics (transcript count, suggestion count, etc.)

## Build & Run
1. Copy `.env.example` to `.env` and set `ANTHROPIC_API_KEY`.
2. Install Python dependencies: `pip install whisper openai-whisper anthropic aiohttp websockets python-dotenv`
3. Install Node dependencies: `npm install`
4. Build overlay: `npm run build:overlay` (outputs to `extension/overlay`)
5. Start Python backend: `python whisper_server.py` (listens on `ws://localhost:3003`)
6. Load extension:
   - Go to `chrome://extensions` → Enable Developer mode
   - Load unpacked → select the `extension/` folder
7. Open a Google Meet call; click the extension icon to toggle capture.
8. Review session logs in `logs/coaching_session_*.log` after calls.

## AI Coaching Features
- **Phase Detection**: Opening, Discovery, Demo, Closing phases
- **Speaker Recognition**: Sales rep vs. prospect via audio channel separation
- **Conservative Triggering**: Only suggests after prospect statements with meaningful content
- **Cooldown System**: 45-second minimum between suggestions to avoid overwhelming
- **Priority Levels**: HIGH/MEDIUM/LOW priority suggestions with different visual styling
- **Technique Classification**: Rapport building, discovery questions, objection handling, etc.

## Security & Privacy Notes
- Audio is processed locally with Whisper (no external transcription API calls).
- Only transcribed text is sent to Claude API for coaching suggestions.
- Session logs stored locally in `logs/` directory.
- Ensure secure transport (WSS/HTTPS) in production and obtain participant consent.

## Debugging & Troubleshooting
- **Console logs**: Python backend shows detailed processing steps
- **Session logs**: `logs/coaching_session_*.log` contains complete session analysis
- **Extension debugging**: Use Chrome DevTools on extension popup and content scripts
- **Common issues**:
  - Whisper model download on first use may take time
  - FFmpeg required for audio processing (Windows path configured in code)
  - ANTHROPIC_API_KEY must be set for coaching suggestions
