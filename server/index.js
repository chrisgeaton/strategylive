import http from 'http';
import express from 'express';
import { WebSocketServer } from 'ws';
import { createWhisperSession } from './lib/whisperClient.js';
import { suggestFromClaude } from './lib/claudeClient.js';
import { TranscriptAggregator } from './lib/aggregator.js';
import { ConversationState } from './lib/conversationState.js';
import { SuggestionEngine } from './lib/suggestionEngine.js';
import { MetricsLogger } from './lib/metrics.js';
import { v4 as uuidv4 } from 'uuid';

const app = express();
const server = http.createServer(app);
const wss = new WebSocketServer({ server });

const PORT = process.env.PORT || 3001;

// Add CORS middleware
app.use((req, res, next) => {
  res.header('Access-Control-Allow-Origin', '*');
  res.header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS');
  res.header('Access-Control-Allow-Headers', 'Origin, X-Requested-With, Content-Type, Accept');
  next();
});

app.get('/health', (_req, res) => res.json({ ok: true }));

// Minimal in-memory session store for transcripts per connection
const sessionData = new Map();

console.log('WebSocket server ready, waiting for connections...');

wss.on('connection', (ws, req) => {
  console.log('WebSocket connection attempt from:', req.headers.origin || 'unknown origin');
  console.log('WebSocket URL:', req.url);
  console.log('🔗 WebSocket SUCCESSFULLY connected - readyState:', ws.readyState);
  
  const params = new URLSearchParams(req.url?.split('?')[1] || '');
  const kind = params.get('kind') || 'audio';
  const sampleRate = Number(params.get('sample_rate') || process.env.DEEPGRAM_SAMPLE_RATE || 48000);
  const channels = Math.max(1, Math.min(2, Number(params.get('channels') || 1)));
  
  console.log('WebSocket params:', { kind, sampleRate, channels });

  if (kind !== 'audio') {
    ws.send(JSON.stringify({ type: 'error', error: 'Unsupported kind' }));
    ws.close();
    return;
  }

  const whisper = createWhisperSession({ sampleRate, channels });
  const conv = new ConversationState();
  const agg = new TranscriptAggregator({
    pauseMs: 400,
    minChars: 8,
    minConfidence: 0.6,
    gapMs: 3500,
    onGap: (g) => {
      if (ws.readyState === ws.OPEN) ws.send(JSON.stringify({ type: 'gap', durationMs: g.durationMs }));
    }
  });
  const sugg = new SuggestionEngine({ cooldownMs: 12000 });
  const state = { speaking: { sales: false, prospect: false } };
  const sessionId = uuidv4();
  const metrics = new MetricsLogger({ sessionId, meta: { sampleRate, channels, ua: req.headers['user-agent'] || '' } });
  sessionData.set(ws, state);

  whisper.onTranscript((payload, isFinal) => {
    console.log('Transcript received:', { payload, isFinal });
    const text = typeof payload === 'string' ? payload : payload?.text;
    if (!text) {
      console.log('No text in transcript payload');
      return;
    }
    const speaker = (typeof payload === 'object' && payload?.channelIndex != null)
      ? (payload.channelIndex === 0 ? 'sales' : 'prospect')
      : undefined; // unknown if single-channel

    console.log(`Transcript: "${text}" (final: ${isFinal}, speaker: ${speaker})`);

    // Forward raw transcript for UI
    // Emit raw transcript and record metrics
    const confidence = Array.isArray(payload.words) && payload.words.length ?
      (payload.words.map(w=>Number(w.confidence)).filter(n=>!Number.isNaN(n)).reduce((a,b)=>a+b,0) / payload.words.length) : undefined;
    ws.send(JSON.stringify({ type: 'transcript', text, final: isFinal, speaker }));
    metrics.event('transcript', { final: isFinal, speaker, textLen: text.length, confidence });
    metrics.recordTranscript({ final: isFinal, speaker, confidence });

    // Ingest into aggregator for sentence detection and filtering
    const results = agg.ingest({ text, isFinal, words: payload.words || [], speaker }, (note) => {
      if (note.type === 'raw') {
        // hook for future confidence UI if needed
      } else if (note.type === 'gap') {
        metrics.event('gap', { durationMs: note.durationMs });
        metrics.incGap();
      }
    });

    // Update speaking activity heuristics (simple: any interim from speaker indicates active)
    if (!isFinal && speaker) state.speaking[speaker] = true;
    if (isFinal && speaker) state.speaking[speaker] = false;

    for (const r of results) {
      const { clean, phase, ts } = conv.addUtterance({ speaker: r.speaker, text: r.sentence });
      metrics.event('sentence', { speaker: r.speaker, phase, textLen: clean.length });
      metrics.recordSentence({ speaker: r.speaker });
      const speakingActive = state.speaking.sales || state.speaking.prospect;
      if (sugg.shouldTrigger({ speaker: r.speaker, sentence: clean, phase, speakingActive })) {
        const context = conv.getRecentContext(1400);
        const firedAt = Date.now();
        suggestFromClaude(`Phase: ${phase}\n\n${context}\n\nProspect just said: "${clean}"`).then((suggestion) => {
          if (!suggestion) return;
          if (ws.readyState === ws.OPEN) ws.send(JSON.stringify({ type: 'suggestion', suggestion }));
          const latencyMs = Date.now() - firedAt;
          metrics.event('suggestion', { phase, latencyMs, suggestionLen: suggestion.length });
          metrics.incSuggestion();
          metrics.recordSuggestionLatency(latencyMs);
        }).catch((err) => {
          if (ws.readyState === ws.OPEN) ws.send(JSON.stringify({ type: 'error', error: 'suggestion_failed', message: String(err) }));
          metrics.event('error', { source: 'suggestion', message: String(err) });
        });
      }
    }
  });

  whisper.onError((err) => {
    console.log('Deepgram error:', err);
    if (ws.readyState === ws.OPEN) ws.send(JSON.stringify({ type: 'error', error: 'deepgram_error', message: String(err) }));
    metrics.event('error', { source: 'deepgram', message: String(err) });
  });

  let audioChunkCount = 0;
  
  ws.on('message', (data, isBinary) => {
    // Expect 16-bit PCM little-endian frames or Float32 arrays encoded as ArrayBuffer
    audioChunkCount++;
    console.log(`🎯 MESSAGE HANDLER CALLED - chunk ${audioChunkCount}, size: ${data.length}, isBinary: ${isBinary}`);
    if (audioChunkCount % 100 === 0) {
      console.log(`Received ${audioChunkCount} audio chunks, latest size: ${data.length} bytes`);
    }
    
    try {
      // Debug the message format
      if (audioChunkCount === 1) {
        console.log('First message - isBinary:', isBinary, 'data type:', typeof data, 'data length:', data.length);
        if (data.length >= 8) {
          const bytes = isBinary ? Array.from(data.slice(0, 8)) : Array.from(Buffer.from(data).slice(0, 8));
          console.log('First 8 bytes received:', bytes.map(b => b.toString(16).padStart(2, '0')).join(' '));
        }
      }
      
      // Debug every few chunks to see raw data
      if (audioChunkCount <= 3 || audioChunkCount % 50 === 0) {
        const bytes = isBinary ? Array.from(data.slice(0, 16)) : Array.from(Buffer.from(data).slice(0, 16));
        console.log(`🔍 RAW CHUNK ${audioChunkCount} BYTES:`, bytes.map(b => b.toString(16).padStart(2, '0')).join(' '));
        console.log(`🔍 RAW CHUNK ${audioChunkCount} DECIMAL:`, bytes.slice(0, 8));
      }
      
      whisper.sendAudio(isBinary ? data : Buffer.from(data));
    } catch (e) {
      console.log('Audio forward error:', e);
      ws.send(JSON.stringify({ type: 'error', error: 'audio_forward_failed', message: String(e) }));
      metrics.event('error', { source: 'audio_forward', message: String(e) });
    }
  });

  ws.on('close', () => {
    sessionData.delete(ws);
    whisper.close();
    metrics.endSession();
  });
});

server.listen(PORT, () => {
  console.log(`Server listening on http://localhost:${PORT}`);
});
