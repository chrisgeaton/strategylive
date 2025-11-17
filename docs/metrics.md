# Metrics Logging

## Overview
Each WebSocket session logs structured events into `metrics/<sessionId>.jsonl` and writes a session summary to `metrics/<sessionId>-summary.json` when the session closes.

## What’s Captured
- transcript: final/interim, speaker, text length, average confidence
- sentence: speaker, phase, text length (post-filtering)
- suggestion: phase, latency from request to response (ms), suggestion length
- gap: detected long pause duration (ms)
- error: source and message
- session_start/session_end: metadata and summary

## Files
- JSONL: one JSON record per line with a `ts` (timestamp) and `type`
- Summary: counters, average confidence, suggestion latency mean, session duration, meta (UA, sample rate, channels)

## Usage
- Logs are written automatically during calls. Inspect `metrics/` after a session.
- Use any JSONL tool or a quick script to aggregate across sessions.

## Notes
- Accuracy still requires human evaluation; averages and counts support that process.
- Consider adding structured IDs for calls/opportunities to correlate with CRM data.

