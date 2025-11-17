# Task: Add metrics logger for conversation intelligence

## Date
2025-09-11 16:02

## Prompt
Please add the metrics logger

## Context
We want to record per-session events and summary statistics to validate transcription quality, speaker mapping, and suggestion timing without impacting latency.

## Actions Taken
1. Implemented `MetricsLogger` writing JSONL events to `metrics/<sessionId>.jsonl` and session summary to `metrics/<sessionId>-summary.json`.
2. Wired metrics into `server/index.js`:
   - Logs transcript events with confidence, speaker, and final/interim.
   - Logs sentence events (post-filtering) with phase.
   - Logs suggestion events with phase and request→response latency.
   - Logs gap and error events; writes summary on session close.
3. Added `docs/metrics.md` describing logged data and usage.

## Files Changed
- `server/lib/metrics.js` — new metrics logger module.
- `server/index.js` — integrated logging on key pipeline stages and errors.
- `docs/metrics.md` — documentation for metrics.

## Testing
- Local run: verified files are created in `metrics/` and JSONL lines append per event.
- Confirmed summary includes counters, avg confidence, and latency info.

## Outcome
Per-session metrics now captured for analysis without network dependencies. Ready to evaluate accuracy and timing against targets.

## Notes
- Future: add configurable log sampling, structured call IDs, and aggregate reporting.

