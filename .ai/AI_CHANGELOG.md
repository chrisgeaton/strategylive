# AI_CHANGELOG.md

## Overview
This changelog tracks AI-assisted work on the strategylive project.
Location: `.ai/AI_CHANGELOG.md`

---

## 2025-09-11

### Project Integration
- Set up AI tracking integration and documentation
  - Added `CLAUDE.md` with AI tracking protocol
  - Created root `README.md` noting `.ai/README.md`
  - Ensured `.ai/` is tracked via `.gitignore`
  - Created initial task log for this setup in `.ai/tasks/`
  - Cleaned `.ai/README.md` to fix encoding artifacts and standardize headings

### Documentation Updates
- Added an "AI Assistant Collaboration Directive" section to `README.md` instructing all AI assistants to act as discerning collaborators, avoid reflexive praise, and prioritize rigorous, objective feedback.

### MVP Scaffold
- Added project structure for Google Meet real-time assistant:
  - Backend WebSocket server with Deepgram/Claude integration points
  - Chrome extension (audio capture, overlay injection)
  - React overlay app (Vite) output into `extension/overlay`
  - Environment template and architecture documentation

### Audio Capture & Diarization
- Implemented dual-source capture (tab + mic) with stereo interleave for deterministic role mapping (sales vs prospect).
- Backend Deepgram Live now supports `channels=1|2` and maps channel index to `speaker` labels in transcript messages.
- Added reconnection and error reporting for permissions, devices, and network issues.
- Documented approach and testing in `docs/audio.md`.

### Conversation Intelligence
- Added word-level parsing, filler removal, and sentence segmentation using punctuation and pauses.
- Conversation state tracking with phases (opening→discovery→demo→objection→closing), topic hints, and speaker turns.
- Smart suggestion triggers: only on complete prospect statements, no interruptions, cooldown and dedupe to minimize repetition.
- Gap detection for long silences; documentation in `docs/conversation.md`.

### Metrics
- Implemented per-session metrics logger writing JSONL event streams and summaries under `metrics/`.
- Tracking transcripts (final/interim, confidence), sentences, suggestions (latency), gaps, and errors.
- Docs in `docs/metrics.md`.
