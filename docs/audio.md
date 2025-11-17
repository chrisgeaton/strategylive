# Audio Capture Approach (Google Meet)

## Goals
- Capture audio from the active Google Meet tab.
- Distinguish salesperson (local mic) vs prospect (remote tab audio).
- Stream in real time to the backend with <200ms added processing delay.
- Handle permissions, device, and network issues robustly.

## Implementation

### Dual-Source Capture and Stereo Interleave
- Use `chrome.tabCapture.capture({ audio: true })` to capture the Meet tab (remote participants).
- Use `navigator.mediaDevices.getUserMedia({ audio: { echoCancellation: true, noiseSuppression: true }})` to capture the microphone.
- Combine streams with Web Audio API:
  - `AudioContext(48kHz)` → `MediaStreamSource` for mic and tab.
  - `ChannelMergerNode(2)` with channel 0 = mic (sales), channel 1 = tab (prospect).
  - `ScriptProcessor(1024, 2, 0)` reads Float32 frames and interleaves to 16-bit PCM stereo.
- Send PCM buffers via WebSocket to backend with query `channels=2&sample_rate=48000`.

### Backend Streaming
- Backend wraps Deepgram Live with `encoding=linear16`, `sample_rate=48000`, `channels=2`, `multichannel=true`, `diarize=true`.
- Transcripts include a channel index; we map channel 0 → `sales`, channel 1 → `prospect`.

### Fallbacks
- If mic permission is denied/unavailable, degrade to mono capture (tab only) with `channels=1`.
- Transcripts will not have role mapping in mono mode; Deepgram diarization may still separate speakers but without deterministic role labels.

## Latency Considerations
- Buffer size 1024 samples @48kHz ≈ 21.3ms frames.
- WebSocket send is immediate after each frame.
- Deepgram Live returns interim results; we forward those instantly.
- Target added processing <200ms is achievable on typical networks.

## Error Handling
- Permission denied: content script reports `permission_denied` and falls back (if possible).
- Device unavailable: reports `mic_unavailable` and uses tab-only mode.
- Network/WS errors: reconnect with exponential backoff up to 15s, without blocking UI.
- Meet UI changes: overlay is injected by selector-agnostic code; capture relies on `tabCapture` which is resilient to DOM changes.

## Constraints & Limitations
- Cross-browser: Chrome prioritized. `chrome.tabCapture` is Chrome-specific; other browsers may require alternative APIs or desktop capture.
- Call quality: Audio is captured passively via Web Audio; no output is played (node connected via zero-gain sink). No impact on call quality.
- Mic echo cancellation is enabled, but channel separation is not a perfect ground truth when voices overlap.
- Production should use WSS and auth; sample here uses unsecured WS for local dev.

## Testing Methodology
- Scenarios:
  - Solo (mic only) → ensure transcripts labeled `sales`.
  - Remote-only (muted mic) → ensure transcripts labeled `prospect`.
  - Overlap speech → confirm both channels carry audio, labels present; Deepgram diarization quality depends on overlap.
  - Permission denied → observe fallback to mono and error status.
  - Network drop → observe auto-reconnect and resumed streaming.
- Tools:
  - Chrome extension devtools console for status logs.
  - Backend logs for WS connect/disconnect and errors.
  - Deepgram dashboard to verify channel/multichannel recognition.

## Performance Characteristics (Initial)
- Frame size: 1024 @48kHz (~21ms); measured send interval aligns with buffer cadence.
- Round-trip interim transcript times observed locally typically 80–150ms (depends on network).
- CPU impact in content script minimal on modern hardware; AudioWorklet can be considered if needed.

