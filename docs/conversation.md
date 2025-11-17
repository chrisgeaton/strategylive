# Conversation Intelligence Pipeline

## Goals
Transform raw Deepgram live transcripts into actionable sales insights while preserving low end-to-end latency.

## Processing Stages
1. Ingestion
   - Receive Deepgram events with interim/final flags and word timings/confidence.
   - Pass through interim for UI; process finals for intelligence.
2. Cleaning & Segmentation
   - Remove filler words (e.g., "um", "uh", "you know").
   - Sentence boundary detection using punctuation and pauses (>400ms) from word timestamps.
3. Conversation State Tracking
   - Maintain timeline of utterances with speaker, type (statement/question/objection), phase.
   - Phases: opening → discovery → demo → objection handling → closing (heuristic keywords).
   - Identify topics by recurring keywords.
4. Suggestion Triggers
   - Trigger on complete prospect statements (not on every interim token).
   - Smart timing: skip while anyone is actively speaking (no interruptions).
   - Cooldown and de-duplication to avoid repetition; prioritize phase-appropriate guidance.

## Performance Optimizations
- Batch at sentence boundaries; skip low-confidence (<0.6 average) segments.
- 1024-sample audio frames (~21ms) maintain sub-200ms perceived latency.
- Suggestions gated by cooldown to reduce LLM calls while staying responsive.

## Gap Detection
- Detect long pauses (>3.5s) and surface as `gap` events for optional UI handling (e.g., prompt a question when natural).

## Accuracy & Metrics (to collect)
- WER on internal sales calls; target >85% business vocabulary accuracy.
- Speaker mapping accuracy (>90%) via stereo channel heuristic.
- Suggestion timing naturalness: no suggestions during active prospect speaking.
- Topic coherence across transitions (manual annotation sample).

## Edge Cases & Handling
- Overlapping speech: sentence boundary waits for finals; some interleaving may occur but phase logic remains robust.
- Low-confidence audio: filtered; deepen thresholds if call quality degrades.
- UI changes on Meet: capture is tab-level (resilient), overlay is DOM-agnostic via iframe.

## Next Steps
- Add AudioWorklet for processing stability; consider VAD for finer speech activity detection.
- Phase detection via small classifier; topic modeling with embeddings for better coherence.

